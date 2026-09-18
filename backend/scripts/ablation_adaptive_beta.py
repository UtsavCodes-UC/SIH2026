"""
Ablation study: does fitness-adaptive per-particle beta (QPSO's
`adaptive_beta=True`) widen QPSO's win rate over classical PSO, compared to
the uniform-beta schedule?

Motivated by the Finding 3-5 pattern (docs/BENCHMARKS.md): every previous
enhancement pushed the *whole* swarm toward exploitation (or disrupted it)
together and lost. This instead lets each particle's own beta depend on its
own quality -- good particles exploit, bad particles keep exploring -- so
swarm-wide diversity should survive even as the best solution improves,
without abandoning the validated overall beta schedule (the per-particle
multiplier averages to ~1.0 across the swarm).

Usage (from backend/, with the venv active):
    python scripts/ablation_adaptive_beta.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.baselines.classical_pso import ClassicalPSO  # noqa: E402
from app.core.local_search import polish_result  # noqa: E402
from app.core.qpso import QPSO  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402


def compare(n_stops: int, seeds: range, adaptive_beta: bool) -> None:
    wins, ties, losses = 0, 0, 0
    gaps = []

    for seed in seeds:
        graph = generate_synthetic_graph(n_nodes=n_stops * 2, seed=seed)
        stops = list(range(1, n_stops + 1))
        request = RouteRequest(depot=0, stops=stops)
        problem = RoutingProblem(graph, request)

        q = polish_result(
            problem,
            QPSO(graph, request, adaptive_beta=adaptive_beta, seed=1).run(),
        )
        p = polish_result(problem, ClassicalPSO(graph, request, seed=1).run())

        if q.best_cost < p.best_cost - 1e-6:
            wins += 1
        elif p.best_cost < q.best_cost - 1e-6:
            losses += 1
        else:
            ties += 1
        gaps.append(100.0 * (q.best_cost - p.best_cost) / p.best_cost)

    n = wins + ties + losses
    label = "adaptive_beta=True " if adaptive_beta else "adaptive_beta=False"
    print(
        f"  n_stops={n_stops:<3} {label} wins={wins:<3} ties={ties:<3} losses={losses:<3} "
        f"win_rate={100*wins/n:5.1f}%  avg(QPSO-PSO)/PSO={sum(gaps)/n:+.2f}%"
    )


def main() -> None:
    seeds = range(300, 330)  # same 30-instance sample as Findings 2-5

    for n_stops in (20, 30, 50):
        t0 = time.perf_counter()
        compare(n_stops, seeds, adaptive_beta=False)
        compare(n_stops, seeds, adaptive_beta=True)
        print(f"  ({time.perf_counter() - t0:.1f}s for this size)\n")


if __name__ == "__main__":
    main()
