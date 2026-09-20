"""
How far from optimal are we? The CVRPLIB "X" instances with 100-200 customers, every one with a proven optimal cost.
See docs/BENCHMARKS.md, Finding 14. Fetch the data first: python scripts/fetch_cvrplib.py

Two pipelines per instance, both run through the same adapter (`app/data/cvrplib.py`) that scores exactly as the
benchmark does (rounded Euclidean distances):

    app default   warm-started QPSO (40 particles x 800 iterations), then the older polish `improve_routes`:
                  what the app did before Finding 13
    route search  nearest neighbour -> `RouteSearch` local search -> iterated local search, read at cumulative
                  time budgets (seconds of ILS)

The fleet allowed is ceil(1.25 x k) + 2 vans (`default_fleet`), where k (from the instance name) is the fewest vans
that can carry the demand; the script checks that the optimal solution itself fits in that fleet, so the limit never
excludes it.
Every final answer is re-scored from the coordinates and re-checked (each customer once, capacity, fleet) without
using any solver's own bookkeeping.

Time budgets make the numbers depend on how loaded the machine is (the runs share it), so they reproduce to within
a fraction of a percent, not exactly.

Usage (from backend/, venv active):
    python scripts/cvrplib_benchmark.py --csv results/cvrplib/x_100_200.csv
    python scripts/cvrplib_benchmark.py --from-csv results/cvrplib/x_100_200.csv       # just print the tables

The OR-Tools column (guided local search, 60 s, cost matrix as data, the reference of Findings 12-13) comes from
results/cvrplib/x_100_200_ortools.csv when it exists; make it with scripts/ortools_reference.py (`--problem cvrplib`).
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.baselines.dijkstra_baseline import nearest_neighbor_order  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.local_search import polish_result  # noqa: E402
from app.core.qpso import QPSO  # noqa: E402
from app.core.route_search import RouteSearch  # noqa: E402
from app.core.vrp_formulation import split_at_depot  # noqa: E402
from app.data.cvrplib import build_problem, check_solution, default_fleet, load_instance, load_solution, solution_cost  # noqa: E402
from fetch_cvrplib import CATALOGUE, DATA  # noqa: E402

BUDGETS = (10, 30, 60, 120)  # cumulative seconds of iterated local search


def customers_of(routes):
    """[depot, ..., depot] route lists -> lists of customers only."""
    return [r[1:-1] for r in routes if len(r) > 2]


def rescore(instance, routes, fleet: int) -> int:
    """Cost of a solver's routes from the coordinates, after checking they are a valid solution."""
    plain = customers_of(routes)
    check_solution(instance, plain, max_vehicles=fleet)
    return solution_cost(instance, plain)


def run_route_search(name: str, budgets, seed: int = 1) -> dict:
    instance = load_instance(DATA / f"{name}.vrp")
    fleet = default_fleet(instance)
    optimal_routes, optimal = load_solution(DATA / f"{name}.sol")
    assert len(optimal_routes) <= fleet, f"{name}: the optimal solution needs {len(optimal_routes)} vans, fleet is {fleet}"
    _, _, problem = build_problem(instance, fleet)

    row = {"instance": name, "customers": instance.n_customers, "k": instance.min_vehicles, "capacity": instance.capacity,
           "fleet": fleet, "optimal": optimal, "optimal_routes": len(optimal_routes)}
    t0 = time.perf_counter()
    search = RouteSearch(problem, problem.split(nearest_neighbor_order(problem)), seed=seed)
    row["start_cost"] = rescore(instance, search.result_routes(), fleet)
    search.local_search()
    row["ls_seconds"] = round(time.perf_counter() - t0, 2)
    row["ls_cost"] = rescore(instance, search.result_routes(), fleet)
    assert search.cost == row["ls_cost"], "the search's own cost differs from the recomputed one"

    spent, iterations = 0.0, 0
    for budget in budgets:
        t1 = time.perf_counter()
        trace = search.run_ils(10**9, max_seconds=max(0.0, budget - spent))
        spent += time.perf_counter() - t1
        iterations += len(trace)
        row[f"ils_cost_{budget}s"] = rescore(instance, search.result_routes(), fleet)
        assert search.cost == row[f"ils_cost_{budget}s"], "the search's own cost differs from the recomputed one"
        row[f"ils_iterations_{budget}s"] = iterations
    row["routes_used"] = len(customers_of(search.result_routes()))
    return row


def run_app_default(name: str) -> dict:
    instance = load_instance(DATA / f"{name}.vrp")
    fleet = default_fleet(instance)
    graph, request, problem = build_problem(instance, fleet)
    t0 = time.perf_counter()
    raw = QPSO(graph, request, warm_start=True, seed=1).run()
    polished = polish_result(problem, raw, 1000.0, inter_route=True)
    seconds = time.perf_counter() - t0
    return {"instance": name, "app_seconds": round(seconds, 2),
            "app_raw_cost": rescore(instance, split_at_depot(raw.best_route, 0), fleet),
            "app_cost": rescore(instance, split_at_depot(polished.best_route, 0), fleet)}


def task(job):
    kind, name, budgets = job
    return run_route_search(name, budgets) if kind == "search" else run_app_default(name)


