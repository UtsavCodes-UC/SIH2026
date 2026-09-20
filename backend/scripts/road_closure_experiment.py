"""
What does closing a road cost a plan, and can the app's what-if be trusted? See docs/BENCHMARKS.md, Finding 19.

Closing a road can only make the best possible plan slower or leave it as it is. A heuristic solver can still report a
"saving", because the search is randomized and any change to the leg times sends it down a different path. So for each
instance (the app's synthetic network, random stops and demands, fleet for 85% utilisation) we

    1. plan with the app default (QPSO, warm start, polish) and with the route search (3 s);
    2. close one road that the plan drives on (a random one, never one that cuts a stop off) and plan again with the
       same settings, seed, stops and demands;
    3. plan the OPEN network once more with a different algorithm seed, which measures the run-to-run noise on its own.

"Change" is the closed plan's cost against the open plan's, in percent (cost = minutes + 1000 x overload, the app's own).
A negative change is an apparent saving from closing a road, which cannot be real.

Usage (from backend/, venv active):
    python scripts/road_closure_experiment.py --csv results/road_closures/closures.csv
    python scripts/road_closure_experiment.py --from-csv results/road_closures/closures.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.vrp_formulation import RouteRequest, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402
from app.services.closures import set_closures  # noqa: E402
from app.services.graph_store import GraphStore  # noqa: E402
from app.services.solver import solve  # noqa: E402

SIZES = (15, 30)
INSTANCES = 20
FIRST_SEED = 900
CAPACITY, UTILIZATION = 100.0, 0.85
SOLVERS = {
    "default": ("qpso", dict(n_particles=40, n_iterations=800, polish=True, warm_start=True)),
    "search": ("route_search", dict(n_particles=40, n_iterations=800, polish=False, warm_start=False, time_limit_sec=3.0)),
}
FIELDS = ["stops", "seed", "solver", "open_cost", "closed_cost", "other_seed_cost", "change_pct", "noise_pct", "closed_roads_used"]


def cost_of(stored, request, solver, seed):
    algorithm, kwargs = SOLVERS[solver]
    solution = solve(stored.graph, request, algorithm, seed=seed, **kwargs)
    routes = split_at_depot(solution.final.best_route, request.depot)
    evaluation = solution.problem.evaluate_routes(routes)
    return evaluation.total_time_min + 1000.0 * evaluation.capacity_violation, routes


def roads_driven(graph, routes):
    used = set()
    for route in routes:
        for u, v in zip(route, route[1:]):
            path = graph.shortest_path(u, v)
            used |= {frozenset(p) for p in zip(path, path[1:])}
    return used


def run(job):
    n_stops, seed = job
    graph = generate_synthetic_graph(n_nodes=80, area_size_km=8.0, seed=seed)
    stored = GraphStore().add(graph, "synthetic", "experiment", (0.0, 0.0))
    rng = random.Random(seed)
    nodes = list(graph.graph.nodes)
    depot = nodes[0]
    stops = rng.sample([n for n in nodes if n != depot], n_stops)
    demands = {s: rng.randint(5, 25) for s in stops}
    fleet = max(1, math.ceil(sum(demands.values()) / (UTILIZATION * CAPACITY)))
    request = RouteRequest(depot=depot, stops=stops, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=fleet)

    rows = []
    for solver in SOLVERS:
        open_cost, routes = cost_of(stored, request, solver, seed)
        other_cost, _ = cost_of(stored, request, solver, seed + 1)
        used = sorted(roads_driven(graph, routes), key=sorted)
        rng.shuffle(used)
        for road in used:  # the first road whose closure leaves every stop reachable
            u, v = sorted(road)
            set_closures(stored, [(u, v)])
            if set(stops) <= graph.mutually_reachable(depot):
                break
            set_closures(stored, [])
        else:
            raise RuntimeError("no road of the plan can be closed")
        closed_cost, _ = cost_of(stored, request, solver, seed)
        set_closures(stored, [])
        rows.append({
            "stops": n_stops, "seed": seed, "solver": solver, "open_cost": round(open_cost, 4), "closed_cost": round(closed_cost, 4),
            "other_seed_cost": round(other_cost, 4), "change_pct": round(100 * (closed_cost - open_cost) / open_cost, 3),
            "noise_pct": round(100 * abs(other_cost - open_cost) / open_cost, 3), "closed_roads_used": len(used),
        })
    return rows


def summarize(rows):
    for n_stops in SIZES:
        for solver in SOLVERS:
            sub = [r for r in rows if r["stops"] == n_stops and r["solver"] == solver]
            change = [float(r["change_pct"]) for r in sub]
            noise = [float(r["noise_pct"]) for r in sub]
            saving = [c for c in change if c < -0.05]
            print(
                f"{n_stops:3d} stops, {solver:8s} n={len(sub)}  mean change {statistics.mean(change):+6.2f}%  median {statistics.median(change):+6.2f}%  "
                f"apparent savings {len(saving):2d}/{len(sub)} (largest {min(change):+.1f}%)  "
                f"run-to-run noise (open network, other seed) mean {statistics.mean(noise):.2f}%  max {max(noise):.1f}%"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path)
    args = parser.parse_args()

    if args.from_csv:
        summarize(list(csv.DictReader(args.from_csv.open())))
        return
    jobs = [(n, FIRST_SEED + i) for n in SIZES for i in range(INSTANCES)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for batch in pool.map(run, jobs) for row in batch]
    summarize(rows)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
