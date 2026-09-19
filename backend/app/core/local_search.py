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
) -> OptimizationResult:
    """Run 2-opt on each of `result`'s vehicle routes and return a new
    OptimizationResult with the polished routes/cost. Each route is polished
    on its own, so the stops-per-vehicle assignment (and thus every load) is
    unchanged. Runtime of the polish pass is added to the reported runtime;
    the polished cost is appended to convergence_history so it's visible as
    one extra point on a convergence chart."""
    start = time.perf_counter()

    depot = problem.request.depot
    polished_routes = [
        [depot, *two_opt(route[1:-1], problem.leg_time, depot), depot]
        for route in split_at_depot(result.best_route, depot)
    ]

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
