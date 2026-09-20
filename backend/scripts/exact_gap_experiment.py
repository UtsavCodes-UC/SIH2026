"""
How far from the exact optimum are the solvers on small problems, with the current code? See docs/BENCHMARKS.md, Finding 20.

The exact optimum comes from `app/core/baselines/exact_cvrp.py` (validated against exhaustive search): it minimizes exactly what
the solvers minimize, driving minutes + 1000 x overload, over at most `n_vehicles` routes. Every solver runs through
`app.services.solver.solve`, as POST /optimize runs it, and its raw and finished results are re-scored the same way.

    A  the app's problem: several vans with capacities, 10 / 12 / 14 stops, fleet for 85% utilisation, demands 5-25
         qpso, pso, ga   the app's settings: 40 x 800, warm start, polish (raw = before the polish, finished = after)
         qpso cold       the same without the warm start
         nn              nearest neighbour (raw) and nearest neighbour + polish (finished)
         search          the route search, 3 s
    B  one van, no capacities, a plain tour (the classic small case with a Held-Karp optimum): 12 / 16 stops
         qpso, pso, ga cold and qpso warm; raw and polished (2-opt); and the route search (3 s)

30 random instances per size on the app's synthetic road network (80 intersections, 8 km, random congestion), one seed per
instance, the same instance for every method. Gap = 100 x (cost - optimum) / optimum; 0 means it found the optimum.

Usage (from backend/, venv active):
    python scripts/exact_gap_experiment.py --csv results/exact_gap/gaps.csv
    python scripts/exact_gap_experiment.py --from-csv results/exact_gap/gaps.csv
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.baselines.exact_cvrp import exact_solve  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402
from app.services.solver import solve  # noqa: E402

INSTANCES = 30
FIRST_SEED = 1200
CAPACITY, UTILIZATION = 100.0, 0.85
SWARM = dict(n_particles=40, n_iterations=800)
# (label, algorithm, options, which stages to report)
METHODS_A = [
    ("qpso", "qpso", dict(SWARM, polish=True, warm_start=True), ("raw", "finished")),
    ("pso", "pso", dict(SWARM, polish=True, warm_start=True), ("raw", "finished")),
    ("ga", "ga", dict(SWARM, polish=True, warm_start=True), ("raw", "finished")),
    ("qpso cold", "qpso", dict(SWARM, polish=True, warm_start=False), ("raw", "finished")),
    ("nearest neighbour", "nearest_neighbor", dict(n_particles=1, n_iterations=1, polish=True), ("raw", "finished")),
    ("route search 3 s", "route_search", dict(n_particles=1, n_iterations=1, polish=False, time_limit_sec=3.0), ("finished",)),
]
METHODS_B = [
    ("qpso cold", "qpso", dict(SWARM, polish=True, warm_start=False), ("raw", "finished")),
    ("pso cold", "pso", dict(SWARM, polish=True, warm_start=False), ("raw", "finished")),
    ("ga cold", "ga", dict(SWARM, polish=True, warm_start=False), ("raw", "finished")),
    ("qpso warm", "qpso", dict(SWARM, polish=True, warm_start=True), ("raw", "finished")),
    ("route search 3 s", "route_search", dict(n_particles=1, n_iterations=1, polish=False, time_limit_sec=3.0), ("finished",)),
]
EXPERIMENTS = {"A": ((10, 12, 14), METHODS_A), "B": ((12, 16), METHODS_B)}
FIELDS = ["experiment", "stops", "seed", "vehicles", "method", "stage", "cost", "optimum", "gap_pct", "seconds"]


def build(experiment: str, n_stops: int, seed: int):
    graph = generate_synthetic_graph(n_nodes=80, area_size_km=8.0, seed=seed)
    rng = random.Random(seed)
    nodes = list(graph.graph.nodes)
    depot = nodes[0]
    stops = rng.sample([n for n in nodes if n != depot], n_stops)
    if experiment == "B":
        return graph, RouteRequest(depot=depot, stops=stops, n_vehicles=1)
    demands = {s: rng.randint(5, 25) for s in stops}
    fleet = max(1, math.ceil(sum(demands.values()) / (UTILIZATION * CAPACITY)))
    return graph, RouteRequest(depot=depot, stops=stops, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=fleet)


def score(problem: RoutingProblem, result) -> float:
    routes = split_at_depot(result.best_route, problem.request.depot)
    return problem.penalized_cost(problem.evaluate_routes(routes))


def run(job):
    experiment, n_stops, seed = job
    graph, request = build(experiment, n_stops, seed)
    optimum = exact_solve(RoutingProblem(graph, request)).cost
    rows = []
    for label, algorithm, options, stages in EXPERIMENTS[experiment][1]:
        started = time.perf_counter()
        solution = solve(graph, request, algorithm, seed=seed, **options)
        seconds = round(time.perf_counter() - started, 2)
        assert sorted(s for r in split_at_depot(solution.final.best_route, request.depot) for s in r[1:-1]) == sorted(request.stops), "a stop was lost or repeated"
        for stage in stages:
            cost = score(solution.problem, solution.raw if stage == "raw" else solution.final)
            assert cost >= optimum - 1e-6, f"{label} {stage} beat the exact optimum: {cost} < {optimum}"
            rows.append({
                "experiment": experiment, "stops": n_stops, "seed": seed, "vehicles": request.n_vehicles, "method": label, "stage": stage,
                "cost": round(cost, 4), "optimum": round(optimum, 4), "gap_pct": round(100 * (cost - optimum) / optimum, 4), "seconds": seconds,
            })
    return rows


def summarize(rows) -> None:
    for experiment, (sizes, methods) in EXPERIMENTS.items():
        for n_stops in sizes:
            sub = [r for r in rows if r["experiment"] == experiment and int(r["stops"]) == n_stops]
            if not sub:
                continue
            instances = sorted({int(r["seed"]) for r in sub})
            vans = statistics.mean(int(r["vehicles"]) for r in sub if r["method"] == methods[0][0] and r["stage"] == "finished")
            what = "the app's problem, several vans" if experiment == "A" else "one van, a plain tour"
            print(f"\n{experiment}: {n_stops} stops, {what} ({len(instances)} instances, {vans:.1f} vans on average)")
            print(f"  {'method':<20}{'stage':<10}{'optimal':>9}{'mean gap':>10}{'median':>8}{'worst':>8}")
            by = {}
            for label, _, _, stages in methods:
                for stage in stages:
                    cells = {int(r["seed"]): float(r["gap_pct"]) for r in sub if r["method"] == label and r["stage"] == stage}
                    by[(label, stage)] = cells
                    gaps = list(cells.values())
                    print(
                        f"  {label:<20}{stage:<10}{sum(g <= 1e-6 for g in gaps):>5}/{len(gaps):<3}{statistics.mean(gaps):>9.2f}%{statistics.median(gaps):>7.2f}%{max(gaps):>7.1f}%"
                    )
            first = "qpso" if experiment == "A" else "qpso cold"
            for other in [m[0] for m in methods if m[0] not in (first, "qpso cold", "qpso warm", "qpso")]:
                for stage in ("raw", "finished"):
                    a, b = by.get((first, stage)), by.get((other, stage))
                    if not a or not b:
                        continue
                    wins = sum(a[s] < b[s] - 1e-9 for s in a)
                    losses = sum(a[s] > b[s] + 1e-9 for s in a)
                    print(f"    {first} vs {other:<18}{stage:<9} better on {wins}, worse on {losses}, level on {len(a) - wins - losses}   p(better)={sign_test_p_value(wins, losses):.3f}  p(worse)={sign_test_p_value(losses, wins):.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path)
    args = parser.parse_args()

    if args.from_csv:
        summarize(list(csv.DictReader(args.from_csv.open())))
        return
    jobs = [(e, n, FIRST_SEED + i) for e, (sizes, _) in EXPERIMENTS.items() for n in sizes for i in range(INSTANCES)]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for batch in pool.map(run, jobs) for row in batch]
    print(f"{len(jobs)} instances, {time.perf_counter() - started:.0f} s")
    summarize(rows)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
