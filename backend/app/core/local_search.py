"""
2-opt local search: given a visiting order, repeatedly reverses whichever
contiguous segment most shortens the tour, until no single reversal helps
(a local optimum). Applied as a cheap "polish" step after any
construction/metaheuristic algorithm -- O(n^2) per pass, and very effective
at removing the crossing-edge inefficiencies that random-key/permutation
search leaves behind.

Applying it uniformly to every algorithm's output (see benchmark.py) keeps
the comparison fair: the question becomes "whose *starting point* leads to
a better local optimum", not "which algorithm forgot to clean up after itself".

`improve_routes` is the stronger, multi-vehicle polish: besides 2-opt inside each route it moves
runs of stops from one vehicle to another and swaps stops between vehicles, whenever that lowers
travel time plus the overload penalty. It is what the app applies by default (docs/BENCHMARKS.md,
Finding 10: 10-18% lower cost than 2-opt alone on nearest-neighbour routes, in well under a second).

`refine_positions_with_two_opt` + `encode_order` additionally support a
*memetic* variant: polishing each particle's personal-best mid-search
(QPSO/ClassicalPSO's `memetic_interval` parameter), not just the final
answer. For QPSO specifically this improves two things at once -- the
per-particle attractor AND the swarm-wide `mbest` (the mean of all
personal bests) -- since `mbest` has no equivalent in classical PSO, this
is the one place a shared technique can have a structurally different
payoff for QPSO than for PSO. See docs/BENCHMARKS.md for the ablation.
"""

from __future__ import annotations

import time
from typing import Callable, Sequence

import numpy as np

from app.core.types import OptimizationResult
from app.core.vrp_formulation import RoutingProblem, split_at_depot


def two_opt(order: Sequence, leg_time: Callable[[object, object], float], depot, max_passes: int = 100) -> list:
    """Reverse route segments until no single reversal shortens the tour.

    Leg costs are NOT assumed symmetric: our graphs are directed with an
    independent congestion factor per direction, so reversing a segment also
    changes the direction every internal leg is driven in. The textbook 2-opt
    delta ignores that and, on asymmetric costs, accepted "improving" moves that
    lengthened the tour (up to +46% in a random test). Forward and reverse
    prefix sums give the exact cost of a reversal in O(1); they are rebuilt only
    after a move is accepted.
    """
    route = [depot, *order, depot]
    n = len(route)

    def prefix_sums() -> tuple[list[float], list[float]]:
        forward, reverse = [0.0] * n, [0.0] * n
        for k in range(n - 1):
            forward[k + 1] = forward[k] + leg_time(route[k], route[k + 1])
            reverse[k + 1] = reverse[k] + leg_time(route[k + 1], route[k])
        return forward, reverse

    forward, reverse = prefix_sums()
    improved = True
    passes = 0

    while improved and passes < max_passes:
        improved = False
        passes += 1
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                a, b, c, d = route[i - 1], route[i], route[j], route[j + 1]
                delta = (
                    leg_time(a, c) + (reverse[j] - reverse[i]) + leg_time(b, d)
                    - leg_time(a, b) - (forward[j] - forward[i]) - leg_time(c, d)
                )
                if delta < -1e-9:
                    route[i : j + 1] = reversed(route[i : j + 1])
                    forward, reverse = prefix_sums()
                    improved = True

    return route[1:-1]


def polish_result(
    problem: RoutingProblem,
    result: OptimizationResult,
    penalty_weight: float = 1000.0,
    inter_route: bool = False,
) -> OptimizationResult:
    """Polish `result` and return a new OptimizationResult with the polished routes/cost.

    By default this runs 2-opt on each vehicle's route on its own, so the stops-per-vehicle assignment
    (and thus every load) is unchanged. With `inter_route=True` it runs `improve_routes` instead, which
    also moves stops between vehicles. Runtime of the polish is added to the reported runtime; the
    polished cost is appended to convergence_history so it's visible as one extra point on a chart."""
    start = time.perf_counter()

    depot = problem.request.depot
    routes = split_at_depot(result.best_route, depot)
    if inter_route:
        polished_routes = improve_routes(problem, routes, penalty_weight)
    else:
        polished_routes = [[depot, *two_opt(route[1:-1], problem.leg_time, depot), depot] for route in routes]

    evaluation = problem.evaluate_routes(polished_routes)
    cost = evaluation.total_time_min + penalty_weight * evaluation.capacity_violation
    polish_runtime = time.perf_counter() - start

    return OptimizationResult(
        best_route=evaluation.route,
        best_cost=cost,
        convergence_history=[*result.convergence_history, cost],
        runtime_sec=result.runtime_sec + polish_runtime,
        iterations=result.iterations,
        n_particles=result.n_particles,
    )


def encode_order(order: Sequence, stops: list) -> np.ndarray:
    """Inverse of the random-key decode (argsort). Assigns each stop a rank-based
    position value so that argsort(result) reproduces `order` exactly -- the
    "smallest position value" re-encoding rule standard in random-key GA/PSO
    literature. Used to write a 2-opt-polished route back into a particle's
    continuous position vector.
    """
    n = len(stops)
    rank_of_stop = {stop: rank for rank, stop in enumerate(order)}
    positions = np.empty(n)
    for i, stop in enumerate(stops):
        positions[i] = (rank_of_stop[stop] + 0.5) / n
    return positions


