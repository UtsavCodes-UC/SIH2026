"""
Loads a real city's road network via OSMnx (OpenStreetMap) and converts it
into the internal TrafficGraph schema, for the "real or simulated large-scale
scenario" demonstration deliverable.

    - the fetched network is cached on disk as GraphML, so a demo doesn't
      depend on the Overpass API being reachable after the first load
    - only the largest STRONGLY connected component is kept: every retained
      node can reach every other one on the directed road graph, so any set of
      stops is routable
    - travel time comes from segment length and the `maxspeed` tag when present,
      otherwise a typical urban speed for the road class (OSMnx's own speed
      helpers changed names between major versions, so we don't depend on them)
    - every node gets `lat`, `lon` (for the map) and `pos` (km east/north of the
      centre, for traffic patterns); edges keep their road geometry as `shape`
      for drawing routes along the actual streets
"""

from __future__ import annotations

import json
import os
import pickle
import re
import shutil
import threading
from pathlib import Path

import networkx as nx

from app.core.geo import local_km
from app.core.graph_model import TrafficGraph

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
# The four preset places (at the UI's default 1200 m radius) ship with the repo, so a fresh clone, a fresh Docker container or a
# fresh cloud instance loads them at once instead of downloading from OpenStreetMap (map data (c) OpenStreetMap contributors, ODbL).
PRESET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "presets"

# Parsing a map file and converting it is the slow part of loading a city (about a second on a laptop, half a minute on a small free
# host). The converted graph is kept in memory as bytes, so every later load of the same file is an unpickle and returns a fresh
# copy: sessions never share edits. Keyed by the file too, so a re-downloaded map is never served from the memo.
_CITY_MEMO: dict[tuple, bytes] = {}
_CITY_MEMO_MAX = 12

# Public Overpass servers, tried in this order. The main one can refuse connections from cloud hosts (a free Render instance could
# not reach it), and osmnx then fails with a confusing "cannot access local variable 'response'" instead of saying so.
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api",
    "https://overpass.private.coffee/api",
    "https://overpass.kumi.systems/api",
    "https://maps.mail.ru/osm/tools/overpass/api",
)

# Typical urban speeds (km/h) when a segment has no usable maxspeed tag.
DEFAULT_SPEED_KPH = {
    "motorway": 70.0, "motorway_link": 45.0, "trunk": 55.0, "trunk_link": 40.0,
    "primary": 40.0, "primary_link": 30.0, "secondary": 35.0, "secondary_link": 28.0,
    "tertiary": 30.0, "tertiary_link": 25.0, "unclassified": 28.0, "residential": 22.0,
    "living_street": 12.0, "service": 15.0,
}
FALLBACK_SPEED_KPH = 25.0

# A few ready-made places for the UI (approximate centre points).
PRESETS = [
    {"name": "Connaught Place, New Delhi", "lat": 28.6315, "lon": 77.2167},
    {"name": "Sector 18, Noida", "lat": 28.5700, "lon": 77.3210},
    {"name": "MG Road, Bengaluru", "lat": 12.9758, "lon": 77.6068},
    {"name": "CST / Fort, Mumbai", "lat": 18.9398, "lon": 72.8355},
]


class CityLoadError(RuntimeError):
    """The city network could not be fetched (usually: no network / Overpass unreachable)."""


class UnusablePlaceError(CityLoadError):
    """The request itself can't work, so retrying won't help: an unknown place name, or a place with almost no roads."""


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def parse_speed_kph(maxspeed, highway) -> float:
    """maxspeed can be '50', '30 mph', a list of those, or missing; fall back to the road class."""
    raw = _first(maxspeed)
    if raw is not None:
        match = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mph)?", str(raw).lower())
        if match:
            speed = float(match.group(1)) * (1.609344 if match.group(2) else 1.0)
            if speed > 0:
                return speed
    return DEFAULT_SPEED_KPH.get(_first(highway), FALLBACK_SPEED_KPH)


