"""
Exact optimum of a small capacitated routing problem, to measure the heuristics against (docs/BENCHMARKS.md, Finding 20).

The objective is the one every solver in the app minimizes: the driving cost of all routes plus `penalty_weight` per unit of
capacity overload, with at most `n_vehicles` routes (the cost weights of the request are respected, since the legs come from
the problem). Three steps, all exact:

1. Held-Karp over subsets:   dp[S][j] = cheapest path depot -> (all stops of S) -> ending at j.
2. Cost of serving S with one vehicle:   cost[S] = min_j (dp[S][j] + leg(j, depot)) + penalty * max(0, load(S) - capacity).
3. Best way to split the stops into at most n_vehicles such subsets:   f_k[M] = min over S containing the lowest stop of M of
   cost[S] + f_{k-1}[M without S]   (the lowest stop is put in a block first so each partition is counted once).

Time and memory are exponential: O(2^n n^2) for step 1 and about n_vehicles * 3^n / 2 for step 3, so it is meant for up to
about 14-15 stops (a few seconds). With one vehicle it is plain Held-Karp and can go to 16 stops. Not supported: time windows
(a route's cost would depend on when it starts).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.core.vrp_formulation import RoutingProblem

MAX_STOPS = 16
MAX_STOPS_WITH_SEVERAL_VEHICLES = 15


@dataclass
class ExactSolution:
    cost: float  # driving cost + penalty_weight * overload, the same quantity as RoutingProblem.penalized_cost
    routes: list[list]  # depot-delimited, one per vehicle used
    runtime_sec: float


def _submasks(avail: int, cache: dict[int, np.ndarray]) -> np.ndarray:
    """Every subset of the bitmask `avail` (the empty one included) as an array of bitmasks."""
    found = cache.get(avail)
    if found is None:
        bits = [b for b in range(avail.bit_length()) if avail >> b & 1]
        index = np.arange(1 << len(bits), dtype=np.int64)
        found = np.zeros_like(index)
        for position, bit in enumerate(bits):
            found |= ((index >> position) & 1) << bit
        cache[avail] = found
    return found


def exact_solve(problem: RoutingProblem, penalty_weight: float = 1000.0) -> ExactSolution:
    started = time.perf_counter()
    request = problem.request
    if problem.has_time_windows:
        raise ValueError("the exact solver does not model time windows: with windows a route's cost depends on when it starts")
    stops = list(dict.fromkeys(request.stops))
    n, fleet = len(stops), request.n_vehicles
    limit = MAX_STOPS if fleet == 1 else MAX_STOPS_WITH_SEVERAL_VEHICLES
    if n > limit:
        raise ValueError(f"the exact solver is exponential; {n} stops is over its limit of {limit} for {fleet} vehicle(s)")
    depot, leg = request.depot, problem.legs

    to_stop = np.array([leg[depot][s] for s in stops])
    from_stop = np.array([leg[s][depot] for s in stops])
    between = np.array([[0.0 if a == b else leg[a][b] for b in stops] for a in stops])
    size, bit = 1 << n, 1 << np.arange(n)

    # 1. Held-Karp over subsets
    dp = np.full((size, n), np.inf)
    dp[bit, np.arange(n)] = to_stop
    for mask in range(1, size):
        reach = (dp[mask][:, None] + between).min(axis=0)  # cheapest way to end at each stop k after visiting `mask`
        free = (mask & bit) == 0
        if free.any():
            target, k = mask | bit[free], np.nonzero(free)[0]
            dp[target, k] = np.minimum(dp[target, k], reach[free])

    # 2. the cost of serving each subset with one vehicle
    route_cost = (dp + from_stop).min(axis=1)
    route_cost[0] = 0.0
    load = np.zeros(size)
    if request.demands is not None and request.vehicle_capacity is not None:
        for j, stop in enumerate(stops):
            load[1 << j : 2 << j] = load[: 1 << j] + request.demands.get(stop, 0)
        cost = route_cost + penalty_weight * np.maximum(0.0, load - request.vehicle_capacity)
    else:
        cost = route_cost

    # 3. the best split into at most `fleet` subsets
    full = size - 1
    best = np.full(size, np.inf)
    best[0] = 0.0
    choices: list[np.ndarray] = []
    cache: dict[int, np.ndarray] = {}
    for _ in range(fleet):
        current, choice = best.copy(), np.full(size, -1, dtype=np.int64)  # inherits "one vehicle fewer" unless improved
        for sub in range(1, size):
            lowest = sub & -sub
            rest = _submasks(full & ~sub & ~((lowest << 1) - 1), cache)  # what the other vehicles serve: only stops above the lowest of `sub`
            candidate = cost[sub] + best[rest]
            masks = sub | rest
            better = candidate < current[masks]
            if better.any():
                current[masks[better]] = candidate[better]
                choice[masks[better]] = sub
        best = current
        choices.append(choice)

    # rebuild the routes
    routes, mask, layer = [], full, fleet
    while mask:
        sub = int(choices[layer - 1][mask])
        layer -= 1
        if sub == -1:
            continue
        routes.append([depot, *[stops[j] for j in _best_order(dp, between, from_stop, sub)], depot])
        mask ^= sub
    return ExactSolution(cost=float(best[full]), routes=routes, runtime_sec=time.perf_counter() - started)


def _best_order(dp: np.ndarray, between: np.ndarray, from_stop: np.ndarray, mask: int) -> list[int]:
    """The visiting order (stop indices) behind dp[mask]'s best tour, found by walking back through the table."""
    j = int(np.argmin(dp[mask] + from_stop))
    order = [j]
    while mask & (mask - 1):  # more than one stop left
        previous = mask ^ (1 << j)
        candidates = dp[previous] + between[:, j]
        candidates[[k for k in range(len(candidates)) if not previous >> k & 1]] = np.inf
        j, mask = int(np.argmin(candidates)), previous
        order.append(j)
    return order[::-1]
