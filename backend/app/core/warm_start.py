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
from app.core.local_search import two_opt
from app.core.vrp_formulation import RoutingProblem


def heuristic_seed_orders(problem: RoutingProblem) -> list[list]:
    """Stop orders to seed a swarm with, best last-resort first: [nearest neighbour, nearest neighbour + 2-opt]."""
    depot = problem.request.depot
    nearest = nearest_neighbor_order(problem)
    polished: list = []
    for route in problem.split(nearest):
        polished.extend(two_opt(route[1:-1], problem.leg_time, depot))
    return [nearest, polished]
