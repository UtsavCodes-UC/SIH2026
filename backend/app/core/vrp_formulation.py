"""
Mathematical formulation of the routing problem (Day 1 deliverable #2).

MVP scope: single-vehicle route that starts and ends at a depot and visits a
given set of stops exactly once (a Traveling-Salesman-style tour over
shortest-path leg costs) — the base case of the VRP. Multi-vehicle splitting
and time windows are noted as extensions below; capacity is implemented now
as a soft constraint since it costs almost nothing given a single route.

Decision variable (conceptually): a permutation pi of `stops`, defining the
visiting order. QPSO/PSO/GA all optimize over this permutation via different
encodings; exact baselines (Day 1 baselines/) solve the same objective exactly.

Objective (minimize):
    total_time(pi) = sum of shortest_path_time(route[i], route[i+1])
                      for route = [depot, pi(1), ..., pi(k), depot]

Constraints:
    - every stop visited exactly once            -> guaranteed by permutation encoding
    - vehicle capacity: sum(demand[s] for s in stops) <= vehicle_capacity
                                                   -> enforced as a penalty term (soft constraint)

Extensions (not implemented in this MVP, left as clearly-marked hooks):
    - time windows [earliest_i, latest_i] per stop -> would add a penalty term
      based on cumulative arrival time, computed alongside total_time above
    - multiple vehicles / route splitting          -> would partition `stops`
      into several RouteRequest sub-problems, one per vehicle
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from app.core.graph_model import TrafficGraph


@dataclass
class RouteRequest:
    depot: object
    stops: list
    demands: dict | None = None
    vehicle_capacity: float | None = None


@dataclass
class RouteEvaluation:
    route: list
    total_time_min: float
    feasible: bool
    capacity_violation: float = 0.0


class RoutingProblem:
    """Binds a RouteRequest to a graph, precomputing the leg costs needed to
    score any candidate visiting order in O(k) instead of running shortest-path
    on every evaluation."""

    def __init__(self, graph: TrafficGraph, request: RouteRequest):
        if not request.stops:
            raise ValueError("RouteRequest.stops must be non-empty")
        self.graph = graph
        self.request = request
        nodes = [request.depot, *dict.fromkeys(request.stops)]
        self._leg_time = graph.all_pairs_shortest_time(nodes)

    def leg_time(self, u, v) -> float:
        return self._leg_time[u][v]

    def evaluate(self, stop_order: Sequence) -> RouteEvaluation:
        route = [self.request.depot, *stop_order, self.request.depot]
        total_time = sum(self.leg_time(route[i], route[i + 1]) for i in range(len(route) - 1))

        capacity_violation = 0.0
        if self.request.vehicle_capacity is not None and self.request.demands:
            load = sum(self.request.demands.get(s, 0) for s in stop_order)
            capacity_violation = max(0.0, load - self.request.vehicle_capacity)

        return RouteEvaluation(
            route=route,
            total_time_min=total_time,
            feasible=capacity_violation == 0.0,
            capacity_violation=capacity_violation,
        )

    def cost(self, stop_order: Sequence, penalty_weight: float = 1000.0) -> float:
        """Fitness value used by the metaheuristics: objective + penalty for
        constraint violations, so infeasible solutions are ranked worse but
        the search can still move through them (soft-constraint handling)."""
        evaluation = self.evaluate(stop_order)
        return evaluation.total_time_min + penalty_weight * evaluation.capacity_violation
