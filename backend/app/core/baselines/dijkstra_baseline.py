"""
Nearest-neighbor baseline: the classical, non-metaheuristic way to turn
shortest-path costs (Dijkstra, via TrafficGraph/RoutingProblem) into a route.

At each step, go to the closest not-yet-visited stop (by shortest-path travel
time from the current position); return to the depot at the end. Deterministic,
O(n^2), no tuning knobs -- the "cheap heuristic" reference point that QPSO/PSO/GA
are expected to beat, and that the exact solver's optimality gap is measured against.
"""

from __future__ import annotations

import time

from app.core.graph_model import TrafficGraph
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem


def nearest_neighbor(graph: TrafficGraph, request: RouteRequest) -> OptimizationResult:
    start = time.perf_counter()
    problem = RoutingProblem(graph, request)

    remaining = list(dict.fromkeys(request.stops))
    order: list = []
    current = request.depot

    while remaining:
        next_stop = min(remaining, key=lambda s: problem.leg_time(current, s))
        order.append(next_stop)
        remaining.remove(next_stop)
        current = next_stop

    evaluation = problem.evaluate(order)
    cost = evaluation.total_time_min + 1000.0 * evaluation.capacity_violation
    runtime_sec = time.perf_counter() - start

    return OptimizationResult(
        best_route=evaluation.route,
        best_cost=cost,
        convergence_history=[cost],
        runtime_sec=runtime_sec,
        iterations=1,
        n_particles=1,
    )
