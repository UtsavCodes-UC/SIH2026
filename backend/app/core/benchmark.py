"""
Benchmarking harness: runs QPSO against every baseline in
app/core/baselines/ on the same graph instance and collects:

    - solution quality (total cost) and optimality gap vs the exact
      (Held-Karp) baseline, when the instance is small enough to solve exactly
    - convergence curve (best cost per iteration/generation)
    - wall-clock runtime

`run_scalability_sweep` reruns this across synthetic graphs of increasing
size to show how solution quality and runtime scale (Day 3 deliverable);
the exact baseline is automatically dropped once instances exceed
MAX_STOPS_FOR_EXACT, since Held-Karp is exponential.

Output feeds:
    - scripts/run_benchmark.py (CLI comparison + convergence chart)
    - the /benchmark API endpoint + frontend charts (Day 2)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.baselines.classical_pso import ClassicalPSO
from app.core.baselines.dijkstra_baseline import nearest_neighbor
from app.core.baselines.exact_held_karp import MAX_STOPS_FOR_EXACT, held_karp
from app.core.baselines.genetic_algorithm import GeneticAlgorithm
from app.core.graph_model import TrafficGraph
from app.core.local_search import polish_result
from app.core.qpso import QPSO
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph


@dataclass
class BenchmarkConfig:
    n_particles: int = 40
    n_iterations: int = 800
    ga_population_size: int = 40
    ga_generations: int = 800
    penalty_weight: float = 1000.0
    seed: int | None = None
    include_exact: bool = True  # auto-skipped once stop count exceeds MAX_STOPS_FOR_EXACT
    polish_with_two_opt: bool = True  # applied uniformly to every non-exact algorithm, for a fair comparison


@dataclass
class AlgorithmBenchmark:
    name: str
    result: OptimizationResult
    raw_cost: float  # cost before 2-opt polish, so the polish step's own contribution is visible
    optimality_gap_pct: float | None  # None when no exact baseline is available for this instance


@dataclass
class BenchmarkReport:
    n_nodes: int
    n_stops: int
    exact_cost: float | None
    algorithms: list[AlgorithmBenchmark]

    def summary_table(self) -> str:
        header = f"{'algorithm':<18}{'raw cost':>12}{'polished':>12}{'gap %':>10}{'runtime (s)':>14}{'iterations':>12}"
        lines = [f"[{self.n_nodes} nodes, {self.n_stops} stops]", header, "-" * len(header)]
        for algo in self.algorithms:
            gap = f"{algo.optimality_gap_pct:.2f}" if algo.optimality_gap_pct is not None else "-"
            lines.append(
                f"{algo.name:<18}{algo.raw_cost:>12.2f}{algo.result.best_cost:>12.2f}{gap:>10}"
                f"{algo.result.runtime_sec:>14.4f}{algo.result.iterations:>12}"
            )
        return "\n".join(lines)


def run_benchmark(
    graph: TrafficGraph,
    request: RouteRequest,
    config: BenchmarkConfig | None = None,
) -> BenchmarkReport:
    config = config or BenchmarkConfig()
    n_stops = len(set(request.stops))

    runs: list[tuple[str, OptimizationResult]] = [
        ("nearest_neighbor", nearest_neighbor(graph, request)),
        (
            "classical_pso",
            ClassicalPSO(
                graph,
                request,
                n_particles=config.n_particles,
                n_iterations=config.n_iterations,
                penalty_weight=config.penalty_weight,
                seed=config.seed,
            ).run(),
        ),
        (
            "genetic_algorithm",
            GeneticAlgorithm(
                graph,
                request,
                population_size=config.ga_population_size,
                n_generations=config.ga_generations,
                penalty_weight=config.penalty_weight,
                seed=config.seed,
            ).run(),
        ),
        (
            "qpso",
            QPSO(
                graph,
                request,
                n_particles=config.n_particles,
                n_iterations=config.n_iterations,
                penalty_weight=config.penalty_weight,
                seed=config.seed,
            ).run(),
        ),
    ]

    exact_cost = None
    if config.include_exact and n_stops <= MAX_STOPS_FOR_EXACT:
        exact_result = held_karp(graph, request)
        exact_cost = exact_result.best_cost
        runs.append(("held_karp_exact", exact_result))

    problem = RoutingProblem(graph, request)
    algorithms = []
    for name, result in runs:
        raw_cost = result.best_cost
        if config.polish_with_two_opt and name != "held_karp_exact":
            result = polish_result(problem, result, config.penalty_weight)

        gap = None
        if exact_cost is not None and exact_cost > 0:
            gap = 100.0 * (result.best_cost - exact_cost) / exact_cost
        algorithms.append(AlgorithmBenchmark(name=name, result=result, raw_cost=raw_cost, optimality_gap_pct=gap))

    return BenchmarkReport(
        n_nodes=graph.node_count,
        n_stops=n_stops,
        exact_cost=exact_cost,
        algorithms=algorithms,
    )


def run_scalability_sweep(
    node_counts: list[int],
    n_stops_fraction: float = 0.3,
    config: BenchmarkConfig | None = None,
    seed: int | None = None,
) -> list[BenchmarkReport]:
    """Regenerate a synthetic graph at each size in `node_counts`, pick roughly
    `n_stops_fraction` of its nodes as stops, and benchmark all algorithms --
    showing how solution quality and runtime scale as the problem grows
    (Day 3 deliverable: "demonstrate scalability")."""
    reports = []
    for n_nodes in node_counts:
        graph = generate_synthetic_graph(n_nodes=n_nodes, seed=seed)
        n_stops = max(1, round(n_nodes * n_stops_fraction))
        stops = list(range(1, n_stops + 1))  # nodes 1..n_stops; node 0 is the depot
        request = RouteRequest(depot=0, stops=stops)
        reports.append(run_benchmark(graph, request, config))
    return reports
