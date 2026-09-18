"""
Exact ground-truth baseline via Held-Karp dynamic programming over subsets
(the standard exact algorithm for a depot-anchored TSP tour): O(2^n * n^2)
time/space instead of the O(n!) of brute force. Practical up to roughly
n <= 15-16 stops -- past that, use the OR-Tools wrapper in exact_ortools.py
(near-exact, scales further) instead.

    dp[S][j] = min cost of a path that starts at the depot, visits exactly
               the stops in subset S, and ends at stop j
    dp[{j}][j] = leg_time(depot, j)
    dp[S][j]   = min over k in S-{j} of dp[S-{j}][k] + leg_time(k, j)

The optimal tour cost is min over j of dp[full_set][j] + leg_time(j, depot).
"""

from __future__ import annotations

import time

from app.core.graph_model import TrafficGraph
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem

MAX_STOPS_FOR_EXACT = 16


def held_karp(graph: TrafficGraph, request: RouteRequest) -> OptimizationResult:
    start = time.perf_counter()
    problem = RoutingProblem(graph, request)

    stops = list(dict.fromkeys(request.stops))
    n = len(stops)
    if n > MAX_STOPS_FOR_EXACT:
        raise ValueError(
            f"held_karp is exact but exponential; {n} stops exceeds the "
            f"MAX_STOPS_FOR_EXACT={MAX_STOPS_FOR_EXACT} safety limit. "
            "Use exact_ortools for larger instances."
        )

    depot = request.depot
    leg = lambda a, b: problem.leg_time(a, b)  # noqa: E731

    # dp[(mask, j)] = (cost, predecessor) — mask is the bitset of visited stop indices, tour ends at stop j
    dp: dict[tuple[int, int], tuple[float, int | None]] = {}
    for j in range(n):
        dp[(1 << j, j)] = (leg(depot, stops[j]), None)

    for mask in range(1, 1 << n):
        for j in range(n):
            if not (mask & (1 << j)):
                continue
            if (mask, j) not in dp:
                continue
            cost_j, _ = dp[(mask, j)]
            for k in range(n):
                if mask & (1 << k):
                    continue
                new_mask = mask | (1 << k)
                new_cost = cost_j + leg(stops[j], stops[k])
                if (new_mask, k) not in dp or new_cost < dp[(new_mask, k)][0]:
                    dp[(new_mask, k)] = (new_cost, j)

    full_mask = (1 << n) - 1
    best_last, best_cost = None, float("inf")
    for j in range(n):
        if (full_mask, j) not in dp:
            continue
        total = dp[(full_mask, j)][0] + leg(stops[j], depot)
        if total < best_cost:
            best_cost = total
            best_last = j

    # reconstruct order by walking predecessors back from (full_mask, best_last)
    order_idx: list[int] = []
    mask, j = full_mask, best_last
    while j is not None:
        order_idx.append(j)
        _, prev = dp[(mask, j)]
        mask &= ~(1 << j)
        j = prev
    order_idx.reverse()
    stop_order = [stops[i] for i in order_idx]

    evaluation = problem.evaluate(stop_order)
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
