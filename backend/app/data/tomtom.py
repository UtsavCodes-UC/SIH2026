"""
TomTom Traffic Flow adapter (Flow Segment Data API).

For a point it returns the speeds of the road segment nearest to it: `currentSpeed` (live)
and `freeFlowSpeed` (ideal conditions) in km/h, a `confidence` in [0, 1], a `roadClosure`
flag and the segment's shape. Docs:
https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data

Notes
- Free plan: 2,500 non-tile requests a day, so callers sample the network rather than measure
  every road, and requests are paced (`max_qps`) instead of fired all at once.
- The key travels only from this server to TomTom. It is never logged, never returned by the
  API, and is scrubbed from every error message raised here.
- 400 means "no road near that point at this zoom": a missing reading, not a failure.
  403 means TomTom rejected the key (wrong key, or Traffic API not enabled for it, or domain
  whitelisting turned on, which blocks server-side calls); 429 means the rate limit was hit.
"""

from __future__ import annotations

import functools
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from app.core.live_traffic import FlowSample

BASE_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/{zoom}/json"


@functools.lru_cache(maxsize=1)
def _tls_context() -> ssl.SSLContext:
    """The OS trust store plus the Mozilla roots that ship with certifi.

    Python on Windows reads only the roots already installed in the OS store, and Windows installs some
    lazily, so a fresh machine can fail with "self signed certificate in certificate chain" against a
    perfectly valid site (seen once against api.tomtom.com; the next call worked). Adding certifi's bundle
    makes the call independent of that. Verification stays on.
    """
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError):
        pass
    return context


def _default_urlopen(url: str, timeout: float | None = None):
    return urllib.request.urlopen(url, timeout=timeout, context=_tls_context())


class TrafficProviderError(RuntimeError):
    """The live-traffic provider could not be used (bad key, quota, unreachable, no data)."""


class TomTomFlowProvider:
    name = "TomTom"

    def __init__(
        self,
        api_key: str,
        zoom: int = 15,
        max_qps: float = 5.0,
        timeout: float = 10.0,
        workers: int = 4,
        urlopen=_default_urlopen,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self._key = api_key
        self._zoom = zoom
        self._interval = 1.0 / max(max_qps, 0.1)
        self._timeout = timeout
        self._workers = workers
        self._urlopen, self._sleep, self._clock = urlopen, sleep, clock
        self._pace_lock = threading.Lock()
        self._next_slot = 0.0
        self._abort = threading.Event()

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "***") if self._key else text

    def _wait_for_turn(self) -> None:
        with self._pace_lock:
            now = self._clock()
            start = max(now, self._next_slot)
            self._next_slot = start + self._interval
        if start > now:
            self._sleep(start - now)

    def _request(self, lat: float, lon: float) -> dict | None:
        query = urllib.parse.urlencode({"key": self._key, "point": f"{lat:.6f},{lon:.6f}", "unit": "kmph"})
        url = f"{BASE_URL.format(zoom=self._zoom)}?{query}"
        last_problem = "no response"
        for attempt in range(3):
            if self._abort.is_set():
                return None
            self._wait_for_turn()
            try:
                with self._urlopen(url, timeout=self._timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code == 400:
                    return None  # nothing measured near this point
                if exc.code == 403:
                    self._abort.set()
                    raise TrafficProviderError(
                        "TomTom rejected the API key (HTTP 403). Check that the key is correct, that 'Traffic API' "
                        "(and 'Traffic Flow API') are enabled on it in the TomTom developer portal, and that domain "
                        "whitelisting is switched OFF (server-side calls send no browser Referer)."
                    ) from None
                if exc.code == 429:
                    last_problem = "rate limit reached (HTTP 429; the free plan allows 2,500 requests a day)"
                    self._sleep(1.0 * (attempt + 1))
                    continue
                last_problem = f"HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                last_problem = self._scrub(str(getattr(exc, "reason", exc)))
        if "rate limit" in last_problem:
            self._abort.set()
            raise TrafficProviderError(f"TomTom {last_problem}.") from None
        raise TrafficProviderError(f"could not get a reading from TomTom ({last_problem}).") from None

    def fetch_point(self, lat: float, lon: float) -> FlowSample | None:
        payload = self._request(lat, lon)
        if not payload:
            return None
        try:
            data = payload["flowSegmentData"]
            shape = [(float(c["latitude"]), float(c["longitude"])) for c in data.get("coordinates", {}).get("coordinate", [])]
            return FlowSample(
                lat=lat,
                lon=lon,
                current_kph=float(data["currentSpeed"]),
                free_flow_kph=float(data["freeFlowSpeed"]),
                confidence=float(data.get("confidence", 1.0)),
                road_closure=bool(data.get("roadClosure", False)),
                shape=shape,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def fetch(self, points: list[tuple[float, float]]) -> list[FlowSample | None]:
        """One reading per point (None where TomTom had nothing near it), in the same order."""
        self._abort.clear()
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            futures = [pool.submit(self.fetch_point, lat, lon) for lat, lon in points]
            results, error = [], None
            for future in futures:
                try:
                    results.append(future.result())
                except TrafficProviderError as exc:
                    error = error or exc
                    results.append(None)
        if error is not None:
            raise error
        return results