def to_traffic_graph(osm_graph: nx.MultiDiGraph, centre_lat: float, centre_lon: float) -> TrafficGraph:
    """Convert an OSMnx MultiDiGraph (nodes carry x=lon, y=lat; edges carry length in metres)."""
    strong = max(nx.strongly_connected_components(osm_graph), key=len)
    kept = osm_graph.subgraph(strong)

    graph = TrafficGraph(directed=True)
    for node, data in kept.nodes(data=True):
        lat, lon = float(data["y"]), float(data["x"])
        graph.add_node(int(node), lat=lat, lon=lon, pos=local_km(lat, lon, centre_lat, centre_lon))

    best: dict[tuple[int, int], tuple[float, float, list | None, str | None]] = {}
    for u, v, data in kept.edges(data=True):
        if u == v:
            continue
        length_km = float(data.get("length", 0.0)) / 1000.0
        if length_km <= 0:
            continue
        highway = _first(data.get("highway"))
        minutes = length_km / parse_speed_kph(data.get("maxspeed"), highway) * 60.0
        geometry = data.get("geometry")
        shape = [(lat, lon) for lon, lat in geometry.coords] if geometry is not None else None
        key = (int(u), int(v))
        # parallel roads: keep the quickest; on a tie keep the one that has road geometry to draw
        if key not in best:
            best[key] = (length_km, minutes, shape, highway)
        else:
            _, best_minutes, best_shape, _ = best[key]
            faster = minutes < best_minutes - 1e-12
            tie_with_shape = abs(minutes - best_minutes) <= 1e-12 and best_shape is None and shape is not None
            if faster or tie_with_shape:
                best[key] = (length_km, minutes, shape, highway)

    for (u, v), (length_km, minutes, shape, highway) in best.items():
        graph.add_edge(u, v, length_km, minutes, 1.0)
        if shape is not None:
            graph.graph[u][v]["shape"] = shape
        if highway is not None:
            graph.graph[u][v]["highway"] = str(highway)  # road class: live-traffic sampling favours major roads
    return graph


def city_key(lat: float, lon: float, radius_m: int, network_type: str = "drive") -> str:
    """Identifies one downloaded map; also ties recorded traffic snapshots to it."""
    return f"osm_{lat:.4f}_{lon:.4f}_{radius_m}_{network_type}"


def _cache_path(lat: float, lon: float, radius_m: int, network_type: str) -> Path:
    return CACHE_DIR / f"{city_key(lat, lon, radius_m, network_type)}.graphml"


def _seed_from_presets(path: Path) -> None:
    """Copy a bundled preset map into the cache the first time it is asked for (no-op for any other place)."""
    bundled = PRESET_DIR / path.name
    if not path.exists() and bundled.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")  # copy, then rename: never a half-written file
        shutil.copyfile(bundled, partial)
        partial.replace(path)


def _memo_key(path: Path) -> tuple:
    stat = path.stat()
    return (str(path), stat.st_mtime_ns, stat.st_size)


def warm_presets() -> None:
    """Load the four preset places once, so the first visitor does not wait for the conversion (run in the background at start-up)."""
    # the default radius of every preset first, then the bigger bundled maps that other radii are cut from
    jobs = [(p, 1200) for p in PRESETS] + [(p, r) for p in PRESETS for r in _bundled_radii(p["lat"], p["lon"], "drive") if r != 1200]
    for preset, radius in jobs:
        try:
            load_city_graph(preset["lat"], preset["lon"], radius_m=radius)
        except Exception:  # noqa: BLE001 - warming is best effort; a failure just means that city loads on demand
            continue


def _bundled_radii(lat: float, lon: float, network_type: str) -> list[int]:
    """Radii (metres) at which this exact centre ships in PRESET_DIR, smallest first."""
    found = []
    for path in PRESET_DIR.glob(f"osm_{lat:.4f}_{lon:.4f}_*_{network_type}.graphml"):
        match = re.search(r"_(\d+)_" + re.escape(network_type) + r"\.graphml$", path.name)
        if match:
            found.append(int(match.group(1)))
    return sorted(found)


def _crop_from_bundle(lat: float, lon: float, radius_m: int, network_type: str) -> TrafficGraph | None:
    """A preset place at a smaller radius than the one that ships: cut the square of half-side `radius_m` out of the bigger map and keep
    its largest strongly connected part, which is what a download of that radius gives (up to a few roads at the very edge). Needs no
    internet, so changing the radius of a preset place is instant. None if no bundled map of that centre is big enough."""
    larger = [r for r in _bundled_radii(lat, lon, network_type) if r > radius_m]
    if not larger:
        return None
    big = load_city_graph(lat, lon, radius_m=larger[0], network_type=network_type)
    half = radius_m / 1000.0  # `pos` is kilometres east and north of the centre
    inside = [n for n, a in big.graph.nodes(data=True) if abs(a["pos"][0]) <= half and abs(a["pos"][1]) <= half]
    if not inside:
        return None
    part = big.graph.subgraph(inside)
    strong = max(nx.strongly_connected_components(part), key=len)
    cropped = TrafficGraph(directed=True)
    for node in strong:
        cropped.add_node(node, **big.graph.nodes[node])
    for u, v, data in part.subgraph(strong).edges(data=True):
        cropped.graph.add_edge(u, v, **data)  # keeps the road shape, class, congestion and weight
    return cropped