def write_csv(path: Path, rows, budgets) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["instance", "customers", "k", "capacity", "fleet", "optimal", "optimal_routes", "app_raw_cost", "app_cost", "app_seconds",
              "start_cost", "ls_cost", "ls_seconds"] + [f"ils_cost_{b}s" for b in budgets] + [f"ils_iterations_{b}s" for b in budgets] + ["routes_used"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_csv(path: Path):
    rows = []
    for r in csv.DictReader(path.open(encoding="utf-8")):
        rows.append({k: (float(v) if k not in ("instance",) else v) for k, v in r.items()})
    budgets = tuple(int(k[len("ils_cost_"):-1]) for k in rows[0] if k.startswith("ils_cost_"))
    return rows, budgets


def report(rows, budgets, ortools: Path | None = None) -> None:
    columns = [("app default", "app_cost"), ("nn start", "start_cost"), ("local search", "ls_cost")] + [(f"ILS {b} s", f"ils_cost_{b}s") for b in budgets]
    if ortools is not None and ortools.exists():
        known = {r["instance"]: float(r["cost"]) for r in csv.DictReader(ortools.open(encoding="utf-8"))}
        if all(r["instance"] in known for r in rows):
            for r in rows:
                r["ortools_cost"] = known[r["instance"]]
            columns.insert(1, ("OR-Tools 60 s", "ortools_cost"))
    gap = lambda row, key: 100.0 * (row[key] - row["optimal"]) / row["optimal"]  # noqa: E731
    print(f"{len(rows)} CVRPLIB X instances, {int(min(r['customers'] for r in rows))}-{int(max(r['customers'] for r in rows))} customers, all with a proven optimal cost; % above optimal")
    print(f"{'instance':<12}{'stops/van':>10}{'optimal':>9}" + "".join(f"{label:>14}" for label, _ in columns) + f"{'ILS its/s':>11}")
    last = budgets[-1]
    for r in rows:
        rate = r[f"ils_iterations_{last}s"] / (last + r["ls_seconds"])
        print(f"{r['instance']:<12}{r['customers'] / r['k']:>10.1f}{r['optimal']:>9.0f}" + "".join(f"{gap(r, key):>13.2f}%" for _, key in columns) + f"{rate:>11.0f}")

    print()
    for label, fn in (("mean", statistics.fmean), ("median", statistics.median), ("worst", max), ("best", min)):
        print(f"{label:<31}" + "".join(f"{fn(gap(r, key) for r in rows):>13.2f}%" for _, key in columns))
    print()
    for limit in (1, 2, 5):
        print(f"{'within ' + str(limit) + '% of optimal':<31}" + "".join(f"{str(sum(gap(r, key) <= limit for r in rows)) + '/' + str(len(rows)):>14}" for _, key in columns))

    if "ortools_cost" in rows[0]:
        print("\nagainst OR-Tools 60 s, per instance (wins/ties/losses of the row's cost against it; mean cost difference, negative = cheaper than OR-Tools; sign test on the row being cheaper):")
        for label, key in columns:
            if key == "ortools_cost":
                continue
            wins = sum(r[key] < r["ortools_cost"] for r in rows)
            losses = sum(r[key] > r["ortools_cost"] for r in rows)
            difference = statistics.fmean(100.0 * (r[key] - r["ortools_cost"]) / r["ortools_cost"] for r in rows)
            print(f"  {label:<14}{wins}/{len(rows) - wins - losses}/{losses}   {difference:+.2f}%   p = {sign_test_p_value(wins, losses):.4f}")
    print("\nmean gap by route length (customers per van in the optimal solution's fleet size k):")
    groups = (("short (< 6)", lambda s: s < 6), ("medium (6-13)", lambda s: 6 <= s <= 13), ("long (> 13)", lambda s: s > 13))
    for label, keep in groups:
        subset = [r for r in rows if keep(r["customers"] / r["k"])]
        if not subset:
            continue
        cells = "".join(f"{statistics.fmean(gap(r, key) for r in subset):>13.2f}%" for _, key in columns)
        rate = statistics.fmean(r[f"ils_iterations_{last}s"] / (last + r["ls_seconds"]) for r in subset)
        print(f"{label + f' n={len(subset)}':<31}{cells}{rate:>11.0f}")

    print(f"\nlocal search from nearest neighbour takes {statistics.fmean(r['ls_seconds'] for r in rows):.2f} s on average (worst {max(r['ls_seconds'] for r in rows):.2f} s); "
          f"the app default takes {statistics.fmean(r['app_seconds'] for r in rows):.1f} s (worst {max(r['app_seconds'] for r in rows):.1f} s)")
    extra = statistics.fmean(r["routes_used"] - r["optimal_routes"] for r in rows)
    print(f"vans used by the ILS solution minus vans in the optimal solution: {extra:+.2f} on average")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--budgets", type=int, nargs="+", default=list(BUDGETS), help="cumulative seconds of ILS to read the cost at")
    parser.add_argument("--only", nargs="+", help="instance names, default all fetched ones")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path)
    parser.add_argument("--ortools", type=Path, default=Path(__file__).resolve().parent.parent / "results" / "cvrplib" / "x_100_200_ortools.csv")
    args = parser.parse_args()

    if args.from_csv:
        report(*read_csv(args.from_csv), ortools=args.ortools)
        return
    names = args.only or [n for n in CATALOGUE if (DATA / f"{n}.vrp").exists() and (DATA / f"{n}.sol").exists()]
    if not names:
        raise SystemExit("no instances found: run scripts/fetch_cvrplib.py first")
    budgets = tuple(args.budgets)
    jobs = [("search", n, budgets) for n in names] + [("app", n, budgets) for n in names]  # the long jobs first
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(task, jobs, chunksize=1))
    merged = {}
    for r in results:
        merged.setdefault(r["instance"], {}).update(r)
    rows = [merged[n] for n in names]
    print(f"[{time.perf_counter() - started:.0f} s wall, {args.workers} processes]")
    out = args.csv or Path(__file__).resolve().parent.parent / "results" / "cvrplib" / "_tmp.csv"
    write_csv(out, rows, budgets)
    report(*read_csv(out), ortools=args.ortools)
    if not args.csv:
        out.unlink()


if __name__ == "__main__":
    main()
