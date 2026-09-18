"""
Ablation study: does periodic memetic 2-opt refinement of personal bests
(QPSO/ClassicalPSO's `memetic_interval`) give QPSO a *disproportionate*
edge over classical PSO, or does it help both equally?

For each instance size, runs four configurations across N seeded instances
and reports win/tie/loss counts + average relative gap:
    QPSO no-memetic   vs  PSO no-memetic   (the Day-1 baseline result)
    QPSO memetic      vs  PSO memetic      (both get the new technique)

If the technique is QPSO-specific (as hypothesized -- it improves both the
attractor AND mbest for QPSO, but only the attractor for PSO), QPSO's win
rate in the second comparison should be meaningfully higher than the first.

Usage (from backend/, with the venv active):
    python scripts/ablation_memetic.py
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


def compare(n_stops: int, seeds: range, memetic_interval: int | None) -> None:
    wins, ties, losses = 0, 0, 0
    gaps = []

    for seed in seeds:
        graph = generate_synthetic_graph(n_nodes=n_stops * 2, seed=seed)
        stops = list(range(1, n_stops + 1))
        request = RouteRequest(depot=0, stops=stops)
        problem = RoutingProblem(graph, request)

        q = polish_result(
            problem,
            QPSO(graph, request, memetic_interval=memetic_interval, seed=1).run(),
        )
        p = polish_result(
            problem,
            ClassicalPSO(graph, request, memetic_interval=memetic_interval, seed=1).run(),
        )

        if q.best_cost < p.best_cost - 1e-6:
            wins += 1
        elif p.best_cost < q.best_cost - 1e-6:
            losses += 1
        else:
            ties += 1
        gaps.append(100.0 * (q.best_cost - p.best_cost) / p.best_cost)

    n = wins + ties + losses
    label = f"memetic={memetic_interval}" if memetic_interval else "memetic=off"
    print(
        f"  n_stops={n_stops:<3} {label:<15} wins={wins:<3} ties={ties:<3} losses={losses:<3} "
        f"win_rate={100*wins/n:5.1f}%  avg(QPSO-PSO)/PSO={sum(gaps)/n:+.2f}%"
    )


def main() -> None:
    seeds = range(300, 330)  # 30 instances per size, matching the Day-1 validation sample

    for n_stops in (20, 30, 50):
        t0 = time.perf_counter()
        compare(n_stops, seeds, memetic_interval=None)
        compare(n_stops, seeds, memetic_interval=25)
        print(f"  ({time.perf_counter() - t0:.1f}s for this size)\n")


if __name__ == "__main__":
    main()
