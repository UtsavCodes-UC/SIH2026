"""
Ablation study: does stagnation-triggered diversity injection
(QPSO's `stagnation_limit`/`reinjection_fraction`) widen QPSO's win rate
over classical PSO, compared to no injection?

Motivated by Findings 3 and 4 (docs/BENCHMARKS.md): both memetic refinement
and weighted mbest hurt QPSO's edge because they push the swarm toward
exploitation earlier, cutting into the sustained exploration Finding 2
showed the advantage actually comes from. This instead fights premature
convergence directly -- it should, in theory, extend the exploration phase
rather than shorten it. Like weighted_mbest, PSO has no equivalent state to
give this to "for fairness" (nothing stops us from doing an analogous
random-restart on PSO's worst particles too, but that's a separate,
generic technique -- this ablation isolates whether the stagnation-gated
version specifically helps QPSO).

Usage (from backend/, with the venv active):
    python scripts/ablation_stagnation.py
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


def compare(n_stops: int, seeds: range, stagnation_limit: int | None, reinjection_fraction: float = 0.25) -> None:
    wins, ties, losses = 0, 0, 0
    gaps = []

    for seed in seeds:
        graph = generate_synthetic_graph(n_nodes=n_stops * 2, seed=seed)
        stops = list(range(1, n_stops + 1))
        request = RouteRequest(depot=0, stops=stops)
        problem = RoutingProblem(graph, request)

        q = polish_result(
            problem,
            QPSO(
                graph, request,
                stagnation_limit=stagnation_limit, reinjection_fraction=reinjection_fraction, seed=1,
            ).run(),
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
    label = f"stagnation_limit={stagnation_limit}" if stagnation_limit else "stagnation_limit=off"
    print(
        f"  n_stops={n_stops:<3} {label:<22} wins={wins:<3} ties={ties:<3} losses={losses:<3} "
        f"win_rate={100*wins/n:5.1f}%  avg(QPSO-PSO)/PSO={sum(gaps)/n:+.2f}%"
    )


def main() -> None:
    seeds = range(300, 330)  # same 30-instance sample as Findings 2-4

    for n_stops in (20, 30, 50):
        t0 = time.perf_counter()
        compare(n_stops, seeds, stagnation_limit=None)
        compare(n_stops, seeds, stagnation_limit=60, reinjection_fraction=0.25)
        compare(n_stops, seeds, stagnation_limit=100, reinjection_fraction=0.15)
        print(f"  ({time.perf_counter() - t0:.1f}s for this size)\n")


if __name__ == "__main__":
    main()
