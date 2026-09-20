"""
Weighted transportation network model (Day 1 deliverable #1).

Wraps a NetworkX (Di)Graph where:
- nodes  = intersections / depots
- edges  = roads, each carrying {distance_km, base_travel_time_min, congestion_factor}
- edge "weight" (what routing/shortest-path calls optimize) = base_travel_time_min * congestion_factor,
  recomputable at any time to simulate dynamic/real-time traffic conditions.
"""

from __future__ import annotations

import random
from typing import Iterable

import networkx as nx


class TrafficGraph:
    def __init__(self, directed: bool = True):
        self._g: nx.Graph = nx.DiGraph() if directed else nx.Graph()

    @property
    def graph(self) -> nx.Graph:
        """The underlying networkx graph, for anything not exposed here (plotting, algorithms, etc.)."""
        return self._g

    @property
    def directed(self) -> bool:
        return self._g.is_directed()

    def __len__(self) -> int:
        return self._g.number_of_nodes()

    @property
    def node_count(self) -> int:
        return self._g.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._g.number_of_edges()

    # ---- construction -----------------------------------------------------

    def add_node(self, node_id, **attrs) -> None:
        self._g.add_node(node_id, **attrs)

    def add_edge(
        self,
        u,
        v,
        distance_km: float,
        base_travel_time_min: float,
        congestion_factor: float = 1.0,
    ) -> None:
        if distance_km < 0 or base_travel_time_min < 0:
            raise ValueError("distance_km and base_travel_time_min must be non-negative")
        if congestion_factor <= 0:
            raise ValueError("congestion_factor must be > 0")
        self._g.add_edge(
            u,
            v,
            distance_km=distance_km,
            base_travel_time_min=base_travel_time_min,
            congestion_factor=congestion_factor,
            weight=base_travel_time_min * congestion_factor,
        )

    @classmethod
    def from_edge_list(cls, edges: Iterable[tuple], directed: bool = True) -> "TrafficGraph":
        """edges: iterable of (u, v, distance_km, base_travel_time_min[, congestion_factor])."""
        g = cls(directed=directed)
        for edge in edges:
            u, v, distance_km, base_travel_time_min, *rest = edge
            congestion_factor = rest[0] if rest else 1.0
            g.add_edge(u, v, distance_km, base_travel_time_min, congestion_factor)
        return g

    # ---- dynamic weights ----------------------------------------------------

    def travel_time(self, u, v) -> float:
        """Current weighted travel time for edge (u, v)."""
        data = self._g[u][v]
        return data["base_travel_time_min"] * data["congestion_factor"]

    def update_congestion(self, u, v, congestion_factor: float) -> None:
        if congestion_factor <= 0:
            raise ValueError("congestion_factor must be > 0")
        data = self._g[u][v]
        data["congestion_factor"] = congestion_factor
        data["weight"] = data["base_travel_time_min"] * congestion_factor

    def randomize_congestion(self, low: float = 0.8, high: float = 2.5, rng: random.Random | None = None) -> None:
        """Simulate real-time traffic conditions by re-rolling every edge's congestion factor."""
        rng = rng or random
        for u, v in list(self._g.edges()):
            self.update_congestion(u, v, rng.uniform(low, high))

    def refresh_weights(self) -> None:
        """Recompute the 'weight' attribute on every edge from base_travel_time_min * congestion_factor."""
        for _, _, data in self._g.edges(data=True):
            data["weight"] = data["base_travel_time_min"] * data["congestion_factor"]

    # ---- routing queries ----------------------------------------------------

    def shortest_path(self, source, target, weights=None) -> list:
        """Quickest path; or, given `CostWeights`, the cheapest path under that blend of time, distance and congestion."""
        if weights is None or weights.is_default:
            return nx.shortest_path(self._g, source, target, weight="weight")
        return nx.shortest_path(self._g, source, target, weight=lambda u, v, edge: weights.arc_cost(edge))

    def mutually_reachable(self, node) -> set:
        """The nodes a vehicle can drive to from `node` and get back from (`node` included). Stops outside this set
        cannot be part of a tour that starts and ends at `node`; roads closed in the app are what usually cut them off."""
        g = self._g
        if not g.is_directed():
            return nx.node_connected_component(g, node)
        return (nx.descendants(g, node) & nx.ancestors(g, node)) | {node}

    def shortest_path_time(self, source, target) -> float:
        return nx.shortest_path_length(self._g, source, target, weight="weight")

    def all_pairs_shortest_time(self, nodes: Iterable) -> dict[object, dict[object, float]]:
        """Single-source Dijkstra from each node in `nodes`, restricted to those nodes as sources.

        Used by vrp_formulation.RoutingProblem to get leg costs between an arbitrary
        set of stops without materializing full all-pairs shortest paths for the whole graph.
        """
        result: dict[object, dict[object, float]] = {}
        for n in nodes:
            result[n] = nx.single_source_dijkstra_path_length(self._g, n, weight="weight")
        return result

    def all_pairs_shortest_cost(self, nodes: Iterable, weights) -> dict[object, dict[object, float]]:
        """Like `all_pairs_shortest_time`, but the cost of an arc is the blend of time, distance and congestion in
        `weights` (see core/cost_model.py). With the default weights it is exactly `all_pairs_shortest_time`."""
        if weights.is_default:
            return self.all_pairs_shortest_time(nodes)
        arc_cost = lambda u, v, edge: weights.arc_cost(edge)  # noqa: E731
        return {n: nx.single_source_dijkstra_path_length(self._g, n, weight=arc_cost) for n in nodes}

    def all_pairs_path_minutes(self, nodes: Iterable, weights) -> dict[object, dict[object, float]]:
        """Real driving minutes (congestion included) along the cheapest path between every pair of `nodes`, the path
        being the one `all_pairs_shortest_cost(nodes, weights)` prices. Needed when a clock has to run in minutes while
        the cost blends in distance or congestion (time windows, core/time_windows.py)."""
        nodes = list(nodes)
        wanted = set(nodes)
        arc_cost = lambda u, v, edge: weights.arc_cost(edge)  # noqa: E731
        g = self._g
        result: dict[object, dict[object, float]] = {}
        for source in nodes:
            _, paths = nx.single_source_dijkstra(g, source, weight=arc_cost)
            row = {}
            for target in wanted:
                path = paths.get(target)
                if path is not None:
                    row[target] = sum(g[a][b]["base_travel_time_min"] * g[a][b]["congestion_factor"] for a, b in zip(path, path[1:]))
            result[source] = row
        return result

    # ---- serialization (Day 2: API request/response payloads) --------------

    def to_dict(self) -> dict:
        return {
            "directed": self.directed,
            "nodes": [{"id": n, **attrs} for n, attrs in self._g.nodes(data=True)],
            "edges": [
                {
                    "u": u,
                    "v": v,
                    "distance_km": data["distance_km"],
                    "base_travel_time_min": data["base_travel_time_min"],
                    "congestion_factor": data["congestion_factor"],
                }
                for u, v, data in self._g.edges(data=True)
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "TrafficGraph":
        g = cls(directed=payload.get("directed", True))
        for node in payload["nodes"]:
            node_id = node["id"]
            attrs = {k: v for k, v in node.items() if k != "id"}
            g.add_node(node_id, **attrs)
        for edge in payload["edges"]:
            g.add_edge(
                edge["u"],
                edge["v"],
                edge["distance_km"],
                edge["base_travel_time_min"],
                edge.get("congestion_factor", 1.0),
            )
        return g
