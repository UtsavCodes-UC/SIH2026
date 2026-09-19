"""
CLI: paired QPSO vs classical PSO comparison across many random instances.

Reports, for the raw metaheuristic output (headline) and for the same output
after a uniform 2-opt polish (hybrid): win/tie/loss, mean and worst-case
improvement, an exact sign-test p-value, seed-to-seed spread and convergence
speed -- and optionally writes every individual run to CSV so the numbers can
be audited or re-analyzed.

Usage (from backend/, with the venv active):
    python scripts/compare_qpso_vs_pso.py
    python scripts/compare_qpso_vs_pso.py --stops 30 --instances 30 --seeds 1 2 3
    python scripts/compare_qpso_vs_pso.py --stops 20 30 50 --pso-preset clerc --csv-dir results
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.benchmark import BenchmarkConfig, run_qpso_vs_pso  # noqa: E402

# Classical PSO parameter sets, to check the result isn't an artifact of one baseline.
PSO_PRESETS = {
    "ours": {},  # ClassicalPSO defaults: inertia 0.9 -> 0.4, c1 = c2 = 2.0, v_max 0.5
    "teammate": dict(w_start=0.7, w_end=0.7, c1=1.5, c2=1.5, v_max=0.2),
    "clerc": dict(w_start=0.729, w_end=0.729, c1=1.49445, c2=1.49445, v_max=0.5),  # constriction PSO
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stops", type=int, nargs="+", default=[20, 30, 50], help="stop counts to compare at")
    parser.add_argument("--instances", type=int, default=30, help="random instances per stop count")
    parser.add_argument("--first-instance-seed", type=int, default=300)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1], help="algorithm seeds per instance")
    parser.add_argument("--iterations", type=int, default=800)
    parser.add_argument("--particles", type=int, default=40)
    parser.add_argument("--pso-preset", choices=sorted(PSO_PRESETS), default="ours")
    parser.add_argument("--csv-dir", type=Path, default=None, help="write one per-run CSV per stop count here")
    args = parser.parse_args()

    config = BenchmarkConfig(n_particles=args.particles, n_iterations=args.iterations)
    instance_seeds = range(args.first_instance_seed, args.first_instance_seed + args.instances)

    for n_stops in args.stops:
        report = run_qpso_vs_pso(
            n_stops,
            instance_seeds=instance_seeds,
            algo_seeds=args.seeds,
            config=config,
            pso_kwargs=PSO_PRESETS[args.pso_preset],
        )
        print(f"[PSO baseline: {args.pso_preset}]")
        print(report.summary_table())
        if args.csv_dir is not None:
            csv_path = args.csv_dir / f"qpso_vs_pso_{n_stops}stops_{args.pso_preset}.csv"
            report.to_csv(csv_path)
            print(f"per-run results written to {csv_path}")
        print()


if __name__ == "__main__":
    main()