def _download(ox, lat: float, lon: float, radius_m: int, network_type: str):
    """Download a map, trying each public Overpass server in turn and saying, per server, what went wrong."""
    _configure_osmnx(ox)
    failures = []
    for endpoint in OVERPASS_ENDPOINTS:
        ox.settings.overpass_endpoint = endpoint
        try:
            return ox.graph_from_point((lat, lon), dist=radius_m, network_type=network_type, simplify=True)
        except Exception as exc:  # network errors surface as many different exception types
            host = endpoint.split("/")[2]
            # osmnx 1.9 raises UnboundLocalError from its own error handler when it cannot connect at all
            reason = "could not connect" if isinstance(exc, UnboundLocalError) else f"{type(exc).__name__}: {str(exc)[:110]}"
            failures.append(f"{host}: {reason}")
    raise CityLoadError(
        f"could not fetch OpenStreetMap data for ({lat:.4f}, {lon:.4f}) at {radius_m} m: no server answered ({'; '.join(failures)}). "
        "Check the internet connection, or load a location that was cached earlier."
    )


def _configure_osmnx(ox) -> None:
    """Keep OSMnx's own HTTP cache inside data/cache (its default is ./cache in the current directory)."""
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(CACHE_DIR / "osmnx_http")
    ox.settings.requests_timeout = 60


def load_city_graph(
    lat: float,
    lon: float,
    radius_m: int = 1500,
    network_type: str = "drive",
    refresh: bool = False,
) -> TrafficGraph:
    """Fetch (or load from the disk cache) the road network within `radius_m` of a point."""
    path = _cache_path(lat, lon, radius_m, network_type)
    if not refresh:
        _seed_from_presets(path)
        if path.exists() and (blob := _CITY_MEMO.get(_memo_key(path))) is not None:
            return pickle.loads(blob)
        if not path.exists() and (cropped := _crop_from_bundle(lat, lon, radius_m, network_type)) is not None:
            return cropped

    import osmnx as ox  # heavy import; only needed when a city is actually requested

    if path.exists() and not refresh:
        osm_graph = ox.load_graphml(path)
    else:
        osm_graph = _download(ox, lat, lon, radius_m, network_type)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(osm_graph, path)

    graph = to_traffic_graph(osm_graph, lat, lon)
    if len(_CITY_MEMO) >= _CITY_MEMO_MAX:
        _CITY_MEMO.pop(next(iter(_CITY_MEMO)))
    _CITY_MEMO[_memo_key(path)] = pickle.dumps(graph, protocol=pickle.HIGHEST_PROTOCOL)
    return graph


def _geocode_cache_path() -> Path:
    return CACHE_DIR / "geocode.json"


def _read_geocode_cache() -> dict[str, list[float]]:
    try:
        data = json.loads(_geocode_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _place_key(place: str) -> str:
    return " ".join(place.lower().split())


def remembered_places() -> dict[str, tuple[float, float]]:
    """Places looked up or loaded before (lower-cased name -> (lat, lon)); they work without the internet."""
    places = {}
    for key, value in _read_geocode_cache().items():
        if isinstance(value, list) and len(value) == 2:
            places[key] = (float(value[0]), float(value[1]))
    return places


def remember_place(place: str, lat: float, lon: float) -> None:
    cache = _read_geocode_cache()
    cache[_place_key(place)] = [float(lat), float(lon)]
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _geocode_cache_path().write_text(json.dumps(cache, indent=1), encoding="utf-8")
    except OSError:
        pass  # a read-only disk only costs the offline shortcut


def is_preset(lat: float, lon: float) -> bool:
    return any(abs(p["lat"] - lat) < 0.0005 and abs(p["lon"] - lon) < 0.0005 for p in PRESETS)


def geocode(place: str) -> tuple[float, float]:
    """Place name -> (lat, lon) via Nominatim. Answers are remembered on disk, so a place that was
    typed once loads again later without the internet (its map is cached the same way)."""
    cached = remembered_places().get(_place_key(place))
    if cached:
        return cached

    import osmnx as ox
    from osmnx._errors import InsufficientResponseError

    _configure_osmnx(ox)
    try:
        lat, lon = ox.geocode(place)
    except InsufficientResponseError as exc:
        raise UnusablePlaceError(
            f"Couldn't find a place called {place!r}. Try adding the city or country, "
            "for example 'Koramangala, Bengaluru, India'."
        ) from exc
    except Exception as exc:  # network errors surface as many different exception types
        raise CityLoadError(
            f"could not look up {place!r} on OpenStreetMap: {exc}. "
            "Check the internet connection, or pick one of the ready-made places."
        ) from exc

    remember_place(place, lat, lon)
    return float(lat), float(lon)
