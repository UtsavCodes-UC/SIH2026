"""
Why does QPSO fall behind classical PSO at 50-100 customers with several vehicles, and what fixes it?
See docs/BENCHMARKS.md, Finding 9 (the problem) and Finding 10 (this investigation).

Runs named algorithm variants on the same random capacitated multi-vehicle instances (customers with
demands 5-25, vehicle capacity 100, fleet sized so utilization is at most `--utilization`), in parallel,
and compares each one with classical PSO instance by instance:

    raw       what the algorithm found by itself
    +polish   the same result after the route polish (`--polish full`: 2-opt inside routes plus moving
              stops between vehicles; `--polish two_opt`: 2-opt inside each route only)

Nearest neighbour (+2-opt) is always included as a reality check: an optimizer that loses to it is
not worth its run time.

Usage (from backend/, venv active):
    python scripts/scale_experiments.py --list
    python scripts/scale_experiments.py --customers 100 --instances 10 --variants pso qpso qpso_b0.3_0.05
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
from app.core.baselines.dijkstra_baseline import nearest_neighbor  # noqa: E402
from app.core.baselines.genetic_algorithm import GeneticAlgorithm  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.local_search import polish_result  # noqa: E402
from app.core.qpso import QPSO  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402

CAPACITY = 100
PENALTY = 1000.0

# name -> (algorithm, constructor kwargs). Every metaheuristic gets the same particles x iterations budget
# unless a variant says otherwise.
VARIANTS: dict[str, tuple[str, dict]] = {
    "pso": ("pso", {}),
    "qpso": ("qpso", {}),  # current defaults: beta 1.0 -> 0.2 up to 50 stops, shrinking in proportion beyond
    "qpso_b1.0_0.2": ("qpso", {"beta_start": 1.0, "beta_end": 0.2}),  # the old fixed schedule, whatever the size
    "ga": ("ga", {}),
}
# jump-size sweep: the hypothesis is that QPSO's default jump reorders 100 random keys far too much
for start, end in [(0.5, 0.1), (0.3, 0.05), (0.15, 0.02), (0.05, 0.01)]:
    VARIANTS[f"qpso_b{start}_{end}"] = ("qpso", {"beta_start": start, "beta_end": end})

# warm start: two particles begin as the nearest-neighbour solution and its 2-opt polish (same for both algorithms)
VARIANTS["pso_warm"] = ("pso", {"warm_start": True})
VARIANTS["qpso_warm"] = ("qpso", {"warm_start": True})
VARIANTS["qpso_warm_b0.5_0.1"] = ("qpso", {"warm_start": True, "beta_start": 0.5, "beta_end": 0.1})
VARIANTS["ga_warm"] = ("ga", {"warm_start": True})


def build_instance(n_customers: int, utilization: float, seed: int):
    graph = generate_synthetic_graph(n_nodes=2 * n_customers, seed=seed)
    rng = random.Random(seed)
    customers = list(range(1, n_customers + 1))
    demands = {c: rng.randint(5, 25) for c in customers}
    n_vehicles = math.ceil(sum(demands.values()) / (utilization * CAPACITY))
    request = RouteRequest(depot=0, stops=customers, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=n_vehicles)
    return graph, request


def run_task(task):
    """One (variant, instance) run. Module-level so worker processes can import it."""
    name, algorithm, kwargs, n_customers, utilization, seed, n_iterations, n_particles, algo_seed, inter_route = task
    graph, request = build_instance(n_customers, utilization, seed)
    problem = RoutingProblem(graph, request)
    t0 = time.perf_counter()
    if algorithm == "nn":
        result = nearest_neighbor(graph, request)
    elif algorithm == "ga":
        result = GeneticAlgorithm(graph, request, population_size=n_particles, n_generations=n_iterations, seed=algo_seed, **kwargs).run()
    elif algorithm == "pso":
        result = ClassicalPSO(graph, request, n_particles=n_particles, n_iterations=n_iterations, seed=algo_seed, **kwargs).run()
    else:
        result = QPSO(graph, request, n_particles=n_particles, n_iterations=n_iterations, seed=algo_seed, **kwargs).run()
    seconds = time.perf_counter() - t0
    two_opt_only = polish_result(problem, result, PENALTY).best_cost
    full = polish_result(problem, result, PENALTY, inter_route=True).best_cost
    feasible = problem.evaluate_routes(split_at_depot(result.best_route, 0)).feasible
    return name, seed, result.best_cost, full if inter_route else two_opt_only, seconds, feasible, two_opt_only, full


def compare(label, ours, reference):
    wins = int((ours < reference - 1e-6).sum())
    losses = int((reference < ours - 1e-6).sum())
    improvement = float((100 * (reference - ours) / reference).mean())
    p = sign_test_p_value(wins, losses)
    return f"{wins:>2}/{len(ours) - wins - losses}/{losses:<2} {improvement:+7.1f}%  p={p:.3f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="show the variant names and exit")
    parser.add_argument("--customers", type=int, default=100)
    parser.add_argument("--instances", type=int, default=10)
    parser.add_argument("--utilization", type=float, default=0.85)
    parser.add_argument("--first-instance-seed", type=int, default=500)
    parser.add_argument("--iterations", type=int, default=800)
    parser.add_argument("--particles", type=int, default=40)
    parser.add_argument("--algo-seed", type=int, default=1)
    parser.add_argument("--variants", nargs="+", default=["pso", "qpso"])
    parser.add_argument("--polish", choices=["two_opt", "full"], default="full",
                        help="two_opt: each route on its own; full: also move/swap stops between vehicles")
    parser.add_argument("--reference", default="pso", help="the variant every other one is compared against")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--csv", type=Path, help="write every run (raw, +2-opt only, +full polish) to this file")
    args = parser.parse_args()

    if args.list:
        for name, (algorithm, kwargs) in VARIANTS.items():
            print(f"{name:<24} {algorithm:<5} {kwargs}")
        return
    REFERENCE = args.reference
    unknown = [v for v in [*args.variants, REFERENCE] if v not in VARIANTS]
    if unknown:
        raise SystemExit(f"unknown variants {unknown}; see --list")
    names = list(dict.fromkeys([REFERENCE, *args.variants]))

    inter_route = args.polish == "full"
    seeds = [args.first_instance_seed + k for k in range(args.instances)]
    tasks = [
        (name, *VARIANTS[name], args.customers, args.utilization, seed, args.iterations, args.particles, args.algo_seed, inter_route)
        for name in names
        for seed in seeds
    ] + [("nn", "nn", {}, args.customers, args.utilization, seed, 0, 0, 0, inter_route) for seed in seeds]

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_task, tasks, chunksize=1))
    elapsed = time.perf_counter() - t0

    by_name: dict[str, dict[int, tuple]] = {}
    for name, seed, raw, polished, seconds, feasible, _two_opt, _full in rows:
        by_name.setdefault(name, {})[seed] = (raw, polished, seconds, feasible)

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["customers", "utilization", "variant", "instance_seed", "raw_cost", "cost_2opt_only", "cost_full_polish", "seconds", "feasible"])
            for name, seed, raw, _polished, seconds, feasible, two_opt_only, full in sorted(rows, key=lambda r: (r[0], r[1])):
                writer.writerow([args.customers, args.utilization, name, seed, f"{raw:.4f}", f"{two_opt_only:.4f}", f"{full:.4f}", f"{seconds:.2f}", int(feasible)])

    def column(name, index):
        return np.array([by_name[name][s][index] for s in seeds], dtype=float)

    print(
        f"\n{args.customers} customers, utilization <= {args.utilization:.0%}, {args.instances} instances "
        f"(seeds {seeds[0]}-{seeds[-1]}), {args.particles} particles x {args.iterations} iterations, algo seed {args.algo_seed}"
        f"  [{elapsed:.0f}s wall]"
    )
    print(f"cells: win/tie/loss against {REFERENCE}, mean improvement (positive = better than {REFERENCE}), sign-test p\n")
    header = f"{'variant':<24}{'mean raw':>10}  {'raw vs ref':<30}{'mean +polish':>13}  {'+polish vs ref':<30}{'s/run':>6}  feas"
    print(header)
    print("-" * len(header))
    ref_raw, ref_pol = column(REFERENCE, 0), column(REFERENCE, 1)
    for name in [*names, "nn"]:
        raw, polished, seconds = column(name, 0), column(name, 1), column(name, 2)
        feasible = np.mean(column(name, 3))
        if name == REFERENCE:
            r_cmp = p_cmp = "(reference)"
        else:
            r_cmp, p_cmp = compare(name, raw, ref_raw), compare(name, polished, ref_pol)
        label = "nearest neighbour" if name == "nn" else name
        print(f"{label:<24}{raw.mean():>10.0f}  {r_cmp:<30}{polished.mean():>13.0f}  {p_cmp:<30}{seconds.mean():>6.1f}  {feasible:.0%}")


if __name__ == "__main__":
    main()
