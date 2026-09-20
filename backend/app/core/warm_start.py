"""
Warm start: put a cheap, good solution into the swarm before the search begins.

A swarm normally starts from random visiting orders. At 100 customers that is hopeless within a normal
budget: 100 numbers to get right, and plain nearest-neighbour routing beats a random-start QPSO or PSO by
30-45% (docs/BENCHMARKS.md, Finding 10). Warm start is the standard remedy: two particles begin as

    1. the nearest-neighbour solution, and
    2. the same solution after a 2-opt polish of each vehicle's route,

and the rest stay random for diversity. The search then improves on a good solution instead of
rediscovering one. Both QPSO and PSO take the same seeds, so a comparison between them stays fair.

Both seeds decode back to exactly these routes: nearest-neighbour closes a vehicle only when no remaining
stop fits, so the first stop of the next route would not have fitted in this one, which is where the
greedy split (`RoutingProblem.split`) cuts too. 2-opt only reorders inside a route, so its loads (and
therefore the cuts) are unchanged.
"""

from __future__ import annotations

from app.core.baselines.dijkstra_baseline import nearest_neighbor_order
from app.core.local_search import two_opt_order
from app.core.vrp_formulation import RoutingProblem


WINDOW_AWARE_SEED = True  # experiments switch this off to measure what the window-aware seed is worth


def window_aware_order(problem: RoutingProblem) -> list:
    """Nearest neighbour by TIME instead of distance, for problems with time windows.

    From the current position and clock, go next to the stop whose service could begin soonest (a van that arrives before
    a window opens waits, so an early-arriving stop is not automatically the best one), with lateness counted at the
    problem's penalty so a stop that can still be made on time is preferred to one that cannot. Vans are filled and closed
    exactly as `nearest_neighbor_order` does, so the order decodes back into these routes with `problem.split`.
    """
    request = problem.request
    windows, minutes = request.time_windows, problem.minutes
    remaining = list(dict.fromkeys(request.stops))
    order: list = []
    current, clock = request.depot, 0.0
    load, vehicles_used = 0.0, 1

    while remaining:
        candidates = remaining
        if request.n_vehicles > 1 and vehicles_used < request.n_vehicles:
            fitting = [s for s in remaining if load + request.demands.get(s, 0) <= request.vehicle_capacity]
            if fitting:
                candidates = fitting
            elif load > 0:  # nothing else fits: this van goes home, the next one starts at the depot at time 0
                current, clock, load, vehicles_used = request.depot, 0.0, 0.0, vehicles_used + 1

        def start_and_late(stop):
            arrival = clock + minutes[current][stop]
            window = windows.get(stop)
            if window is None:
                return arrival, 0.0
            return max(arrival, window.earliest), max(0.0, arrival - window.latest)

        def score(stop):
            start, late = start_and_late(stop)
            return start + request.time_window_penalty * late

        chosen = min(candidates, key=score)
        start, _ = start_and_late(chosen)
        order.append(chosen)
        remaining.remove(chosen)
        current, clock = chosen, start + request.service_time_min
        if request.n_vehicles > 1:
            load += request.demands.get(chosen, 0)
    return order


def heuristic_seed_orders(problem: RoutingProblem) -> list[list]:
    """Stop orders to seed a swarm with, best last-resort first: [nearest neighbour, nearest neighbour + 2-opt], and with
    time windows a third, the window-aware nearest neighbour (2-opt would undo what the windows require, so it is not
    applied to that one)."""
    nearest = nearest_neighbor_order(problem)
    seeds = [nearest, two_opt_order(problem, nearest)]
    if problem.has_time_windows and WINDOW_AWARE_SEED:
        seeds.append(window_aware_order(problem))
    return seeds
