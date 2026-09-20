"""
Do the time windows change the plans, and do the algorithms handle them? See docs/BENCHMARKS.md, Finding 17.

Each problem is solved twice by each algorithm, through the same `solve()` the API uses:

    aware       lateness is priced (10 cost units per minute late, the app's default)
    ignoring    the same windows, but lateness costs nothing (penalty 0), so the plan is what the algorithm
                would build if it did not know about the windows

and every finished plan is then measured against the windows: minutes late, stops late, minutes of driving. The
problems are those of Findings 15-16: the app's synthetic road network with random congestion, random stops and demands,
fleet for 85% utilisation, 20 instances at each of 15 and 30 stops. The windows are the app's demo windows (30-60 minutes
wide, opening up to 80 minutes after the quickest a van could get to the stop), with 5 minutes of service at each stop.
Algorithms: QPSO with warm start and the polish (the app default), classical PSO, GA, nearest neighbour. The route search
and the exact solver do not handle windows and are not included. With windows the swarms and the GA also start from a
window-aware seed (`warm_start.window_aware_order`); `--plain-seeds` switches that off, to measure what it is worth
(results/time_windows/aware_vs_ignoring_plain_seeds.csv).

Usage (from backend/, venv active):
    python scripts/time_windows_experiment.py --csv results/time_windows/aware_vs_ignoring.csv
    python scripts/time_windows_experiment.py --from-csv results/time_windows/aware_vs_ignoring.csv
    python scripts/time_windows_experiment.py --plain-seeds --csv results/time_windows/aware_vs_ignoring_plain_seeds.csv
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import warm_start  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.time_windows import random_time_windows  # noqa: E402
from app.core.vrp_formulation import RoutingProblem, split_at_depot  # noqa: E402
from app.services.solver import solve  # noqa: E402
from app_options_comparison import build  # noqa: E402

ALGORITHMS = {"qpso": "QPSO (app default)", "pso": "classical PSO", "ga": "genetic algorithm", "nearest_neighbor": "nearest neighbour"}
SIZES = (15, 30)
FIRST_SEED = 900
SERVICE_MIN = 5.0
PENALTY = 10.0
FIELDS = ["stops", "seed", "algorithm", "condition", "driving_min", "late_min", "late_stops", "wait_min", "objective"]


def run(job):
    n_stops, seed, plain_seeds = job
    warm_start.WINDOW_AWARE_SEED = not plain_seeds
    graph, base = build(n_stops, seed)
    quickest = graph.all_pairs_shortest_time([base.depot])[base.depot]
    windows = random_time_windows(base.stops, quickest, random.Random(f"{seed}-windows"))
    aware = dataclasses.replace(base, time_windows=windows, service_time_min=SERVICE_MIN, time_window_penalty=PENALTY)
    ignoring = dataclasses.replace(aware, time_window_penalty=0.0)
    judge = RoutingProblem(graph, aware)  # measures every plan against the windows, at the app's penalty
    rows = []
    for algorithm in ALGORITHMS:
        for condition, request in (("aware", aware), ("ignoring", ignoring)):
            solution = solve(graph, request, algorithm, 40, 800, seed, True, warm_start=True)
            routes = split_at_depot(solution.final.best_route, base.depot)
            assert sorted(s for r in routes for s in r[1:-1]) == sorted(base.stops), "a stop was lost or repeated"
            e = judge.evaluate_routes(routes)
            rows.append({"stops": n_stops, "seed": seed, "algorithm": algorithm, "condition": condition,
                         "driving_min": round(e.total_time_min, 4), "late_min": round(e.lateness_min, 4), "late_stops": e.late_stops,
                         "wait_min": round(e.waiting_min, 4), "objective": round(judge.penalized_cost(e), 4)})
    return rows


def report(rows) -> None:
    for n in sorted({r["stops"] for r in rows}):
        print(f"\n{n} stops, {len({r['seed'] for r in rows if r['stops'] == n})} instances: mean over instances; objective = driving minutes + {PENALTY:g} x minutes late")
        print(f"{'':<20}{'plan':<10}{'late min':>10}{'late stops':>12}{'driving':>10}{'waiting':>9}{'objective':>11}   aware vs ignoring on the objective")
        for algorithm, label in ALGORITHMS.items():
            by = {(r["seed"], r["condition"]): r for r in rows if r["stops"] == n and r["algorithm"] == algorithm}
            seeds = sorted({s for s, _ in by})
            wins = sum(by[(s, "aware")]["objective"] < by[(s, "ignoring")]["objective"] - 1e-6 for s in seeds)
            losses = sum(by[(s, "aware")]["objective"] > by[(s, "ignoring")]["objective"] + 1e-6 for s in seeds)
            gain = statistics.fmean(100 * (by[(s, "ignoring")]["objective"] - by[(s, "aware")]["objective"]) / by[(s, "ignoring")]["objective"] for s in seeds)
            for condition in ("ignoring", "aware"):
                sub = [by[(s, condition)] for s in seeds]
                tail = f"   {wins}/{len(seeds) - wins - losses}/{losses} wins/ties/losses, {gain:+.1f}% objective, p = {sign_test_p_value(wins, losses):.4f}" if condition == "aware" else ""
                print(f"{label if condition == 'ignoring' else '':<20}{condition:<10}{statistics.fmean(r['late_min'] for r in sub):>10.1f}{statistics.fmean(r['late_stops'] for r in sub):>12.1f}"
                      f"{statistics.fmean(r['driving_min'] for r in sub):>10.1f}{statistics.fmean(r['wait_min'] for r in sub):>9.1f}{statistics.fmean(r['objective'] for r in sub):>11.1f}{tail}")
        # how the algorithms compare when they know about the windows
        aware = {a: {r["seed"]: r["objective"] for r in rows if r["stops"] == n and r["algorithm"] == a and r["condition"] == "aware"} for a in ALGORITHMS}
        seeds = sorted(aware["qpso"])
        print("QPSO against the others, both window-aware (objective; wins/ties/losses of QPSO being lower):")
        for other in ("pso", "ga", "nearest_neighbor"):
            wins = sum(aware["qpso"][s] < aware[other][s] - 1e-6 for s in seeds)
            losses = sum(aware["qpso"][s] > aware[other][s] + 1e-6 for s in seeds)
            diff = statistics.fmean(100 * (aware[other][s] - aware["qpso"][s]) / aware[other][s] for s in seeds)
            print(f"  vs {ALGORITHMS[other]:<18} {wins}/{len(seeds) - wins - losses}/{losses}  QPSO's objective is {abs(diff):.1f}% {'lower' if diff >= 0 else 'HIGHER'}  p = {sign_test_p_value(wins, losses):.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instances", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--plain-seeds", action="store_true", help="do not give the swarms and the GA the window-aware starting solution")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path)
    args = parser.parse_args()

    if args.from_csv:
        rows = [{**r, "stops": int(r["stops"]), "seed": int(r["seed"]), **{k: float(r[k]) for k in ("driving_min", "late_min", "late_stops", "wait_min", "objective")}}
                for r in csv.DictReader(args.from_csv.open(encoding="utf-8"))]
        report(rows)
        return
    jobs = [(n, FIRST_SEED + k, args.plain_seeds) for n in sorted(SIZES, reverse=True) for k in range(args.instances)]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for chunk in pool.map(run, jobs, chunksize=1) for row in chunk]
    print(f"[{time.perf_counter() - started:.0f} s wall, {args.workers} processes]")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda r: (r["stops"], r["seed"], list(ALGORITHMS).index(r["algorithm"]), r["condition"])))
    report(rows)


if __name__ == "__main__":
    main()
