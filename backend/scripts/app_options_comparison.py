"""
The app's default solver against its new route-search option, at the problem sizes the app is used at.
See docs/BENCHMARKS.md, Finding 15.

Both run through `app.services.solver.solve`, exactly as POST /optimize runs them:

    default        QPSO (40 particles x 800 iterations) with a warm start and the polish   (what the app has always done)
    route search   nearest neighbour, local search between vans, iterated search, at each of the `--time-limits`
                   (default 1, 3 and 10 s; the UI's default is 10, and a small problem that stops improving ends sooner)

On the same synthetic road graphs, stops, demands and fleets (fleet sized for 85% utilisation, capacity 100, demands 5-25,
as the app does when left on auto), paired per instance. Cost is travel time plus 1000 x overload, the app's own.

Usage (from backend/, venv active):
    python scripts/app_options_comparison.py --csv results/app_options/route_search_vs_default.csv
    python scripts/app_options_comparison.py --from-csv results/app_options/route_search_vs_default.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.vrp_formulation import RouteRequest, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402
from app.services.solver import solve  # noqa: E402

SIZES = (15, 30, 60, 100)
FIRST_SEED = 700
CAPACITY = 100.0
UTILIZATION = 0.85


def build(n_stops: int, seed: int):
    graph = generate_synthetic_graph(n_nodes=max(80, 2 * n_stops), area_size_km=8.0, seed=seed)  # the app's default 80-node, 8 km network, grown when there are many stops
    rng = random.Random(seed)
    nodes = list(graph.graph.nodes)
    depot = nodes[0]
    stops = rng.sample([n for n in nodes if n != depot], n_stops)
    demands = {s: rng.randint(5, 25) for s in stops}
    fleet = max(1, math.ceil(sum(demands.values()) / (UTILIZATION * CAPACITY)))
    return graph, RouteRequest(depot=depot, stops=stops, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=fleet)


def run(job):
    n_stops, seed, time_limits = job
    graph, request = build(n_stops, seed)
    row = {"stops": n_stops, "seed": seed, "vehicles": request.n_vehicles}
    runs = [("default", "qpso", dict(n_particles=40, n_iterations=800, polish=True, warm_start=True))]
    runs += [(f"search{limit:g}", "route_search", dict(n_particles=40, n_iterations=800, polish=False, warm_start=False, time_limit_sec=limit)) for limit in time_limits]
    for label, algorithm, kwargs in runs:
        started = time.perf_counter()
        solution = solve(graph, request, algorithm, seed=seed, **kwargs)
        row[f"{label}_seconds"] = round(time.perf_counter() - started, 2)
        routes = split_at_depot(solution.final.best_route, request.depot)
        evaluation = solution.problem.evaluate_routes(routes)
        assert sorted(s for r in routes for s in r[1:-1]) == sorted(request.stops), "a stop was lost or repeated"
        row[f"{label}_cost"] = round(evaluation.total_time_min + 1000.0 * evaluation.capacity_violation, 4)
        row[f"{label}_overload"] = round(evaluation.capacity_violation, 4)
    return row


def labels_in(rows) -> list[str]:
    return sorted({k[: -len("_cost")] for k in rows[0] if k.endswith("_cost") and k != "default_cost"}, key=lambda name: float(name[len("search"):]))


def report(rows) -> None:
    print("route search vs the app default, paired per instance; negative % = route search cheaper")
    print(f"{'stops':>6}{'n':>4}{'default cost':>14}{'default s':>11}   {'route search':<13}{'cost':>8}{'seconds':>9}{'difference':>12}{'wins/ties/losses':>18}{'p':>8}")
    for n in sorted({r["stops"] for r in rows}):
        subset = [r for r in rows if r["stops"] == n]
        a = np.array([r["default_cost"] for r in subset])
        for k, label in enumerate(labels_in(rows)):
            b = np.array([r[f"{label}_cost"] for r in subset])
            wins, losses = int((b < a - 1e-6).sum()), int((a < b - 1e-6).sum())
            difference = statistics.fmean(100.0 * (y - x) / x for x, y in zip(a, b))
            head = f"{n:>6}{len(subset):>4}{a.mean():>14.1f}{statistics.fmean(r['default_seconds'] for r in subset):>11.1f}" if k == 0 else " " * 35
            print(f"{head}   {'limit ' + label[len('search'):] + ' s':<13}{b.mean():>8.1f}{statistics.fmean(r[f'{label}_seconds'] for r in subset):>9.1f}{difference:>+11.2f}%{f'{wins}/{len(subset) - wins - losses}/{losses}':>18}{sign_test_p_value(wins, losses):>8.3f}")
    over = [r for r in rows if any(v > 0 for k, v in r.items() if k.endswith("_overload"))]
    print(f"\ninstances where any solution overloads a van: {len(over)} of {len(rows)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--instances", type=int, default=20)
    parser.add_argument("--sizes", type=int, nargs="+", default=list(SIZES))
    parser.add_argument("--time-limits", type=float, nargs="+", default=[1.0, 3.0, 10.0])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path)
    args = parser.parse_args()

    if args.from_csv:
        rows = [{k: (int(v) if k in ("stops", "seed", "vehicles") else float(v)) for k, v in r.items()} for r in csv.DictReader(args.from_csv.open(encoding="utf-8"))]
        report(rows)
        return
    jobs = [(n, FIRST_SEED + k, tuple(args.time_limits)) for n in sorted(args.sizes, reverse=True) for k in range(args.instances)]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run, jobs, chunksize=1))
    print(f"[{time.perf_counter() - started:.0f} s wall, {args.workers} processes]")
    rows.sort(key=lambda r: (r["stops"], r["seed"]))
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    report(rows)


if __name__ == "__main__":
    main()
