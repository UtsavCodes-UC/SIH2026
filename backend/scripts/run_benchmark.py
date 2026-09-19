"""
CLI: run QPSO vs classical PSO vs GA vs nearest-neighbor vs exact (Held-Karp)
on a synthetic graph instance, print the comparison table, and save a
convergence chart.

Usage (from backend/, with the venv active):
    python scripts/run_benchmark.py
    python scripts/run_benchmark.py --nodes 30 --stops 7 --iterations 150 --seed 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.benchmark import BenchmarkConfig, run_benchmark  # noqa: E402
from app.core.vrp_formulation import RouteRequest  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=25, help="number of nodes in the synthetic graph")
    parser.add_argument("--stops", type=int, default=7, help="number of stops the route must visit")
    parser.add_argument("--iterations", type=int, default=800, help="iterations/generations for QPSO/PSO/GA")
    parser.add_argument("--particles", type=int, default=40, help="particle/population size")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--plot", action="store_true", help="save a convergence chart to convergence.png")
    args = parser.parse_args()

    graph = generate_synthetic_graph(n_nodes=args.nodes, seed=args.seed)
    stops = list(range(1, args.stops + 1))
    request = RouteRequest(depot=0, stops=stops)

    config = BenchmarkConfig(
        n_particles=args.particles,
        n_iterations=args.iterations,
        ga_population_size=args.particles,
        ga_generations=args.iterations,
        seed=args.seed,
    )

    report = run_benchmark(graph, request, config)
    print(report.summary_table())

    if args.plot:
        _save_convergence_plot(report)


def _save_convergence_plot(report) -> None:
    import matplotlib.pyplot as plt

    plt.figure(figsize=(8, 5))
    for algo in report.algorithms:
        history = algo.raw_result.convergence_history
        if len(history) > 1:  # skip single-shot algorithms (nearest-neighbor, exact)
            plt.plot(history, label=algo.name)
    plt.xlabel("iteration")
    plt.ylabel("best cost (min)")
    plt.title(f"Convergence — {report.n_nodes} nodes, {report.n_stops} stops")
    plt.legend()
    plt.tight_layout()
    plt.savefig("convergence.png")
    print("\nsaved convergence.png")


if __name__ == "__main__":
    main()