def refine_positions_with_two_opt(
    positions: np.ndarray,
    stops: list,
    problem: RoutingProblem,
    penalty_weight: float = 1000.0,
    max_passes: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """Memetic refinement step: decode each row of `positions` (one particle
    each), 2-opt polish the resulting route, and re-encode the polished route
    back into a continuous position. `max_passes` is kept small since this
    typically runs on an entire population many times over a search, not once
    at the end -- see qpso.py / classical_pso.py's `memetic_interval`.

    Returns (new_positions, new_costs); 2-opt only ever accepts improving
    moves, so new_costs[i] <= original cost of positions[i] for every i.

    Single-vehicle only: a polished multi-vehicle route need not decode back to
    the same vehicle split, so writing it back into a particle isn't sound.
    """
    if problem.request.n_vehicles > 1:
        raise NotImplementedError("memetic refinement supports single-vehicle requests only")
    depot = problem.request.depot
    new_positions = positions.copy()
    costs = np.empty(len(positions))

    for idx, pos in enumerate(positions):
        order = [stops[i] for i in np.argsort(pos)]
        polished_order = two_opt(order, problem.leg_time, depot, max_passes=max_passes)

        evaluation = problem.evaluate(polished_order)
        costs[idx] = evaluation.total_time_min + penalty_weight * evaluation.capacity_violation
        new_positions[idx] = encode_order(polished_order, stops)

    return new_positions, costs


def improve_routes(
    problem: RoutingProblem,
    routes: Sequence[Sequence],
    penalty_weight: float = 1000.0,
    max_passes: int = 50,
) -> list[list]:
    """Local search across vehicles: the polish a route planner would apply to any solution.

    Repeats these steps until a whole round finds nothing better:

      1. 2-opt inside every route (`two_opt`);
      2. relocate: move a run of 1-3 consecutive stops from one vehicle's route into another's, at the
         best position;
      3. swap: exchange one stop of a route with one stop of another route.

    A move is accepted when it lowers  travel time + penalty_weight * capacity overload  (the same
    fitness the metaheuristics use), so an overloaded van can be relieved as well as a long trip
    shortened, and a feasible plan stays feasible. Every delta is exact for our directed, per-direction
    congested costs because none of these moves reverses a stretch of road; only its neighbours change.

    `routes` are [depot, ..., depot] lists; the result is the same shape. Vehicles are never added, and a
    vehicle whose stops all moved away is dropped from the result.
    """
    depot = problem.request.depot
    legs = problem.legs
    demands = problem.request.demands or {}
    capacity = problem.request.vehicle_capacity

    def excess(load: float) -> float:
        return max(0.0, load - capacity) if capacity is not None else 0.0

    plan = [list(r[1:-1]) if r and r[0] == depot else list(r) for r in routes]
    loads = [sum(demands.get(s, 0) for s in r) for r in plan]

    def neighbours(route: list, i: int, length: int = 1):
        before = route[i - 1] if i > 0 else depot
        after = route[i + length] if i + length < len(route) else depot
        return before, after

    for _ in range(max_passes):
        improved = False

        for a in range(len(plan)):
            plan[a] = two_opt(plan[a], problem.leg_time, depot)

        # relocate a run of 1-3 stops to the best place in another route
        for a in range(len(plan)):
            i = 0
            while i < len(plan[a]):
                moved = False
                for length in (1, 2, 3):
                    if i + length > len(plan[a]):
                        break
                    segment = plan[a][i : i + length]
                    seg_load = sum(demands.get(s, 0) for s in segment)
                    head, tail = segment[0], segment[-1]
                    p, nx = neighbours(plan[a], i, length)
                    saved = legs[p][head] + legs[tail][nx] - legs[p][nx]

                    best_delta, best_where = -1e-9, None
                    for b in range(len(plan)):
                        if b == a:
                            continue
                        overload_change = (
                            excess(loads[a] - seg_load) + excess(loads[b] + seg_load) - excess(loads[a]) - excess(loads[b])
                        )
                        target = plan[b]
                        for k in range(len(target) + 1):
                            u = target[k - 1] if k > 0 else depot
                            v = target[k] if k < len(target) else depot
                            delta = legs[u][head] + legs[tail][v] - legs[u][v] - saved + penalty_weight * overload_change
                            if delta < best_delta:
                                best_delta, best_where = delta, (b, k)
                    if best_where is not None:
                        b, k = best_where
                        del plan[a][i : i + length]
                        plan[b][k:k] = segment
                        loads[a] -= seg_load
                        loads[b] += seg_load
                        improved = moved = True
                        break
                if not moved:
                    i += 1

        # swap one stop of one route with one stop of another
        for a in range(len(plan)):
            for b in range(a + 1, len(plan)):
                for i in range(len(plan[a])):
                    for j in range(len(plan[b])):
                        x, y = plan[a][i], plan[b][j]
                        pa, na = neighbours(plan[a], i)
                        pb, nb = neighbours(plan[b], j)
                        dx, dy = demands.get(x, 0), demands.get(y, 0)
                        overload_change = (
                            excess(loads[a] - dx + dy) + excess(loads[b] - dy + dx) - excess(loads[a]) - excess(loads[b])
                        )
                        delta = (
                            legs[pa][y] + legs[y][na] - legs[pa][x] - legs[x][na]
                            + legs[pb][x] + legs[x][nb] - legs[pb][y] - legs[y][nb]
                            + penalty_weight * overload_change
                        )
                        if delta < -1e-9:
                            plan[a][i], plan[b][j] = y, x
                            loads[a] += dy - dx
                            loads[b] += dx - dy
                            improved = True

        if not improved:
            break

    return [[depot, *route, depot] for route in plan if route]
