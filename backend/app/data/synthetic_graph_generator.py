"""
Generates random weighted graphs of configurable size for controlled,
reproducible benchmarking (Day 1) and scalability testing (Day 3) —
independent of any network dependency on OSM.

Nodes are scattered in a square area; each node connects to its k nearest
neighbors (roads), with edge distance = Euclidean distance and base travel
time derived from an assumed average road speed. Congestion factors are
randomized per edge to simulate real-time traffic.
"""

from __future__ import annotations

import math
import random

import networkx as nx

from app.core.graph_model import TrafficGraph


def _euclidean(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.dist(a, b)


def generate_synthetic_graph(
    n_nodes: int = 30,
    k_nearest: int = 4,
    area_size_km: float = 50.0,
    avg_speed_kmh: float = 40.0,
    congestion_range: tuple[float, float] = (0.8, 2.5),
    directed: bool = True,
    seed: int | None = None,
) -> TrafficGraph:
    if n_nodes < 2:
        raise ValueError("n_nodes must be >= 2")

    rng = random.Random(seed)
    positions = {i: (rng.uniform(0, area_size_km), rng.uniform(0, area_size_km)) for i in range(n_nodes)}

    graph = TrafficGraph(directed=directed)
    for node_id, pos in positions.items():
        graph.add_node(node_id, pos=pos)

    def link(u: int, v: int) -> None:
        if graph.graph.has_edge(u, v):
            return
        distance_km = _euclidean(positions[u], positions[v])
        base_travel_time_min = (distance_km / avg_speed_kmh) * 60.0
        graph.add_edge(u, v, distance_km, base_travel_time_min, 1.0)

    node_ids = list(positions)
    for u in node_ids:
        neighbors = sorted(
            (v for v in node_ids if v != u),
            key=lambda v: _euclidean(positions[u], positions[v]),
        )[:k_nearest]
        for v in neighbors:
            link(u, v)
            if directed:
                link(v, u)

    _ensure_connected(graph, positions, avg_speed_kmh, directed, link)

    graph.randomize_congestion(*congestion_range, rng=rng)
    return graph


def _ensure_connected(
    graph: TrafficGraph,
    positions: dict[int, tuple[float, float]],
    avg_speed_kmh: float,
    directed: bool,
    link,
) -> None:
    """k-nearest-neighbor linking can leave disconnected components; stitch them
    together by connecting each extra component's closest node pair to the main one."""
    underlying = graph.graph.to_undirected() if directed else graph.graph
    components = list(nx.connected_components(underlying))
    if len(components) <= 1:
        return

    components.sort(key=len, reverse=True)
    main = components[0]
    for component in components[1:]:
        u, v, best = None, None, math.inf
        for a in main:
            for b in component:
                d = _euclidean(positions[a], positions[b])
                if d < best:
                    u, v, best = a, b, d
        link(u, v)
        if directed:
            link(v, u)
        main |= component
