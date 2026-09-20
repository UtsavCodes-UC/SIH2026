"""
Reference solutions from OR-Tools' routing solver (guided local search), behind every "% above OR-Tools" in
docs/BENCHMARKS.md. Two steps, because OR-Tools is not in the project's pinned environment (installing it can move
numpy and change the random streams the benchmarks depend on):

  1. in the project venv, write each instance's cost matrix (and demands) to a folder:
         python scripts/ortools_reference.py export --problem cvrp --stops 100 --first-seed 500 --instances 20 --dir C:/tmp/ortools_data
  2. in any environment with `pip install ortools` (a throwaway venv is fine; this step imports nothing from the app):
         python scripts/ortools_reference.py solve  --problem cvrp --stops 100 --first-seed 500 --instances 20 --dir C:/tmp/ortools_data --seconds 60 --csv results/hybrid/cvrp100_best_known.csv

`tsp` is one vehicle over `--stops` stops (instances as in Finding 11); `cvrp` is the capacitated fleet of Findings
10-12. The cost matrix and the demands are handed to OR-Tools AS DATA (RegisterTransitMatrix,
RegisterUnaryTransitVector). The first version of these references registered Python callbacks instead; the search
then spends most of its time calling back into Python, and its "best known" costs were 1.1-3.3% worse than with the
matrix (2.4% on the capacitated instances). Every gap to OR-Tools in the documentation uses the corrected references.

The cost written to the CSV is recomputed from the float matrix for the routes OR-Tools returned (the search itself
uses integer milli-minutes), so it is on exactly the same scale as our own costs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

CAPACITY, UTILIZATION = 100, 0.85


def export(args) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.core.vrp_formulation import RouteRequest, RoutingProblem
    from app.data.synthetic_graph_generator import generate_synthetic_graph

    args.dir.mkdir(parents=True, exist_ok=True)
    for seed in range(args.first_seed, args.first_seed + args.instances):
        graph = generate_synthetic_graph(n_nodes=2 * args.stops, seed=seed)  # the same instance the experiments build
        stops = list(range(1, args.stops + 1))
        payload = {}
        if args.problem == "cvrp":
            rng = random.Random(seed)
            demands = {c: rng.randint(5, 25) for c in stops}
            vehicles = math.ceil(sum(demands.values()) / (UTILIZATION * CAPACITY))
            request = RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=vehicles)
            payload = {"demands": [0, *(demands[c] for c in stops)], "vehicles": vehicles, "capacity": CAPACITY}
        else:
            request = RouteRequest(depot=0, stops=stops)
        problem = RoutingProblem(graph, request)
        nodes = [0, *stops]
        payload["matrix"] = [[0.0 if u == v else problem.leg_time(u, v) for v in nodes] for u in nodes]
        (args.dir / f"{args.problem}{args.stops}_seed{seed}.json").write_text(json.dumps(payload), encoding="utf-8")
    print(f"exported {args.instances} {args.problem} instances of {args.stops} stops to {args.dir}")


def solve_one(job):
    problem, stops, seed, directory, seconds = job
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    data = json.loads((Path(directory) / f"{problem}{stops}_seed{seed}.json").read_text(encoding="utf-8"))
    matrix = data["matrix"]
    vehicles = data.get("vehicles", 1)
    manager = pywrapcp.RoutingIndexManager(len(matrix), vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)
    # data, not callbacks: nothing in the search calls back into Python
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitMatrix([[int(round(v * 1000)) for v in row] for row in matrix]))
    if problem == "cvrp":
        demand = routing.RegisterUnaryTransitVector([int(d) for d in data["demands"]])
        routing.AddDimensionWithVehicleCapacity(demand, 0, [data["capacity"]] * vehicles, True, "capacity")

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(seconds)
    started = time.perf_counter()
    solution = routing.SolveWithParameters(params)
    elapsed = time.perf_counter() - started
    if solution is None:
        return seed, float("nan"), 0, elapsed
    total, used = 0.0, 0
    for v in range(vehicles):
        index, previous, count = routing.Start(v), 0, 0
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            total += matrix[previous][node]
            previous, count = node, count + (node != 0)
            index = solution.Value(routing.NextVar(index))
        total += matrix[previous][0]
        used += count > 0
    return seed, total, used, elapsed


def solve(args) -> None:
    seeds = range(args.first_seed, args.first_seed + args.instances)
    jobs = [(args.problem, args.stops, seed, str(args.dir), args.seconds) for seed in seeds]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(solve_one, jobs))
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["instance_seed", "cost", "vehicles_used", "seconds"])
        for seed, total, used, elapsed in results:
            writer.writerow([seed, f"{total:.4f}", used, f"{elapsed:.1f}"])
    solved = [r[1] for r in results if r[1] == r[1]]
    print(f"wrote {args.csv}: mean cost {sum(solved) / len(solved):.1f} over {len(solved)} solved instances")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "solve"):
        p = sub.add_parser(name)
        p.add_argument("--problem", choices=["tsp", "cvrp"], required=True)
        p.add_argument("--stops", type=int, default=100)
        p.add_argument("--first-seed", type=int, required=True)
        p.add_argument("--instances", type=int, default=20)
        p.add_argument("--dir", type=Path, required=True, help="where the exported instances live")
        if name == "solve":
            p.add_argument("--seconds", type=int, default=60)
            p.add_argument("--workers", type=int, default=6)
            p.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    export(args) if args.command == "export" else solve(args)


if __name__ == "__main__":
    main()
