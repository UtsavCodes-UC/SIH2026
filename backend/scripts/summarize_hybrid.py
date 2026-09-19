"""
Every number in docs/BENCHMARKS.md Finding 11 comes from this script reading the per-run CSVs that
`hybrid_experiments.py` wrote to results/hybrid/ (and the OR-Tools reference tours next to them).

    python scripts/summarize_hybrid.py                    # all sizes found in results/hybrid/
    python scripts/summarize_hybrid.py --dir results/hybrid --first h_qpso --against pso h_pso qpso nn ga

For each file it prints, on the cost after the same final polish (lower is better): the mean cost of every variant,
how far each is above the OR-Tools reference when one exists, and win/tie/loss with mean improvement and an exact
one-sided sign test for the first variant against each of the others.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.benchmark import sign_test_p_value  # noqa: E402


def load(path: Path) -> dict[str, dict[int, tuple[float, float]]]:
    rows: dict[str, dict[int, tuple[float, float]]] = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        rows.setdefault(r["variant"], {})[int(r["instance_seed"])] = (float(r["raw_cost"]), float(r["polished_cost"]))
    return rows


def column(rows, variant, seeds, index):
    return np.array([rows[variant][s][index] for s in seeds])


def paired(ours: np.ndarray, other: np.ndarray) -> str:
    wins, losses = int((ours < other - 1e-6).sum()), int((other < ours - 1e-6).sum())
    improvement = float((100 * (other - ours) / other).mean())
    return f"{wins}/{len(ours) - wins - losses}/{losses}  {improvement:+.1f}%  p={sign_test_p_value(wins, losses):.3f}"


def summarize(path: Path, first: str, against: list[str]) -> None:
    rows = load(path)
    if first not in rows:
        print(f"{path.name}: no '{first}' runs, skipped")
        return
    seeds = sorted(rows[first])
    stem = path.stem  # e.g. tsp100
    reference = path.with_name(stem + "_best_known.csv")
    known = None
    if reference.exists():
        by_seed = {int(r["instance_seed"]): float(r["cost"]) for r in csv.DictReader(reference.open(encoding="utf-8"))}
        known = np.array([by_seed[s] for s in seeds])

    print(f"\n=== {stem}: {len(seeds)} instances (seeds {seeds[0]}-{seeds[-1]}); cost after the same final polish")
    header = f"{'variant':<10}{'mean raw':>10}{'mean cost':>11}" + (f"{'vs OR-Tools':>13}" if known is not None else "") + f"   {first} vs it (win/tie/loss, improvement, p)"
    print(header)
    for name in [first, *[a for a in against if a in rows]]:
        raw, polished = column(rows, name, seeds, 0), column(rows, name, seeds, 1)
        gap = f"{100 * np.mean((polished - known) / known):>+12.1f}%" if known is not None else ""
        versus = "" if name == first else "   " + paired(column(rows, first, seeds, 1), polished)
        print(f"{name:<10}{raw.mean():>10.0f}{polished.mean():>11.0f}{gap}{versus}")
    if known is not None:
        print(f"{'OR-Tools':<10}{'':>10}{known.mean():>11.0f}   (reference: guided local search, mean of {len(seeds)})")
        wins = int((column(rows, first, seeds, 1) < known - 1e-6).sum())
        print(f"{first} is better than the OR-Tools reference on {wins} of {len(seeds)} instances")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parent.parent / "results" / "hybrid")
    parser.add_argument("--first", default="h_qpso")
    parser.add_argument("--against", nargs="+", default=["h_pso", "pso", "qpso", "pso_warm", "qpso_warm", "ga", "nn"])
    args = parser.parse_args()
    files = sorted(p for p in args.dir.glob("*.csv") if not p.stem.endswith("_best_known") and "ablation" not in p.stem)
    for path in sorted(files, key=lambda p: (p.stem.rstrip("0123456789"), int("".join(c for c in p.stem if c.isdigit()) or 0))):
        summarize(path, args.first, args.against)


if __name__ == "__main__":
    main()
