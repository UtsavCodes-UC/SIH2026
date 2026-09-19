"""
Place-name suggestions for the "Search for another place" box.

Two sources are merged, best first:

1. Places we already know, matched instantly and offline: the ready-made presets and any place the
   user has loaded before (remembered in the geocode cache, see `osm_loader.remember_place`).
2. Photon (https://photon.komoot.io), a search-as-you-type geocoder built on OpenStreetMap data.
   OpenStreetMap's own Nominatim server is NOT used here: its usage policy forbids auto-complete
   requests. Photon is meant for it, but is a free shared service, so results are cached, the browser
   waits for a pause in typing, and a self-hosted instance can be used through PLACE_SEARCH_URL
   (set it to `off` to switch online suggestions off).

Photon problems never break the box: the caller still gets the local matches, plus a note that the
online list is unavailable, and the user can always press Enter to search for exactly what they typed.
"""

from __future__ import annotations

import collections
import functools
import json
import logging
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.config import place_search_url
from app.core.geo import local_km
from app.data import osm_loader
from app.data.http import open_url

log = logging.getLogger(__name__)

USER_AGENT = "SIH26137-route-optimizer/0.2 (student project; place search)"
MIN_ONLINE_CHARS = 3  # fewer letters match too much to be worth a request
SAME_PLACE_KM = 0.3  # an online result this close to a known place is the same place

# What OpenStreetMap features are not places you would deliver around (pumping stations, buildings, ...).
NOISE_KEYS = {"landuse", "building", "man_made", "power", "waterway", "railway", "boundary", "office", "craft"}
NOISE_TYPES = {"house"}  # a bare house number


class PlaceSearchUnavailable(RuntimeError):
    """The online suggestion service could not be reached or answered badly."""


@dataclass(frozen=True)
class PlaceSuggestion:
    title: str  # "Koramangala"
    detail: str  # "Bangalore South, Karnataka, India"
    label: str  # title + detail: what the map is named after loading
    kind: str  # "suburb", "road", "city", ...
    lat: float
    lon: float
    source: str  # "preset" | "recent" | "online"


def _kind(props: dict) -> str:
    key, value = props.get("osm_key"), str(props.get("osm_value") or "")
    if key == "highway":
        return "road"
    return (value or props.get("type") or "place").replace("_", " ")


def parse_photon(payload: dict, limit: int) -> list[PlaceSuggestion]:
    """Photon GeoJSON -> suggestions, dropping non-places and repeats. Coordinates are [lon, lat]."""
    found: list[PlaceSuggestion] = []
    seen: set[str] = set()
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        try:
            lon, lat = (float(c) for c in feature["geometry"]["coordinates"][:2])
        except (KeyError, TypeError, ValueError):
            continue
        title = (props.get("name") or props.get("street") or "").strip()
        if not title or props.get("osm_key") in NOISE_KEYS or props.get("type") in NOISE_TYPES:
            continue
        region = [props.get("city") or props.get("county"), props.get("state"), props.get("country")]
        parts = [p.strip() for p in region if isinstance(p, str) and p.strip() and p.strip() != title]
        detail = ", ".join(dict.fromkeys(parts))  # in order, no repeats
        label = f"{title}, {detail}" if detail else title
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        found.append(PlaceSuggestion(title, detail, label, _kind(props), lat, lon, "online"))
        if len(found) == limit:
            break
    return found


def _display_name(key: str) -> str:
    """'koramangala 6th block, bengaluru' -> 'Koramangala 6th Block, Bengaluru' (str.title() would give '6Th')."""
    return re.sub(r"(?<![\w'])[a-z]", lambda m: m.group(0).upper(), key)


