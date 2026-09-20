"""
What do the cost weights do to a plan? See docs/BENCHMARKS.md, Finding 16.

The same problems are solved with four settings of "what to minimize" (the app's presets) and each finished plan is
measured in real minutes, kilometres and congestion delay, whatever it was optimized for:

    fastest      time 1                       (the default)
    shortest     distance 1
    avoid jams   time 0.5, congestion 0.5
    balanced     time 0.4, distance 0.3, congestion 0.3

Two solvers, through the same `solve()` the API uses: the app default (QPSO, warm start, polish) and the route search
(3 s). Problems as in scripts/app_options_comparison.py: the app's synthetic road network with random congestion
(0.8x to 2.5x per road), random stops and demands, fleet sized for 85% utilisation; 20 instances per size.

Usage (from backend/, venv active):
    python scripts/cost_weights_tradeoff.py --csv results/cost_weights/tradeoff.csv
    python scripts/cost_weights_tradeoff.py --from-csv results/cost_weights/tradeoff.csv
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.cost_model import CostWeights, path_metrics  # noqa: E402
from app.core.vrp_formulation import split_at_depot  # noqa: E402
from app.services.solver import solve  # noqa: E402
from app_options_comparison import build  # noqa: E402

SETTINGS = {
    "fastest": CostWeights(1, 0, 0),
    "shortest": CostWeights(0, 1, 0),
    "avoid jams": CostWeights(0.5, 0, 0.5),
    "balanced": CostWeights(0.4, 0.3, 0.3),
}
SOLVERS = {
    "default": ("qpso", dict(n_particles=40, n_iterations=800, polish=True, warm_start=True)),
    "route search": ("route_search", dict(n_particles=40, n_iterations=800, polish=False, warm_start=False, time_limit_sec=3.0)),
}
SIZES = (30, 60)
FIRST_SEED = 800
FIELDS = ["solver", "stops", "seed", "setting", "time_min", "distance_km", "delay_min", "overload"]


def run(job):
    n_stops, seed = job
    graph, base = build(n_stops, seed)
    rows = []
    for setting, weights in SETTINGS.items():
        request = dataclasses.replace(base, cost_weights=weights)
        for solver, (algorithm, kwargs) in SOLVERS.items():
            solution = solve(graph, request, algorithm, seed=seed, **kwargs)
            routes = split_at_depot(solution.final.best_route, request.depot)
            assert sorted(s for r in routes for s in r[1:-1]) == sorted(request.stops), "a stop was lost or repeated"
            time_min = distance = delay = 0.0
            for route in routes:
                for u, v in zip(route, route[1:]):
                    m = path_metrics(graph, graph.shortest_path(u, v, weights))
                    time_min, distance, delay = time_min + m.time_min, distance + m.distance_km, delay + m.delay_min
            overload = solution.problem.evaluate_routes(routes).capacity_violation
            rows.append({"solver": solver, "stops": n_stops, "seed": seed, "setting": setting, "time_min": round(time_min, 4),
                         "distance_km": round(distance, 4), "delay_min": round(delay, 4), "overload": round(overload, 4)})
    return rows


def report(rows) -> None:
    metrics = (("time_min", "minutes"), ("distance_km", "km"), ("delay_min", "delay min"))
    for solver in SOLVERS:
        for n in sorted({r["stops"] for r in rows}):
            subset = [r for r in rows if r["solver"] == solver and r["stops"] == n]
            seeds = sorted({r["seed"] for r in subset})
            by = {(r["seed"], r["setting"]): r for r in subset}
            print(f"\n{solver}, {n} stops, {len(seeds)} instances: mean of the plan's real quantities, and the change from the 'fastest' plan")
            print(f"{'optimized for':<14}" + "".join(f"{label:>22}" for _, label in metrics) + f"{'':>4}fewest-of-four counts (min / km / delay)")
            for setting in SETTINGS:
                cells = []
                for key, _ in metrics:
                    mean = statistics.fmean(by[(s, setting)][key] for s in seeds)
                    base = statistics.fmean(by[(s, "fastest")][key] for s in seeds)
                    change = 100 * statistics.fmean((by[(s, setting)][key] - by[(s, "fastest")][key]) / by[(s, "fastest")][key] for s in seeds if by[(s, "fastest")][key] > 0)
                    cells.append(f"{mean:>12.1f} ({change:+6.1f}%)" if setting != "fastest" else f"{mean:>12.1f}{'':>10}")
                fewest = [sum(by[(s, setting)][key] <= min(by[(s, o)][key] for o in SETTINGS) + 1e-6 for s in seeds) for key, _ in metrics]
                print(f"{setting:<14}" + "".join(f"{c:>22}" for c in cells) + f"{'':>4}{fewest[0]:>3} / {fewest[1]:>3} / {fewest[2]:>3}")
    over = sum(1 for r in rows if r["overload"] > 0)
    print(f"\nplans with an overloaded van: {over} of {len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instances", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path)
    args = parser.parse_args()

    if args.from_csv:
        rows = [{**r, "stops": int(r["stops"]), "seed": int(r["seed"]), "time_min": float(r["time_min"]), "distance_km": float(r["distance_km"]),
                 "delay_min": float(r["delay_min"]), "overload": float(r["overload"])} for r in csv.DictReader(args.from_csv.open(encoding="utf-8"))]
        report(rows)
        return
    jobs = [(n, FIRST_SEED + k) for n in sorted(SIZES, reverse=True) for k in range(args.instances)]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for chunk in pool.map(run, jobs, chunksize=1) for row in chunk]
    print(f"[{time.perf_counter() - started:.0f} s wall, {args.workers} processes]")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda r: (r["solver"], r["stops"], r["seed"], list(SETTINGS).index(r["setting"]))))
    report(rows)


if __name__ == "__main__":
    main()
