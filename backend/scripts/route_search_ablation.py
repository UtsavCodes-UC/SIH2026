"""
Which parts of the route search matter, and how fast and how general is it? See docs/BENCHMARKS.md, Finding 13.

  operators   local search only, from the nearest-neighbour routes, with different sets of moves (and the older
              polish `improve_routes` for comparison): mean cost, gap to the OR-Tools reference, time per instance.
  tuning      iterated local search settings (ruin size, neighbour-list length, accepting slightly worse routes)
              on instances that are NOT the evaluation instances (seeds 600-609), so the settings are not fitted
              to the instances Finding 13 reports on (seeds 500-519).
  timing      seconds for the local search and per iteration of the iterated local search, at 50-200 customers.
  tours       the same search on a single-vehicle tour (one long route), against the hybrid QPSO of Finding 11
              and the OR-Tools tour reference. Slow (minutes per instance at 100 stops), so it is run in parallel.

Usage (from backend/, venv active):
    python scripts/route_search_ablation.py operators --csv results/hybrid/cvrp100_route_search_operators.csv
    python scripts/route_search_ablation.py tuning --csv results/hybrid/cvrp100_route_search_tuning.csv
    python scripts/route_search_ablation.py timing
    python scripts/route_search_ablation.py tours

`operators` and `timing` run one instance at a time so the times are not distorted by other processes; run them
on an idle machine.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.baselines.dijkstra_baseline import nearest_neighbor_order  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.local_search import improve_routes  # noqa: E402
from app.core.route_search import ALL_OPERATORS, RouteSearch  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402
from route_search_experiments import RESULTS, build, cost_of  # noqa: E402

CUSTOMERS = 100
EVALUATION_SEEDS = list(range(500, 520))
TUNING_SEEDS = list(range(600, 610))
TUNING_ITERATIONS = 200

OPERATOR_SETS = {
    "older polish (improve_routes)": None,
    "relocate": ("relocate",),
    "relocate + swap": ("relocate", "swap"),
    "relocate + swap + 2-opt": ("relocate", "swap", "two_opt"),  # the moves of the older polish
    "  + 2-opt* (= all but SWAP*)": ("relocate", "swap", "two_opt", "two_opt_star"),
    "  + SWAP* (= all but 2-opt*)": ("relocate", "swap", "two_opt", "swap_star"),
    "  + both = all five": ALL_OPERATORS,
    "all five but relocate": tuple(o for o in ALL_OPERATORS if o != "relocate"),
    "all five but swap": tuple(o for o in ALL_OPERATORS if o != "swap"),
    "all five but 2-opt": tuple(o for o in ALL_OPERATORS if o != "two_opt"),
}

TUNING_CONFIGS = {
    "default (ruin 4-12, 12 neighbours, keep only better)": dict(remove=(4, 12), neighbours=12, accept_worse=0.0),
    "smaller ruin (3-8)": dict(remove=(3, 8), neighbours=12, accept_worse=0.0),
    "larger ruin (8-20)": dict(remove=(8, 20), neighbours=12, accept_worse=0.0),
    "8 neighbours": dict(remove=(4, 12), neighbours=8, accept_worse=0.0),
    "20 neighbours": dict(remove=(4, 12), neighbours=20, accept_worse=0.0),
    "accept 0.1% worse": dict(remove=(4, 12), neighbours=12, accept_worse=0.001),
    "accept 0.3% worse": dict(remove=(4, 12), neighbours=12, accept_worse=0.003),
}


def operators_one(seed: int):
    _, _, problem = build(CUSTOMERS, seed)
    start = problem.split(nearest_neighbor_order(problem))
    out = {}
    for label, operators in OPERATOR_SETS.items():
        t = time.perf_counter()
        if operators is None:
            routes = improve_routes(problem, start)
            cost = cost_of(problem, routes)
        else:
            search = RouteSearch(problem, start, operators=operators, seed=seed)
            search.local_search()
            cost = search.cost
            assert sorted(s for r in search.result_routes() for s in r[1:-1]) == problem.request.stops
        out[label] = (cost, time.perf_counter() - t)
    return out


def tuning_one(task):
    seed, label = task
    config = TUNING_CONFIGS[label]
    _, _, problem = build(CUSTOMERS, seed)
    search = RouteSearch(problem, problem.split(nearest_neighbor_order(problem)), neighbours=config["neighbours"], seed=seed)
    search.local_search()
    started = time.perf_counter()
    search.run_ils(TUNING_ITERATIONS, remove=config["remove"], accept_worse=config["accept_worse"])
    return label, seed, search.cost, time.perf_counter() - started


def compare(ours: np.ndarray, other: np.ndarray) -> str:
    wins, losses = int((ours < other - 1e-6).sum()), int((other < ours - 1e-6).sum())
    return f"{wins}/{len(ours) - wins - losses}/{losses} p={sign_test_p_value(wins, losses):.3f}"


def run_operators(csv_path: Path | None) -> None:
    known = {int(r["instance_seed"]): float(r["cost"]) for r in csv.DictReader((RESULTS / "hybrid" / "cvrp100_best_known.csv").open(encoding="utf-8"))}
    reference = np.array([known[s] for s in EVALUATION_SEEDS])
    rows = [operators_one(seed) for seed in EVALUATION_SEEDS]
    cost = {label: np.array([r[label][0] for r in rows]) for label in OPERATOR_SETS}
    seconds = {label: np.mean([r[label][1] for r in rows]) for label in OPERATOR_SETS}
    base = cost["older polish (improve_routes)"]
    print(f"local search only, from nearest neighbour, {len(EVALUATION_SEEDS)} instances (seeds {EVALUATION_SEEDS[0]}-{EVALUATION_SEEDS[-1]}), 100 customers")
    print(f"{'moves':<34}{'mean cost':>10}{'vs OR-Tools':>13}{'seconds':>9}   wins/ties/losses against the older polish")
    for label in OPERATOR_SETS:
        gap = 100 * np.mean((cost[label] - reference) / reference)
        versus = "" if label == "older polish (improve_routes)" else compare(cost[label], base)
        print(f"{label:<34}{cost[label].mean():>10.0f}{gap:>+12.1f}%{seconds[label]:>9.2f}   {versus}")
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["moves", "instance_seed", "cost", "seconds"])
            for label in OPERATOR_SETS:
                for seed, row in zip(EVALUATION_SEEDS, rows):
                    writer.writerow([label.strip(), seed, f"{row[label][0]:.4f}", f"{row[label][1]:.3f}"])


def run_tuning(csv_path: Path | None, workers: int) -> None:
    tasks = [(seed, label) for label in TUNING_CONFIGS for seed in TUNING_SEEDS]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(tuning_one, tasks, chunksize=1))
    print(f"ILS {TUNING_ITERATIONS} iterations from nearest neighbour on {len(TUNING_SEEDS)} tuning instances (seeds {TUNING_SEEDS[0]}-{TUNING_SEEDS[-1]}, none of them evaluation instances)")
    default = list(TUNING_CONFIGS)[0]
    base = np.array([r[2] for r in sorted(rows, key=lambda r: r[1]) if r[0] == default])
    for label in TUNING_CONFIGS:
        mine = np.array([r[2] for r in sorted(rows, key=lambda r: r[1]) if r[0] == label])
        seconds = np.mean([r[3] for r in rows if r[0] == label])
        change = 100 * (base.mean() - mine.mean()) / base.mean()
        print(f"  {label:<54}{mine.mean():>9.1f}  {change:>+6.2f}% vs default  {seconds:>5.1f} s   " + ("" if label == default else compare(mine, base)))
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["setting", "instance_seed", "cost", "seconds"])
            for label, seed, cost, seconds in sorted(rows, key=lambda r: (list(TUNING_CONFIGS).index(r[0]), r[1])):
                writer.writerow([label, seed, f"{cost:.4f}", f"{seconds:.2f}"])


def run_timing() -> None:
    print("one instance per size (seed 500; capacity 100, demands 5-25, fleet for 85% utilisation, about 6 stops per van)")
    for n in (50, 100, 150, 200):
        _, _, problem = build(n, 500)
        start = problem.split(nearest_neighbor_order(problem))
        t = time.perf_counter()
        search = RouteSearch(problem, start, seed=1)
        setup = time.perf_counter() - t
        t = time.perf_counter()
        search.local_search()
        local = time.perf_counter() - t
        t = time.perf_counter()
        search.run_ils(100)
        per_iteration = (time.perf_counter() - t) / 100
        print(f"  {n:>3} customers: setup {setup:.2f} s, local search from nearest neighbour {local:.2f} s, one ILS iteration {1000 * per_iteration:.0f} ms")


def tour_one(task):
    n, seed, iterations = task
    graph = generate_synthetic_graph(n_nodes=2 * n, seed=seed)
    problem = RoutingProblem(graph, RouteRequest(depot=0, stops=list(range(1, n + 1))))
    started = time.perf_counter()
    search = RouteSearch(problem, [nearest_neighbor_order(problem)], seed=seed)
    search.local_search()
    local = search.cost
    search.run_ils(iterations)
    return seed, local, search.cost, time.perf_counter() - started


def run_tours(workers: int) -> None:
    print("single-vehicle tours (the instances of Finding 11, seeds 300-319): nearest neighbour -> route search -> ILS 1000")
    for n in (50, 100):
        reference = {int(r["instance_seed"]): float(r["cost"]) for r in csv.DictReader((RESULTS / "hybrid" / f"tsp{n}_best_known.csv").open(encoding="utf-8"))}
        hybrid = {int(r["instance_seed"]): float(r["polished_cost"]) for r in csv.DictReader((RESULTS / "hybrid" / f"tsp{n}.csv").open(encoding="utf-8")) if r["variant"] == "h_qpso"}
        started = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(tour_one, [(n, 300 + k, 1000) for k in range(20)], chunksize=1))
        seeds = [r[0] for r in rows]
        ref = np.array([reference[s] for s in seeds])
        local, ils, hyb = np.array([r[1] for r in rows]), np.array([r[2] for r in rows]), np.array([hybrid[s] for s in seeds])
        print(f"  {n:>3} stops ({time.perf_counter() - started:.0f} s wall, {workers} processes; {np.mean([r[3] for r in rows]):.0f} s per instance): "
              f"local search {local.mean():7.1f} ({100 * np.mean((local - ref) / ref):+.1f}%), ILS 1000 {ils.mean():7.1f} ({100 * np.mean((ils - ref) / ref):+.1f}%), "
              f"hybrid QPSO {hyb.mean():7.1f} ({100 * np.mean((hyb - ref) / ref):+.1f}%), OR-Tools {ref.mean():7.1f}; "
              f"ILS better than the hybrid on {int((ils < hyb - 1e-6).sum())}/20, better than OR-Tools on {int((ils < ref - 1e-6).sum())}/20")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["operators", "tuning", "timing", "tours"])
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--workers", type=int, default=4, help="tuning and tours")
    args = parser.parse_args()
    if args.mode == "operators":
        run_operators(args.csv)
    elif args.mode == "tuning":
        run_tuning(args.csv, args.workers)
    elif args.mode == "timing":
        run_timing()
    else:
        run_tours(args.workers)


if __name__ == "__main__":
    main()
