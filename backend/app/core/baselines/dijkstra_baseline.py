"""
Nearest-neighbor baseline: the classical, non-metaheuristic way to turn
shortest-path costs (Dijkstra, via TrafficGraph/RoutingProblem) into a route.

At each step, go to the closest not-yet-visited stop (by shortest-path travel
time from the current position); return to the depot at the end. Deterministic,
O(n^2), no tuning knobs -- the "cheap heuristic" reference point that QPSO/PSO/GA
are expected to beat, and that the exact solver's optimality gap is measured against.

With several vehicles it is capacity-aware: the vehicle only considers stops that
still fit; when none do, it returns to the depot and the next vehicle starts
there. The last vehicle takes whatever remains. The resulting order decodes
(RoutingProblem.split) back into exactly these routes.
"""

from __future__ import annotations

import time

from app.core.graph_model import TrafficGraph
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem


def nearest_neighbor_order(problem: RoutingProblem) -> list:
    """The stops in nearest-neighbour visiting order (routes decode back out of it with `problem.split`)."""
    request = problem.request
    remaining = list(dict.fromkeys(request.stops))
    order: list = []
    current = request.depot
    load, vehicles_used = 0.0, 1

    while remaining:
        candidates = remaining
        if request.n_vehicles > 1 and vehicles_used < request.n_vehicles:
            fitting = [s for s in remaining if load + request.demands.get(s, 0) <= request.vehicle_capacity]
            if fitting:
                candidates = fitting
            elif load > 0:  # nothing else fits: send this vehicle home, the next one starts at the depot
                current, load, vehicles_used = request.depot, 0.0, vehicles_used + 1

        next_stop = min(candidates, key=lambda s: problem.leg_time(current, s))
        order.append(next_stop)
        remaining.remove(next_stop)
        current = next_stop
        if request.n_vehicles > 1:
            load += request.demands.get(next_stop, 0)
    return order


def nearest_neighbor(graph: TrafficGraph, request: RouteRequest) -> OptimizationResult:
    start = time.perf_counter()
    problem = RoutingProblem(graph, request)
    order = nearest_neighbor_order(problem)

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
