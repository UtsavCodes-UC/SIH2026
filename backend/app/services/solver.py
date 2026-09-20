"""Runs one of the routing algorithms on a resolved request (and optionally polishes the result)."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.baselines.classical_pso import ClassicalPSO
from app.core.baselines.dijkstra_baseline import nearest_neighbor
from app.core.baselines.genetic_algorithm import GeneticAlgorithm
from app.core.graph_model import TrafficGraph
from app.core.local_search import polish_result
from app.core.qpso import QPSO
from app.core.route_search import solve_with_search
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem


@dataclass
class Solution:
    problem: RoutingProblem
    raw: OptimizationResult  # the algorithm's own output
    final: OptimizationResult  # after the optional route polish (the same object as `raw` if not polished)

    @property
    def polished(self) -> bool:
        return self.final is not self.raw


def solve(
    graph: TrafficGraph,
    request: RouteRequest,
    algorithm: str,
    n_particles: int,
    n_iterations: int,
    seed: int | None,
    polish: bool,
    penalty_weight: float = 1000.0,
    warm_start: bool = False,
    time_limit_sec: float = 10.0,
) -> Solution:
    problem = RoutingProblem(graph, request)  # validates reachability up front

    if algorithm == "qpso":
        raw = QPSO(graph, request, n_particles=n_particles, n_iterations=n_iterations, penalty_weight=penalty_weight, warm_start=warm_start, seed=seed).run()
    elif algorithm == "pso":
        raw = ClassicalPSO(graph, request, n_particles=n_particles, n_iterations=n_iterations, penalty_weight=penalty_weight, warm_start=warm_start, seed=seed).run()
    elif algorithm == "ga":
        raw = GeneticAlgorithm(graph, request, population_size=n_particles, n_generations=n_iterations, penalty_weight=penalty_weight, warm_start=warm_start, seed=seed).run()
    elif algorithm == "nearest_neighbor":
        raw = nearest_neighbor(graph, request)
    elif algorithm == "route_search":
        # a search over whole route sets that starts from nearest neighbour: it is its own polish, and it uses no swarm
        raw = solve_with_search(problem, penalty_weight=penalty_weight, time_limit_sec=time_limit_sec, seed=seed)
    else:
        raise ValueError(f"unknown algorithm {algorithm!r}")

    final = polish_result(problem, raw, penalty_weight, inter_route=True) if polish and algorithm != "route_search" else raw
    return Solution(problem=problem, raw=raw, final=final)
