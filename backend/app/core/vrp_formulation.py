"""
Mathematical formulation of the routing problem (Day 1 deliverable #2).

Capacitated vehicle routing over a road network. A fleet of `n_vehicles`
identical vehicles of capacity Q starts and ends at a depot and must visit
every stop exactly once (n_vehicles = 1 is the plain single-vehicle tour).

Decision variable (conceptually): a permutation pi of `stops` -- the "giant
tour" -- which a greedy split decoder cuts into per-vehicle routes:

    walk pi in order; start the next vehicle when adding the next stop would
    exceed Q AND a vehicle is still unused; the last vehicle takes everything
    that remains (any excess over Q is a capacity violation).

QPSO / PSO / GA all optimize over pi (via different encodings); the decoder is
shared, so the comparison between them is like-for-like.

Objective (minimize):
    total_time(pi) = sum over vehicles of the shortest-path travel time along
                     [depot, s_1, ..., s_k, depot]   (weights include live congestion)
                   + penalty * capacity_violation(pi)

Constraints:
    - every stop visited exactly once      -> guaranteed by the permutation encoding
    - at most `n_vehicles` routes          -> guaranteed by the decoder
    - vehicle capacity: load(route) <= Q   -> soft constraint (penalty term); with a
      single vehicle the load is the same for every ordering, so the penalty is a constant

Not modeled yet: time windows [earliest_i, latest_i] per stop -- would add a
penalty term from cumulative arrival times computed alongside total_time.

Route representation used everywhere downstream: a FLAT, depot-delimited list,
e.g. [0, a, b, 0, c, d, 0] for two vehicles. For one vehicle it is exactly the
old [depot, ..., depot]. `split_at_depot` recovers the per-vehicle routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.graph_model import TrafficGraph


class UnreachableStopError(ValueError):
    """A stop cannot be reached from the depot (or the depot from the stop) on the directed graph."""


@dataclass
class RouteRequest:
    depot: object
    stops: list
    demands: dict | None = None
    vehicle_capacity: float | None = None
    n_vehicles: int = 1


@dataclass
class RouteEvaluation:
    routes: list[list]  # one [depot, ..., depot] list per vehicle actually used
    total_time_min: float
    feasible: bool
    capacity_violation: float = 0.0

    @property
    def route(self) -> list:
        """Flat depot-delimited route: [0, a, b, 0, c, d, 0]. Equals the single route for one vehicle."""
        flat = list(self.routes[0])
        for route in self.routes[1:]:
            flat.extend(route[1:])
        return flat


def split_at_depot(flat_route: Sequence, depot) -> list[list]:
    """Inverse of RouteEvaluation.route: cut a flat depot-delimited route into per-vehicle routes."""
    routes: list[list] = []
    current = [depot]
    for node in flat_route[1:]:
        current.append(node)
        if node == depot:
            routes.append(current)
            current = [depot]
    if len(current) > 1:  # tolerate a flat route that does not end at the depot
        current.append(depot)
        routes.append(current)
    return routes


class RoutingProblem:
    """Binds a RouteRequest to a graph, precomputing the leg costs needed to
    score any candidate visiting order in O(k) instead of running shortest-path
    on every evaluation."""

    def __init__(self, graph: TrafficGraph, request: RouteRequest):
        if not request.stops:
            raise ValueError("RouteRequest.stops must be non-empty")
        if request.n_vehicles < 1:
            raise ValueError("n_vehicles must be >= 1")
        if request.depot in request.stops:
            raise ValueError("the depot cannot also be a stop")
        if request.n_vehicles > 1 and (request.demands is None or request.vehicle_capacity is None):
            raise ValueError("a multi-vehicle request needs both `demands` and `vehicle_capacity`")

        self.graph = graph
        self.request = request
        nodes = [request.depot, *dict.fromkeys(request.stops)]
        self._leg_time = graph.all_pairs_shortest_time(nodes)
        self._check_reachable(nodes)

    def _check_reachable(self, nodes: list) -> None:
        for u in nodes:
            reachable = self._leg_time[u]
            for v in nodes:
                if u != v and v not in reachable:
                    raise UnreachableStopError(f"node {v!r} is not reachable from node {u!r} on the directed graph")

    def leg_time(self, u, v) -> float:
        return self._leg_time[u][v]

    @property
    def legs(self) -> dict:
        """The whole shortest-time table, legs[u][v] in minutes, for hot loops that can't afford a call per lookup."""
        return self._leg_time

    # ---- decoding -----------------------------------------------------------

    def split(self, stop_order: Sequence) -> list[list]:
        """Greedy giant-tour split into per-vehicle routes (see module docstring)."""
        depot = self.request.depot
        demands, capacity = self.request.demands, self.request.vehicle_capacity
        if demands is None or capacity is None or self.request.n_vehicles == 1:
            return [[depot, *stop_order, depot]]

        routes, current, load = [], [depot], 0.0
        for stop in stop_order:
            demand = demands.get(stop, 0)
            if load > 0 and load + demand > capacity and len(routes) < self.request.n_vehicles - 1:
                current.append(depot)
                routes.append(current)
                current, load = [depot], 0.0
            current.append(stop)
            load += demand
        current.append(depot)
        routes.append(current)
        return routes

    def route_loads(self, routes: list[list]) -> list[float]:
        demands = self.request.demands or {}
        depot = self.request.depot
        return [sum(demands.get(node, 0) for node in route if node != depot) for route in routes]

    # ---- scoring ------------------------------------------------------------

    def evaluate_routes(self, routes: list[list]) -> RouteEvaluation:
        total_time = sum(
            self.leg_time(route[i], route[i + 1]) for route in routes for i in range(len(route) - 1)
        )
        violation = 0.0
        capacity = self.request.vehicle_capacity
        if capacity is not None and self.request.demands is not None:
            violation = sum(max(0.0, load - capacity) for load in self.route_loads(routes))
        return RouteEvaluation(
            routes=routes,
            total_time_min=total_time,
            feasible=violation == 0.0,
            capacity_violation=violation,
        )

    def evaluate(self, stop_order: Sequence) -> RouteEvaluation:
        return self.evaluate_routes(self.split(stop_order))

    def cost(self, stop_order: Sequence, penalty_weight: float = 1000.0) -> float:
        """Fitness used by the metaheuristics: objective + penalty for constraint
        violations, so infeasible solutions are ranked worse but the search can
        still move through them (soft-constraint handling).

        A single allocation-free pass equal to evaluate(stop_order) -- it runs
        tens of thousands of times per solve, so it doesn't build route lists.
        """
        leg, depot = self._leg_time, self.request.depot
        demands, capacity = self.request.demands, self.request.vehicle_capacity
        track_load = demands is not None and capacity is not None
        max_routes = self.request.n_vehicles

        total_time = load = violation = 0.0
        last, routes_closed = depot, 0
        for stop in stop_order:
            if track_load:
                demand = demands.get(stop, 0)
                if load > 0 and load + demand > capacity and routes_closed < max_routes - 1:
                    total_time += leg[last][depot]
                    violation += max(0.0, load - capacity)
                    last, load, routes_closed = depot, 0.0, routes_closed + 1
                load += demand
            total_time += leg[last][stop]
            last = stop
        total_time += leg[last][depot]
        if track_load:
            violation += max(0.0, load - capacity)
        return total_time + penalty_weight * violation
