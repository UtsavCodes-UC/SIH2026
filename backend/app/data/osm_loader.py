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

import re
from pathlib import Path

import networkx as nx

from app.core.geo import local_km
from app.core.graph_model import TrafficGraph

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"

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

    best: dict[tuple[int, int], tuple[float, float, list | None]] = {}
    for u, v, data in kept.edges(data=True):
        if u == v:
            continue
        length_km = float(data.get("length", 0.0)) / 1000.0
        if length_km <= 0:
            continue
        minutes = length_km / parse_speed_kph(data.get("maxspeed"), data.get("highway")) * 60.0
        geometry = data.get("geometry")
        shape = [(lat, lon) for lon, lat in geometry.coords] if geometry is not None else None
        key = (int(u), int(v))
        # parallel roads: keep the quickest; on a tie keep the one that has road geometry to draw
        if key not in best:
            best[key] = (length_km, minutes, shape)
        else:
            _, best_minutes, best_shape = best[key]
            faster = minutes < best_minutes - 1e-12
            tie_with_shape = abs(minutes - best_minutes) <= 1e-12 and best_shape is None and shape is not None
            if faster or tie_with_shape:
                best[key] = (length_km, minutes, shape)

    for (u, v), (length_km, minutes, shape) in best.items():
        graph.add_edge(u, v, length_km, minutes, 1.0)
        if shape is not None:
            graph.graph[u][v]["shape"] = shape
    return graph


def _cache_path(lat: float, lon: float, radius_m: int, network_type: str) -> Path:
    return CACHE_DIR / f"osm_{lat:.4f}_{lon:.4f}_{radius_m}_{network_type}.graphml"


def load_city_graph(
    lat: float,
    lon: float,
    radius_m: int = 1500,
    network_type: str = "drive",
    refresh: bool = False,
) -> TrafficGraph:
    """Fetch (or load from the disk cache) the road network within `radius_m` of a point."""
    import osmnx as ox  # heavy import; only needed when a city is actually requested

    path = _cache_path(lat, lon, radius_m, network_type)
    if path.exists() and not refresh:
        osm_graph = ox.load_graphml(path)
    else:
        try:
            ox.settings.use_cache = True
            ox.settings.cache_folder = str(CACHE_DIR / "osmnx_http")
            ox.settings.requests_timeout = 60
            osm_graph = ox.graph_from_point((lat, lon), dist=radius_m, network_type=network_type, simplify=True)
        except Exception as exc:  # network errors surface as many different exception types
            raise CityLoadError(
                f"could not fetch OpenStreetMap data for ({lat:.4f}, {lon:.4f}): {exc}. "
                "Check the internet connection, or load a location that was cached earlier."
            ) from exc
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(osm_graph, path)

    return to_traffic_graph(osm_graph, lat, lon)


def geocode(place: str) -> tuple[float, float]:
    """Place name -> (lat, lon) via Nominatim (needs network)."""
    import osmnx as ox

    try:
        lat, lon = ox.geocode(place)
    except Exception as exc:
        raise CityLoadError(f"could not geocode {place!r}: {exc}") from exc
    return float(lat), float(lon)