def local_matches(query: str, limit: int = 4) -> list[PlaceSuggestion]:
    """Presets and remembered places whose name contains every word of the query."""
    words = query.lower().split()
    if not words:
        return []
    candidates: list[PlaceSuggestion] = []
    for preset in osm_loader.PRESETS:
        title, _, detail = preset["name"].partition(", ")
        candidates.append(PlaceSuggestion(title, detail, preset["name"], "preset", preset["lat"], preset["lon"], "preset"))
    for key, (lat, lon) in osm_loader.remembered_places().items():
        label = _display_name(key)
        title, _, detail = label.partition(", ")
        candidates.append(PlaceSuggestion(title, detail, label, "recent", lat, lon, "recent"))

    def rank(s: PlaceSuggestion) -> tuple[int, str]:
        return (0 if s.label.lower().startswith(words[0]) else 1, s.label)

    matches = [s for s in candidates if all(w in s.label.lower() for w in words)]
    unique: list[PlaceSuggestion] = []
    for s in sorted(matches, key=rank):
        if not any(_same_place(s, u) for u in unique):  # a preset that was also loaded before
            unique.append(s)
    return unique[:limit]


def _same_place(a: PlaceSuggestion, b: PlaceSuggestion) -> bool:
    east, north = local_km(a.lat, a.lon, b.lat, b.lon)
    return math.hypot(east, north) < SAME_PLACE_KM


class PhotonPlaceSearch:
    """Online suggestions from Photon, with a small in-memory cache so repeated typing costs nothing."""

    def __init__(
        self,
        base_url: str = "https://photon.komoot.io/api/",
        timeout: float = 6.0,
        urlopen=open_url,
        clock=time.monotonic,
        cache_ttl_sec: float = 3600.0,
        cache_size: int = 256,
    ):
        self._base_url = base_url
        self._timeout = timeout
        self._urlopen, self._clock = urlopen, clock
        self._ttl, self._size = cache_ttl_sec, cache_size
        self._cache: collections.OrderedDict[str, tuple[float, list[PlaceSuggestion]]] = collections.OrderedDict()
        self._lock = threading.Lock()

    def search(self, query: str, limit: int = 6, near: tuple[float, float] | None = None) -> list[PlaceSuggestion]:
        """`near` (lat, lon) softly prefers results around a point, e.g. the map being looked at. It only
        re-ranks: a typo like "indiranagr" finds Bengaluru's Indiranagar first, yet "colaba" still finds Mumbai."""
        key = " ".join(query.lower().split())
        if near:
            key += f"@{near[0]:.1f},{near[1]:.1f}"  # about 11 km: nearby maps share cached answers
        with self._lock:
            hit = self._cache.get(key)
            if hit and self._clock() - hit[0] < self._ttl:
                self._cache.move_to_end(key)
                return hit[1][:limit]

        # Ask for a few extra: filtering out non-places and repeats thins the list.
        params = {"q": query, "limit": limit + 4, "lang": "en"}
        if near:
            params.update(lat=f"{near[0]:.4f}", lon=f"{near[1]:.4f}")
        url = self._base_url + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with self._urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise PlaceSearchUnavailable(str(getattr(exc, "reason", exc))) from exc
        if not isinstance(payload, dict):
            raise PlaceSearchUnavailable("unexpected answer from the suggestion service")

        results = parse_photon(payload, limit)
        with self._lock:
            self._cache[key] = (self._clock(), results)
            while len(self._cache) > self._size:
                self._cache.popitem(last=False)
        return results


def suggest(
    query: str, online: PhotonPlaceSearch | None, limit: int = 6, near: tuple[float, float] | None = None
) -> tuple[list[PlaceSuggestion], str | None]:
    """(suggestions, note). The note says why online suggestions are missing, or is None when all is well."""
    query = " ".join(query.split())
    known = local_matches(query)
    if online is None or len(query) < MIN_ONLINE_CHARS:
        return known, None
    try:
        fresh = online.search(query, limit, near)
    except PlaceSearchUnavailable as exc:
        log.warning("place suggestions unavailable: %s", exc)
        return known, "Online suggestions are unavailable right now. Saved places are still listed; press Enter to search for what you typed."
    merged = list(known)
    merged += [s for s in fresh if not any(_same_place(s, k) for k in known)]
    return merged[:limit], None


@functools.lru_cache(maxsize=4)
def _searcher_for(url: str) -> PhotonPlaceSearch:
    return PhotonPlaceSearch(url)


def get_place_search() -> PhotonPlaceSearch | None:
    """The online searcher (one per URL, so its cache persists), or None when switched off. A FastAPI dependency."""
    url = place_search_url()
    return _searcher_for(url) if url else None
