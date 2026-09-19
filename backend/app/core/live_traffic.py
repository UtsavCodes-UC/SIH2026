"""
Turning live traffic-provider readings into congestion factors on the road graph.

Pipeline (no network here, so it is fully testable):

1. `build_road_index`   one entry per road (both directions collapsed), with its midpoint,
                        length and road class.
2. `choose_sample_roads` pick well-spread points, major roads first, to ask the provider about.
                        A free plan allows a few thousand requests a day, so we measure a
                        sample of the network rather than every road.
3. `apply_samples`      each reading (current vs free-flow speed of the road segment nearest
                        the queried point) becomes a slowdown ratio, matched to every OSM road
                        that lies along the reported segment, then spread to the roads we did
                        not measure (nearby measured roads of the same class weigh most, then
                        the class median).

A congestion factor is "how many times slower than free flow" and is never below 1.0 here:
we only ever slow roads down relative to the OSM base speed, never speed them up.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.geo import local_km
from app.core.graph_model import TrafficGraph

MAX_SLOWDOWN = 6.0  # a closed or crawling road never costs more than 6x its free-flow time
MATCH_KM = 0.03  # a road counts as "along" a reported segment if its midpoint is within 30 m
FALLBACK_MATCH_KM = 0.05
PROPAGATION_RADIUS_KM = 0.5
SAME_CLASS_BONUS, OTHER_CLASS_WEIGHT = 1.0, 0.4

CLASS_RANK = {
    "motorway": 0, "trunk": 0, "motorway_link": 1, "trunk_link": 1, "primary": 1, "primary_link": 2,
    "secondary": 2, "secondary_link": 3, "tertiary": 3, "tertiary_link": 4, "unclassified": 4,
    "residential": 5, "living_street": 6, "service": 6,
}
DEFAULT_RANK = 5


@dataclass
class FlowSample:
    """One provider reading for the road segment nearest (lat, lon)."""

    lat: float
    lon: float
    current_kph: float
    free_flow_kph: float
    confidence: float = 1.0
    road_closure: bool = False
    shape: list[tuple[float, float]] = field(default_factory=list)  # (lat, lon) along the segment

    @property
    def slowdown(self) -> float:
        if self.road_closure or self.current_kph <= 0:
            return MAX_SLOWDOWN
        return min(MAX_SLOWDOWN, max(1.0, self.free_flow_kph / self.current_kph))


@dataclass
class RoadIndex:
    ends: list[tuple]  # (u, v) for each road, in the direction first seen
    mid_km: np.ndarray  # (R, 2) midpoints in km east/north of the centre
    mid_latlon: np.ndarray  # (R, 2)
    length_km: np.ndarray
    rank: np.ndarray  # road-class rank, 0 = most important


@dataclass
class TrafficUpdate:
    roads_measured: int
    roads_total: int


def build_road_index(graph: TrafficGraph, centre: tuple[float, float]) -> RoadIndex:
    g = graph.graph
    seen: set[frozenset] = set()
    ends, mids, latlons, lengths, ranks = [], [], [], [], []
    for u, v, data in g.edges(data=True):
        key = frozenset((u, v))
        if key in seen:
            continue
        seen.add(key)
        a, b = g.nodes[u], g.nodes[v]
        lat, lon = (a["lat"] + b["lat"]) / 2.0, (a["lon"] + b["lon"]) / 2.0
        ends.append((u, v))
        mids.append(local_km(lat, lon, *centre))
        latlons.append((lat, lon))
        lengths.append(data["distance_km"])
        ranks.append(CLASS_RANK.get(data.get("highway"), DEFAULT_RANK))
    return RoadIndex(
        ends=ends,
        mid_km=np.array(mids, dtype=float).reshape(-1, 2),
        mid_latlon=np.array(latlons, dtype=float).reshape(-1, 2),
        length_km=np.array(lengths, dtype=float),
        rank=np.array(ranks, dtype=int),
    )


def choose_sample_roads(index: RoadIndex, n: int, min_spacing_km: float = 0.15) -> list[int]:
    """Indices of up to `n` roads: most important classes first, longest first, no two closer than
    `min_spacing_km` (relaxed by halves if the area is too small to place `n` that far apart)."""
    order = sorted(range(len(index.ends)), key=lambda i: (index.rank[i], -index.length_km[i], i))
    chosen: list[int] = []
    taken: set[int] = set()
    spacing = min_spacing_km
    for _ in range(4):
        for i in order:
            if len(chosen) >= n:
                break
            if i in taken:
                continue
            if chosen and np.min(np.linalg.norm(index.mid_km[chosen] - index.mid_km[i], axis=1)) < spacing:
                continue
            chosen.append(i)
            taken.add(i)
        if len(chosen) >= n:
            break
        spacing /= 2.0
    return chosen


def _distance_to_polyline(points: np.ndarray, polyline: np.ndarray) -> np.ndarray:
    """Distance from each of `points` (R, 2) to the polyline (S, 2)."""
    if len(polyline) == 1:
        return np.linalg.norm(points - polyline[0], axis=1)
    a, b = polyline[:-1], polyline[1:]
    ab = b - a
    ab2 = np.maximum((ab**2).sum(axis=1), 1e-12)
    ap = points[:, None, :] - a[None, :, :]
    t = np.clip((ap * ab[None]).sum(axis=2) / ab2[None], 0.0, 1.0)
    nearest = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(points[:, None, :] - nearest, axis=2).min(axis=1)


def _matched_roads(index: RoadIndex, sample: FlowSample, centre: tuple[float, float]) -> set[int]:
    hits: set[int] = set()
    if len(sample.shape) >= 2:
        polyline = np.array([local_km(la, lo, *centre) for la, lo in sample.shape], dtype=float)
        hits.update(np.nonzero(_distance_to_polyline(index.mid_km, polyline) <= MATCH_KM)[0].tolist())
    point = np.array(local_km(sample.lat, sample.lon, *centre), dtype=float)
    distances = np.linalg.norm(index.mid_km - point, axis=1)
    nearest = int(np.argmin(distances))
    if distances[nearest] <= FALLBACK_MATCH_KM:  # the queried road itself always gets its reading
        hits.add(nearest)
    return hits


def apply_samples(
    graph: TrafficGraph,
    centre: tuple[float, float],
    samples: list[FlowSample],
    index: RoadIndex | None = None,
) -> TrafficUpdate:
    """Write congestion factors onto every road of `graph` from the provider `samples`."""
    index = index or build_road_index(graph, centre)
    roads = len(index.ends)
    weighted_sum, weight = np.zeros(roads), np.zeros(roads)
    for sample in samples:
        w = max(sample.confidence, 0.05)
        for i in _matched_roads(index, sample, centre):
            weighted_sum[i] += w * sample.slowdown
            weight[i] += w

    measured = weight > 0
    ratios = np.ones(roads)
    ratios[measured] = weighted_sum[measured] / weight[measured]

    if measured.any() and not measured.all():
        m_mid, m_ratio, m_rank = index.mid_km[measured], ratios[measured], index.rank[measured]
        class_median = {int(r): float(np.median(m_ratio[m_rank == r])) for r in np.unique(m_rank)}
        overall = float(np.median(m_ratio))
        for i in np.nonzero(~measured)[0]:
            d = np.linalg.norm(m_mid - index.mid_km[i], axis=1)
            near = d <= PROPAGATION_RADIUS_KM
            if near.any():
                w = 1.0 / (d[near] + 0.05) ** 2 * np.where(m_rank[near] == index.rank[i], SAME_CLASS_BONUS, OTHER_CLASS_WEIGHT)
                ratios[i] = float((w * m_ratio[near]).sum() / w.sum())
            else:
                ratios[i] = class_median.get(int(index.rank[i]), overall)

    for (u, v), factor in zip(index.ends, ratios):
        for a, b in ((u, v), (v, u)):
            if graph.graph.has_edge(a, b):
                graph.update_congestion(a, b, float(factor))
    return TrafficUpdate(roads_measured=int(measured.sum()), roads_total=roads)


def count_roads(graph: TrafficGraph) -> int:
    return len({frozenset((u, v)) for u, v in graph.graph.edges()})


def export_factors(graph: TrafficGraph) -> list[list]:
    return [[u, v, d["congestion_factor"]] for u, v, d in graph.graph.edges(data=True)]


def import_factors(graph: TrafficGraph, factors: list[list]) -> int:
    """Apply saved [u, v, factor] entries to the edges that exist; returns how many matched."""
    matched = 0
    for u, v, factor in factors:
        if graph.graph.has_edge(u, v) and factor > 0:
            graph.update_congestion(u, v, float(factor))
            matched += 1
    return matched
