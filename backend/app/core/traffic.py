"""
Simulated traffic conditions: the "dynamic weight update mechanism" deliverable.

Each function rewrites the congestion factor of every edge (via
TrafficGraph.update_congestion, so edge weights stay in sync); routing then
reacts on the next solve. Factors multiply base travel time: 1.0 = free flow,
2.5 = 2.5x slower.

Every node needs a `pos` attribute in km (both the synthetic generator and the
OSM loader set one) for the spatial pattern in `apply_rush_hour`.
"""

from __future__ import annotations

import math
import random

import numpy as np

from app.core.graph_model import TrafficGraph


def clear_traffic(graph: TrafficGraph) -> None:
    for u, v in list(graph.graph.edges()):
        graph.update_congestion(u, v, 1.0)


def apply_random_traffic(graph: TrafficGraph, low: float = 0.8, high: float = 2.5, seed: int | None = None) -> None:
    """Independent congestion per directed edge, uniform in [low, high]."""
    if not 0 < low <= high:
        raise ValueError("need 0 < low <= high")
    graph.randomize_congestion(low, high, rng=random.Random(seed))


def apply_rush_hour(graph: TrafficGraph, peak: float = 2.5, noise: float = 0.15, seed: int | None = None) -> None:
    """Congestion peaks at the network's centre and decays outwards:

        factor = (1 + (peak - 1) * exp(-(d / sigma)^2)) * (1 +/- noise)

    with d the distance of the edge midpoint from the node centroid and sigma
    0.45 of the farthest node's distance -- so routes are pushed to detour
    around the busy core instead of cutting through it.
    """
    if peak < 1:
        raise ValueError("peak must be >= 1")
    rng = random.Random(seed)
    positions = {n: attrs.get("pos") for n, attrs in graph.graph.nodes(data=True)}
    if any(p is None for p in positions.values()):
        raise ValueError("rush-hour traffic needs a 'pos' (km) attribute on every node")

    coords = np.array(list(positions.values()), dtype=float)
    centre = coords.mean(axis=0)
    sigma = 0.45 * max(float(np.linalg.norm(coords - centre, axis=1).max()), 1e-9)

    for u, v in list(graph.graph.edges()):
        midpoint = (np.asarray(positions[u], dtype=float) + np.asarray(positions[v], dtype=float)) / 2.0
        distance = float(np.linalg.norm(midpoint - centre))
        factor = 1.0 + (peak - 1.0) * math.exp(-((distance / sigma) ** 2))
        factor *= 1.0 + rng.uniform(-noise, noise)
        graph.update_congestion(u, v, max(0.5, factor))
