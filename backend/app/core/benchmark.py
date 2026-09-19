"""
Benchmarking harness. Two entry points:

`run_benchmark` -- every algorithm (nearest-neighbor, classical PSO, GA, QPSO,
and Held-Karp exact when the instance is small enough) on ONE graph instance:
solution cost, optimality gap vs the exact optimum, convergence curve, runtime.

`run_qpso_vs_pso` -- QPSO vs classical PSO across MANY random instances (and
optionally several algorithm seeds per instance): win/tie/loss counts, mean and
worst-case improvement, an exact sign-test p-value, seed-to-seed spread,
convergence speed, and a per-run CSV so every claim is auditable.

Two costs are reported side by side everywhere, and they answer different questions:

    raw       what the metaheuristic itself found, with no local search. This is
              the like-for-like algorithm comparison (same encoding, same fitness,
              same particle/iteration budget) and the HEADLINE metric.
    +2-opt    the same output after a uniform 2-opt polish (core/local_search.py),
              i.e. the hybrid the production engine would actually run. The
              polish does most of the work for every algorithm, so it shrinks the
              raw gap from ~20% to ~1-2% -- see docs/BENCHMARKS.md, Finding 7.

`run_scalability_sweep` reruns `run_benchmark` across synthetic graphs of
increasing size (Day 3 deliverable); the exact baseline is dropped once
instances exceed MAX_STOPS_FOR_EXACT, since Held-Karp is exponential.

Output feeds scripts/run_benchmark.py, scripts/compare_qpso_vs_pso.py, and the
/benchmark API endpoint + frontend charts (Day 2).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

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

TIE_TOLERANCE = 1e-6


@dataclass
class BenchmarkConfig:
    n_particles: int = 40
    n_iterations: int = 800
    ga_population_size: int = 40
    ga_generations: int = 800
    penalty_weight: float = 1000.0
    seed: int | None = None
    include_exact: bool = True  # auto-skipped once stop count exceeds MAX_STOPS_FOR_EXACT
    polish_with_two_opt: bool = True  # applied uniformly to every non-exact algorithm, alongside the raw result


# --------------------------------------------------------------------------
# Single-instance comparison of every algorithm
# --------------------------------------------------------------------------


@dataclass
class AlgorithmBenchmark:
    name: str
    raw_result: OptimizationResult  # the algorithm's own output, no local search: the headline
    result: OptimizationResult  # after the 2-opt polish; the same object as raw_result if no polish was applied
    raw_gap_pct: float | None  # None when no exact baseline is available for this instance
    polished_gap_pct: float | None  # None when no exact baseline exists or no polish was applied

    @property
    def raw_cost(self) -> float:
        return self.raw_result.best_cost

    @property
    def polished(self) -> bool:
        return self.result is not self.raw_result


@dataclass
class BenchmarkReport:
    n_nodes: int
    n_stops: int
    exact_cost: float | None
    algorithms: list[AlgorithmBenchmark]

    def summary_table(self) -> str:
        header = (
            f"{'algorithm':<18}{'raw cost':>11}{'raw gap %':>11}"
            f"{'+2-opt cost':>13}{'+2-opt gap %':>14}{'raw runtime (s)':>17}{'iterations':>12}"
        )
        lines = [f"[{self.n_nodes} nodes, {self.n_stops} stops]", header, "-" * len(header)]
        for algo in self.algorithms:
            raw_gap = f"{algo.raw_gap_pct:.2f}" if algo.raw_gap_pct is not None else "-"
            pol_gap = f"{algo.polished_gap_pct:.2f}" if algo.polished_gap_pct is not None else "-"
            pol_cost = f"{algo.result.best_cost:.2f}" if algo.polished else "-"
            lines.append(
                f"{algo.name:<18}{algo.raw_cost:>11.2f}{raw_gap:>11}{pol_cost:>13}{pol_gap:>14}"
                f"{algo.raw_result.runtime_sec:>17.4f}{algo.raw_result.iterations:>12}"
            )
        lines.append("raw = algorithm output, no local search (headline); +2-opt = same output after a uniform 2-opt polish")
        return "\n".join(lines)


def _gap_pct(cost: float, exact_cost: float | None) -> float | None:
    if exact_cost is None or exact_cost <= 0:
        return None
    return 100.0 * (cost - exact_cost) / exact_cost


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
    if config.include_exact and n_stops <= MAX_STOPS_FOR_EXACT and request.n_vehicles == 1:
        exact_result = held_karp(graph, request)
        exact_cost = exact_result.best_cost
        runs.append(("held_karp_exact", exact_result))

    problem = RoutingProblem(graph, request)
    algorithms = []
    for name, raw_result in runs:
        result = raw_result
        if config.polish_with_two_opt and name != "held_karp_exact":
            result = polish_result(problem, raw_result, config.penalty_weight)

        algorithms.append(
            AlgorithmBenchmark(
                name=name,
                raw_result=raw_result,
                result=result,
                raw_gap_pct=_gap_pct(raw_result.best_cost, exact_cost),
                polished_gap_pct=_gap_pct(result.best_cost, exact_cost) if result is not raw_result else None,
            )
        )

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


# --------------------------------------------------------------------------
# Paired QPSO vs classical PSO comparison across many instances
# --------------------------------------------------------------------------


def sign_test_p_value(wins: int, losses: int) -> float:
    """One-sided exact sign test: the probability of at least `wins` wins in
    `wins + losses` decisive comparisons if QPSO and PSO were equally good.
    Ties carry no information and are excluded. Deliberately simple and
    conservative -- it ignores the size of each win."""
    n = wins + losses
    if n == 0:
        return 1.0
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n


def iterations_to_reach(history: Sequence[float], target: float) -> int | None:
    """First iteration index at which a best-so-far curve is at or below `target`
    (index 0 is the initial swarm), or None if it never gets there."""
    for iteration, cost in enumerate(history):
        if cost <= target + 1e-9:
            return iteration
    return None


@dataclass
class PairedStats:
    wins: int  # instances where QPSO's cost is lower than PSO's
    ties: int
    losses: int
    mean_improvement_pct: float  # (PSO - QPSO) / PSO * 100, averaged over instances; positive = QPSO better
    worst_improvement_pct: float  # the single worst instance for QPSO (most negative)
    std_improvement_pct: float
    qpso_mean_cost: float
    pso_mean_cost: float
    sign_test_p: float  # one-sided, "QPSO is better"


@dataclass
class ConvergenceSpeed:
    budget: int  # iterations each algorithm was given
    reached_fraction: float  # share of runs where QPSO matched PSO's FINAL raw cost within the budget
    median_iterations: float | None  # median iterations QPSO needed to do so (only runs where it did)


@dataclass
class QpsoVsPsoReport:
    n_stops: int
    n_instances: int
    algo_seeds: tuple[int, ...]
    raw: PairedStats
    polished: PairedStats
    qpso_seed_std: float | None  # mean over instances of the raw-cost std across algorithm seeds (needs >= 2 seeds)
    pso_seed_std: float | None
    convergence: ConvergenceSpeed
    rows: list[dict]  # one per (instance, algorithm seed, algorithm), for CSV export

    def summary_table(self) -> str:
        def p_text(p: float) -> str:
            return "<0.0001" if p < 1e-4 else f"{p:.4f}"

        lines = [
            f"QPSO vs classical PSO | {self.n_stops} stops | {self.n_instances} instances x "
            f"{len(self.algo_seeds)} seed(s) | {self.convergence.budget} iterations",
            f"{'':<36}{'raw (no local search)':>24}{'+2-opt polish (hybrid)':>26}",
            "-" * 86,
        ]

        def row(label: str, raw: str, polished: str) -> None:
            lines.append(f"{label:<36}{raw:>24}{polished:>26}")

        r, p = self.raw, self.polished
        row("QPSO wins / ties / losses", f"{r.wins} / {r.ties} / {r.losses}", f"{p.wins} / {p.ties} / {p.losses}")
        row("mean improvement (+ = QPSO better)", f"{r.mean_improvement_pct:+.2f}%", f"{p.mean_improvement_pct:+.2f}%")
        row("worst-instance improvement", f"{r.worst_improvement_pct:+.2f}%", f"{p.worst_improvement_pct:+.2f}%")
        row("std of improvement", f"{r.std_improvement_pct:.2f} pts", f"{p.std_improvement_pct:.2f} pts")
        row("sign-test p (QPSO better)", p_text(r.sign_test_p), p_text(p.sign_test_p))
        row("mean cost  QPSO / PSO", f"{r.qpso_mean_cost:.1f} / {r.pso_mean_cost:.1f}", f"{p.qpso_mean_cost:.1f} / {p.pso_mean_cost:.1f}")
        if self.qpso_seed_std is not None and self.pso_seed_std is not None:
            row("seed-to-seed std  QPSO / PSO", f"{self.qpso_seed_std:.2f} / {self.pso_seed_std:.2f}", "-")

        c = self.convergence
        if c.median_iterations is None:
            lines.append("convergence: QPSO never reached PSO's final raw cost within the budget")
        else:
            lines.append(
                f"convergence: QPSO matched PSO's final raw cost in {100 * c.reached_fraction:.0f}% of runs, "
                f"median {c.median_iterations:.0f} of {c.budget} iterations ({100 * c.median_iterations / c.budget:.0f}% of the budget)"
            )
        return "\n".join(lines)

    def to_csv(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0].keys()))
            writer.writeheader()
            writer.writerows(self.rows)


def _paired_stats(qpso_costs: Sequence[float], pso_costs: Sequence[float]) -> PairedStats:
    q, p = np.asarray(qpso_costs, dtype=float), np.asarray(pso_costs, dtype=float)
    wins = int(np.sum(q < p - TIE_TOLERANCE))
    losses = int(np.sum(p < q - TIE_TOLERANCE))
    improvement = 100.0 * (p - q) / p
    return PairedStats(
        wins=wins,
        ties=len(q) - wins - losses,
        losses=losses,
        mean_improvement_pct=float(improvement.mean()),
        worst_improvement_pct=float(improvement.min()),
        std_improvement_pct=float(improvement.std(ddof=1)) if len(q) > 1 else 0.0,
        qpso_mean_cost=float(q.mean()),
        pso_mean_cost=float(p.mean()),
        sign_test_p=sign_test_p_value(wins, losses),
    )


def run_qpso_vs_pso(
    n_stops: int,
    instance_seeds: Sequence[int] = tuple(range(300, 330)),
    algo_seeds: Sequence[int] = (1,),
    nodes_per_stop: int = 2,
    config: BenchmarkConfig | None = None,
    pso_kwargs: dict | None = None,
) -> QpsoVsPsoReport:
    """Paired comparison on `len(instance_seeds)` random synthetic instances.

    The instance is the unit of analysis: with several `algo_seeds`, each
    algorithm's cost is first averaged over those seeds per instance, and the
    win/tie/loss counts and sign test run over instances (seeds on the same
    instance aren't independent evidence). The seeds instead give the
    seed-to-seed std, i.e. how repeatable each algorithm is.

    `pso_kwargs` overrides ClassicalPSO's parameters (inertia, c1, c2, v_max),
    to check the result isn't an artifact of one PSO parameter set.
    """
    config = config or BenchmarkConfig()
    pso_kwargs = pso_kwargs or {}

    rows: list[dict] = []
    q_raw_mean, p_raw_mean, q_pol_mean, p_pol_mean = [], [], [], []
    q_seed_std, p_seed_std = [], []
    matched: list[int | None] = []

    shared = dict(
        n_particles=config.n_particles,
        n_iterations=config.n_iterations,
        penalty_weight=config.penalty_weight,
    )

    for instance_seed in instance_seeds:
        graph = generate_synthetic_graph(n_nodes=n_stops * nodes_per_stop, seed=instance_seed)
        request = RouteRequest(depot=0, stops=list(range(1, n_stops + 1)))
        problem = RoutingProblem(graph, request)

        q_raw, p_raw, q_pol, p_pol = [], [], [], []
        for algo_seed in algo_seeds:
            qpso = QPSO(graph, request, seed=algo_seed, **shared).run()
            pso = ClassicalPSO(graph, request, seed=algo_seed, **shared, **pso_kwargs).run()
            qpso_polished = polish_result(problem, qpso, config.penalty_weight)
            pso_polished = polish_result(problem, pso, config.penalty_weight)

            iters_to_match = iterations_to_reach(qpso.convergence_history, pso.best_cost)
            matched.append(iters_to_match)

            for name, raw, polished, extra in (
                ("QPSO", qpso, qpso_polished, iters_to_match),
                ("PSO", pso, pso_polished, None),
            ):
                rows.append(
                    {
                        "n_stops": n_stops,
                        "instance_seed": instance_seed,
                        "algo_seed": algo_seed,
                        "algorithm": name,
                        "raw_cost": raw.best_cost,
                        "polished_cost": polished.best_cost,
                        "raw_runtime_sec": raw.runtime_sec,
                        "iterations_to_match_pso_final": "" if extra is None else extra,
                    }
                )

            q_raw.append(qpso.best_cost)
            p_raw.append(pso.best_cost)
            q_pol.append(qpso_polished.best_cost)
            p_pol.append(pso_polished.best_cost)

        q_raw_mean.append(np.mean(q_raw))
        p_raw_mean.append(np.mean(p_raw))
        q_pol_mean.append(np.mean(q_pol))
        p_pol_mean.append(np.mean(p_pol))
        if len(algo_seeds) > 1:
            q_seed_std.append(np.std(q_raw, ddof=1))
            p_seed_std.append(np.std(p_raw, ddof=1))

    reached = [m for m in matched if m is not None]
    return QpsoVsPsoReport(
        n_stops=n_stops,
        n_instances=len(instance_seeds),
        algo_seeds=tuple(algo_seeds),
        raw=_paired_stats(q_raw_mean, p_raw_mean),
        polished=_paired_stats(q_pol_mean, p_pol_mean),
        qpso_seed_std=float(np.mean(q_seed_std)) if q_seed_std else None,
        pso_seed_std=float(np.mean(p_seed_std)) if p_seed_std else None,
        convergence=ConvergenceSpeed(
            budget=config.n_iterations,
            reached_fraction=len(reached) / len(matched),
            median_iterations=float(np.median(reached)) if reached else None,
        ),
        rows=rows,
    )
