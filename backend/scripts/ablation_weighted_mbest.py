"""
Ablation study: does rank-weighted mbest (QPSO's `weighted_mbest=True`) widen
QPSO's win rate over classical PSO compared to plain-mean mbest?

Unlike the memetic-refinement ablation, this needs no "give PSO the same
technique" fairness check -- PSO has no mbest concept at all, so there's
nothing to give it. Same instance suite as scripts/ablation_memetic.py and
docs/BENCHMARKS.md Finding 2, for a direct before/after comparison.

Usage (from backend/, with the venv active):
    python scripts/ablation_weighted_mbest.py
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


def compare(n_stops: int, seeds: range, weighted_mbest: bool) -> None:
    wins, ties, losses = 0, 0, 0
    gaps = []

    for seed in seeds:
        graph = generate_synthetic_graph(n_nodes=n_stops * 2, seed=seed)
        stops = list(range(1, n_stops + 1))
        request = RouteRequest(depot=0, stops=stops)
        problem = RoutingProblem(graph, request)

        q = polish_result(
            problem,
            QPSO(graph, request, weighted_mbest=weighted_mbest, seed=1).run(),
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
    label = "weighted_mbest=True " if weighted_mbest else "weighted_mbest=False"
    print(
        f"  n_stops={n_stops:<3} {label} wins={wins:<3} ties={ties:<3} losses={losses:<3} "
        f"win_rate={100*wins/n:5.1f}%  avg(QPSO-PSO)/PSO={sum(gaps)/n:+.2f}%"
    )


def main() -> None:
    seeds = range(300, 330)  # same 30-instance sample used for Finding 2 / the memetic ablation

    for n_stops in (20, 30, 50):
        t0 = time.perf_counter()
        compare(n_stops, seeds, weighted_mbest=False)
        compare(n_stops, seeds, weighted_mbest=True)
        print(f"  ({time.perf_counter() - t0:.1f}s for this size)\n")


if __name__ == "__main__":
    main()
