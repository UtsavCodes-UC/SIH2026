"""
Do QPSO, PSO or GA add anything once the multi-vehicle search has strong between-route moves?
See docs/BENCHMARKS.md, Finding 13.

Every pipeline ends with the same route search (`app/core/route_search.py`: relocate, swap, 2-opt*, SWAP*, 2-opt on
a stop's nearest neighbours, then iterated local search), with the same random stream, on the same instances. They
differ only in the routes it starts from:

    nn      nearest neighbour
    pso     warm-started classical PSO (40 particles x 800 iterations), decoded with the greedy split
    qpso    warm-started QPSO, same budget
    ga      warm-started genetic algorithm, same budget

The swarm phase costs wall-clock time that `nn` does not spend, so `nn` is also read at a later iteration, the one
that matches each swarm run's extra time ("nn, time-matched"): the fair control for "is the swarm worth its time?".
The OR-Tools column (if a reference CSV exists) is guided local search with the cost matrix handed over as data.

Usage (from backend/, venv active):
    python scripts/route_search_experiments.py --instances 20 --csv results/hybrid/cvrp100_route_search.csv
    python scripts/route_search_experiments.py --from-csv results/hybrid/cvrp100_route_search.csv   # just print the tables
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.baselines.classical_pso import ClassicalPSO  # noqa: E402
from app.core.baselines.dijkstra_baseline import nearest_neighbor_order  # noqa: E402
from app.core.baselines.genetic_algorithm import GeneticAlgorithm  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.qpso import QPSO  # noqa: E402
from app.core.route_search import RouteSearch  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402

CAPACITY = 100
RESULTS = Path(__file__).resolve().parent.parent / "results"
PIPELINES = ("nn", "pso", "qpso", "ga")
CHECKPOINTS = (0, 100, 200, 500, 1000)  # ILS iterations (0 = local search only)
CONTROL_EXTRA = 600  # how far past the last checkpoint the nn run continues, for the time-matched control
STORED = tuple(range(100, CHECKPOINTS[-1] + CONTROL_EXTRA + 1, 100))  # every 100th iteration of the trace goes to the CSV


def build(n: int, seed: int):
    graph = generate_synthetic_graph(n_nodes=2 * n, seed=seed)
    rng = random.Random(seed)
    stops = list(range(1, n + 1))
    demands = {c: rng.randint(5, 25) for c in stops}
    fleet = math.ceil(sum(demands.values()) / (0.85 * CAPACITY))
    request = RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=fleet)
    return graph, request, RoutingProblem(graph, request)


def cost_of(problem: RoutingProblem, routes) -> float:
    e = problem.evaluate_routes(routes)
    return e.total_time_min + 1000.0 * e.capacity_violation


def run_task(task):
    pipeline, n, seed, iterations = task
    graph, request, problem = build(n, seed)
    t0 = time.perf_counter()
    if pipeline == "nn":
        routes = problem.split(nearest_neighbor_order(problem))
    else:
        swarm = {
            "pso": lambda: ClassicalPSO(graph, request, warm_start=True, seed=1),
            "qpso": lambda: QPSO(graph, request, warm_start=True, seed=1),
            "ga": lambda: GeneticAlgorithm(graph, request, warm_start=True, seed=1),
        }[pipeline]()
        routes = split_at_depot(swarm.run().best_route, request.depot)
    start_seconds = time.perf_counter() - t0
    start_cost = cost_of(problem, routes)

    search = RouteSearch(problem, routes, seed=seed)
    t1 = time.perf_counter()
    search.local_search()
    after_ls = search.cost
    ls_seconds = time.perf_counter() - t1
    total = iterations + (CONTROL_EXTRA if pipeline == "nn" else 0)
    t2 = time.perf_counter()
    trace = search.run_ils(total)
    ils_seconds = time.perf_counter() - t2
    final = search.result_routes()
    evaluation = problem.evaluate_routes(final)  # from scratch, independent of the search's incremental bookkeeping
    valid = (
        sorted(s for r in final for s in r[1:-1]) == request.stops  # every customer exactly once
        and evaluation.capacity_violation == 0 and len(final) <= request.n_vehicles
        and abs(evaluation.total_time_min - trace[-1]) < 1e-6  # the cost the search reports is the cost of these routes
    )
    return {
        "pipeline": pipeline, "seed": seed, "start_cost": start_cost, "start_seconds": start_seconds, "after_ls": after_ls,
        "ls_seconds": ls_seconds, "seconds_per_iteration": ils_seconds / max(1, len(trace)), "trace": trace,
        "final_routes_valid": valid,
    }


def trace_at(row, checkpoint: int) -> float:
    return row["after_ls"] if checkpoint == 0 else row["trace"][min(checkpoint, len(row["trace"])) - 1]


def write_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pipeline", "instance_seed", "start_cost", "start_seconds", "after_local_search", "seconds_per_ils_iteration"] + [f"cost_after_{c}_ils_iterations" for c in STORED] + ["nn_time_matched_extra_iterations"])
        by_seed_nn = {r["seed"]: r for r in rows if r["pipeline"] == "nn"}
        for r in sorted(rows, key=lambda r: (r["pipeline"], r["seed"])):
            extra = matched_iterations(r, by_seed_nn[r["seed"]]) if r["pipeline"] != "nn" else 0
            writer.writerow([r["pipeline"], r["seed"], f"{r['start_cost']:.4f}", f"{r['start_seconds']:.2f}", f"{r['after_ls']:.4f}", f"{r['seconds_per_iteration']:.4f}"] + [f"{trace_at(r, c):.4f}" if c <= len(r["trace"]) else "" for c in STORED] + [extra])


def matched_iterations(row, nn_row) -> int:
    """How many more ILS iterations nearest neighbour gets to spend the time the swarm phase used."""
    return int(round(row["start_seconds"] / max(nn_row["seconds_per_iteration"], 1e-9)))


def read_csv(path: Path):
    rows = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        rows.setdefault(r["pipeline"], {})[int(r["instance_seed"])] = r
    return rows


def compare(ours: np.ndarray, other: np.ndarray) -> str:
    wins, losses = int((ours < other - 1e-6).sum()), int((other < ours - 1e-6).sum())
    return f"{wins}/{len(ours) - wins - losses}/{losses} {100 * np.mean((other - ours) / other):+.1f}% p={sign_test_p_value(wins, losses):.3f}"


def report(rows_by_pipeline, reference_path: Path | None) -> None:
    seeds = sorted(rows_by_pipeline["nn"])
    reference = None
    if reference_path and reference_path.exists():
        known = {int(r["instance_seed"]): float(r["cost"]) for r in csv.DictReader(reference_path.open(encoding="utf-8"))}
        reference = np.array([known[s] for s in seeds])

    def stored(checkpoint):
        return checkpoint == 0 or all(rows_by_pipeline[p][s][f"cost_after_{checkpoint}_ils_iterations"] != "" for p in PIPELINES for s in seeds)

    shown = [c for c in CHECKPOINTS if stored(c)]  # a short run has fewer checkpoints than the default one

    def costs(pipeline, checkpoint):
        if checkpoint == 0:
            return np.array([float(rows_by_pipeline[pipeline][s]["after_local_search"]) for s in seeds])
        return np.array([float(rows_by_pipeline[pipeline][s][f"cost_after_{checkpoint}_ils_iterations"]) for s in seeds])

    print(f"\n{len(seeds)} instances (seeds {seeds[0]}-{seeds[-1]}); mean cost, and % above the OR-Tools reference where there is one")
    print(f"{'starting routes from':<26}" + "".join(f"{('LS only' if c == 0 else f'ILS {c}'):>16}" for c in shown) + f"{'start s':>9}")
    for pipeline in PIPELINES:
        cells = []
        for c in shown:
            mean = costs(pipeline, c).mean()
            gap = f" ({100 * np.mean((costs(pipeline, c) - reference) / reference):+.1f}%)" if reference is not None else ""
            cells.append(f"{mean:>9.0f}{gap:>7}")
        secs = np.mean([float(rows_by_pipeline[pipeline][s]["start_seconds"]) for s in seeds])
        print(f"{pipeline:<26}" + "".join(f"{cell:>16}" for cell in cells) + f"{secs:>9.1f}")
    if reference is not None:
        print(f"{'OR-Tools (matrix costs)':<26}{reference.mean():>9.0f}   (60 s)")
        print("\ninstances better than the OR-Tools reference:")
        for pipeline in PIPELINES:
            print(f"  {pipeline:<6}" + "".join(f"   {('LS only' if c == 0 else f'ILS {c}')}: {int((costs(pipeline, c) < reference - 1e-6).sum())}/{len(seeds)}" for c in shown))

    print("\nwin/tie/loss and mean improvement of each swarm pipeline against nearest neighbour, same ILS iterations:")
    for pipeline in ("pso", "qpso", "ga"):
        print(f"  {pipeline:<6}" + "".join(f"   ILS {c:>4}: {compare(costs(pipeline, c), costs('nn', c))}" for c in shown[1:]))
    print("\nagainst nearest neighbour given the swarm's running time as extra ILS iterations (time-matched control):")
    for pipeline in ("pso", "qpso", "ga"):
        parts = []
        for c in shown[1:]:
            control = []
            for s in seeds:
                extra = int(rows_by_pipeline[pipeline][s]["nn_time_matched_extra_iterations"])
                # the first stored iteration at or after c + extra (rounding up favours nearest neighbour)
                later = next((k for k in STORED if k >= c + extra and rows_by_pipeline["nn"][s][f"cost_after_{k}_ils_iterations"] != ""), max(k for k in STORED if rows_by_pipeline["nn"][s][f"cost_after_{k}_ils_iterations"] != ""))
                control.append(float(rows_by_pipeline["nn"][s][f"cost_after_{later}_ils_iterations"]))
            parts.append(f"   ILS {c:>4}: {compare(costs(pipeline, c), np.array(control))}")
        print(f"  {pipeline:<6}" + "".join(parts))
    extras = [int(rows_by_pipeline["qpso"][s]["nn_time_matched_extra_iterations"]) for s in seeds]
    print(f"\n(the swarm phase takes as long as about {np.mean(extras):.0f} ILS iterations; nn is read at the next stored 100-iteration step at or after that, which favours nn)")
    print("\nqpso vs pso, same starting budget:  " + "  ".join(f"ILS {c}: {compare(costs('qpso', c), costs('pso', c))}" for c in shown[1:]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customers", type=int, default=100)
    parser.add_argument("--instances", type=int, default=20)
    parser.add_argument("--first-instance-seed", type=int, default=500)
    parser.add_argument("--iterations", type=int, default=CHECKPOINTS[-1])
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path, help="print the tables from a saved run instead of running")
    parser.add_argument("--reference", type=Path, default=RESULTS / "hybrid" / "cvrp100_best_known.csv")
    args = parser.parse_args()

    if args.from_csv:
        report(read_csv(args.from_csv), args.reference)
        return

    seeds = [args.first_instance_seed + k for k in range(args.instances)]
    tasks = [(p, args.customers, s, args.iterations) for p in PIPELINES for s in seeds]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_task, tasks, chunksize=1))
    print(f"[{time.perf_counter() - t0:.0f}s wall]")
    assert all(r["final_routes_valid"] for r in rows), "an ILS result lost or repeated a stop, overloaded a van, or reported the wrong cost"
    if args.csv:
        write_csv(args.csv, rows)
        report(read_csv(args.csv), args.reference)
    else:
        tmp = RESULTS / "hybrid" / "_route_search_tmp.csv"
        write_csv(tmp, rows)
        report(read_csv(tmp), args.reference)
        tmp.unlink()


if __name__ == "__main__":
    main()
