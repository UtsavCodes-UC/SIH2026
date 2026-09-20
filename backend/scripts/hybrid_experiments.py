"""
Does a QPSO built as "adaptive random-key QPSO + elite archive + 2-opt + diversity restart + hybrid
initialization" beat classical PSO at 100 stops, and does the QPSO update itself matter once every method
gets the same components?  See docs/BENCHMARKS.md, Finding 11.

Variants (`--list`):
    pso, qpso, ga, nn       the bare baselines (qpso uses the size-aware jump of Finding 10)
    h_qpso, h_pso           the full hybrid engine (app/core/hybrid_swarm.py) with each search operator
    a_*                     ablation, add one component to a bare QPSO: init, beta, elite, ls, restart
    d_*                     ablation, drop one component from the full hybrid QPSO

Problems: `--problem tsp` is a single vehicle visiting `--stops` stops; `--problem cvrp` is a fleet with
capacities (as in Finding 10). Every variant gets the same particles x iterations budget. For cvrp,
`--decoder optimal` cuts every visiting order into routes with the optimal Split instead of the greedy rule
(Finding 12); the final polish and the OR-Tools reference are the same either way.

"raw" is what the method itself returned (for the hybrids that includes the 2-opt they run inside their
search); "+polish" is that result after the same final polish for everyone (2-opt, plus moving stops between
vehicles for cvrp). Only "+polish" is like-for-like between a bare method and a hybrid.

Usage (from backend/, venv active):
    python scripts/hybrid_experiments.py --problem tsp --stops 100 --instances 20 --variants pso qpso h_qpso h_pso ga
    python scripts/hybrid_experiments.py --problem tsp --stops 100 --variants h_qpso a_init a_beta a_elite a_ls a_restart d_init d_beta d_elite d_ls d_restart
    python scripts/hybrid_experiments.py --problem tsp --stops 100 --best-known results/hybrid/tsp100_best_known.csv
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
from app.core.hybrid_swarm import HybridSwarm  # noqa: E402
from app.core.local_search import polish_result  # noqa: E402
from app.core.qpso import QPSO  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402

CAPACITY = 100
PENALTY = 1000.0
FIRST_SEED = {"tsp": 300, "cvrp": 500}  # the instance seeds used by Findings 7 and 9-10

ALL_OFF = dict(hybrid_init=False, adaptive_beta=False, elite_archive=False, elite_attractor=False, local_search=False, restart=False)
COMPONENTS = {
    "init": dict(hybrid_init=True),
    "beta": dict(adaptive_beta=True),
    "elite": dict(elite_archive=True, elite_attractor=True),
    "ls": dict(elite_archive=True, local_search=True),  # 2-opt on swarm tours; the archive is only its bookkeeping
    "restart": dict(elite_archive=True, restart=True),
}
DROP = {
    "init": dict(hybrid_init=False),
    "beta": dict(adaptive_beta=False),
    "elite": dict(elite_attractor=False),
    "ls": dict(local_search=False),
    "restart": dict(restart=False),
}

VARIANTS: dict[str, tuple[str, dict]] = {
    "pso": ("pso", {}),
    "qpso": ("qpso", {}),
    "ga": ("ga", {}),
    "pso_warm": ("pso", {"warm_start": True}),
    "qpso_warm": ("qpso", {"warm_start": True}),
    "ga_warm": ("ga", {"warm_start": True}),
    "h_qpso": ("hybrid", {"operator": "qpso"}),
    "h_pso": ("hybrid", {"operator": "pso"}),
}
for _name, _flags in COMPONENTS.items():
    VARIANTS[f"a_{_name}"] = ("hybrid", {"operator": "qpso", **ALL_OFF, **_flags})
for _name, _flags in DROP.items():
    VARIANTS[f"d_{_name}"] = ("hybrid", {"operator": "qpso", **_flags})


def build_instance(problem: str, n_stops: int, seed: int, utilization: float, decoder: str = "greedy"):
    graph = generate_synthetic_graph(n_nodes=2 * n_stops, seed=seed)
    stops = list(range(1, n_stops + 1))
    if problem == "tsp":
        return graph, RouteRequest(depot=0, stops=stops)
    rng = random.Random(seed)
    demands = {c: rng.randint(5, 25) for c in stops}
    n_vehicles = math.ceil(sum(demands.values()) / (utilization * CAPACITY))
    return graph, RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=n_vehicles, decoder=decoder)


def run_task(task):
    """One (variant, instance) run. Module-level so worker processes can import it."""
    name, algorithm, kwargs, problem_kind, n_stops, utilization, seed, n_iterations, n_particles, algo_seed, decoder = task
    graph, request = build_instance(problem_kind, n_stops, seed, utilization, decoder)
    problem = RoutingProblem(graph, request)
    t0 = time.perf_counter()
    if algorithm == "nn":
        result = nearest_neighbor(graph, request)
    elif algorithm == "ga":
        result = GeneticAlgorithm(graph, request, population_size=n_particles, n_generations=n_iterations, seed=algo_seed, **kwargs).run()
    elif algorithm == "pso":
        result = ClassicalPSO(graph, request, n_particles=n_particles, n_iterations=n_iterations, seed=algo_seed, **kwargs).run()
    elif algorithm == "qpso":
        result = QPSO(graph, request, n_particles=n_particles, n_iterations=n_iterations, seed=algo_seed, **kwargs).run()
    else:
        result = HybridSwarm(graph, request, n_particles=n_particles, n_iterations=n_iterations, seed=algo_seed, **kwargs).run()
    seconds = time.perf_counter() - t0
    polished = polish_result(problem, result, PENALTY, inter_route=True).best_cost
    feasible = problem.evaluate_routes(split_at_depot(result.best_route, 0)).feasible
    return name, seed, result.best_cost, polished, seconds, feasible


def compare(ours, reference):
    wins, losses = int((ours < reference - 1e-6).sum()), int((reference < ours - 1e-6).sum())
    improvement = float((100 * (reference - ours) / reference).mean())
    return f"{wins:>2}/{len(ours) - wins - losses}/{losses:<2} {improvement:+6.1f}%  p={sign_test_p_value(wins, losses):.3f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="show the variant names and exit")
    parser.add_argument("--problem", choices=["tsp", "cvrp"], default="tsp")
    parser.add_argument("--stops", type=int, default=100)
    parser.add_argument("--instances", type=int, default=20)
    parser.add_argument("--utilization", type=float, default=0.85, help="cvrp only")
    parser.add_argument("--decoder", choices=["greedy", "optimal"], default="greedy", help="cvrp only: how an order is cut into routes")
    parser.add_argument("--first-instance-seed", type=int, default=None)
    parser.add_argument("--iterations", type=int, default=800)
    parser.add_argument("--particles", type=int, default=40)
    parser.add_argument("--algo-seed", type=int, default=1)
    parser.add_argument("--variants", nargs="+", default=["pso", "qpso", "h_qpso", "h_pso"])
    parser.add_argument("--reference", default="pso", help="the variant every other one is compared against")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--csv", type=Path, help="write every run to this file")
    parser.add_argument("--best-known", type=Path, help="CSV with instance_seed,cost: adds a '% above best known' column")
    args = parser.parse_args()

    if args.list:
        for name, (algorithm, kwargs) in VARIANTS.items():
            print(f"{name:<12} {algorithm:<7} {kwargs}")
        return
    reference = args.reference
    unknown = [v for v in [*args.variants, reference] if v not in VARIANTS]
    if unknown:
        raise SystemExit(f"unknown variants {unknown}; see --list")
    names = list(dict.fromkeys([reference, *args.variants]))

    first = args.first_instance_seed if args.first_instance_seed is not None else FIRST_SEED[args.problem]
    seeds = [first + k for k in range(args.instances)]
    tasks = [
        (name, *VARIANTS[name], args.problem, args.stops, args.utilization, seed, args.iterations, args.particles, args.algo_seed, args.decoder)
        for name in names
        for seed in seeds
    ] + [("nn", "nn", {}, args.problem, args.stops, args.utilization, seed, 0, 0, 0, args.decoder) for seed in seeds]

    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run_task, tasks, chunksize=1))
    elapsed = time.perf_counter() - t0

    by_name: dict[str, dict[int, tuple]] = {}
    for name, seed, raw, polished, seconds, feasible in rows:
        by_name.setdefault(name, {})[seed] = (raw, polished, seconds, feasible)

    def column(name, index):
        return np.array([by_name[name][s][index] for s in seeds], dtype=float)

    best_known = None
    if args.best_known:
        known = {int(r["instance_seed"]): float(r["cost"]) for r in csv.DictReader(args.best_known.open(encoding="utf-8"))}
        best_known = np.array([known[s] for s in seeds])

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["problem", "stops", "variant", "instance_seed", "raw_cost", "polished_cost", "seconds", "feasible"])
            for name, seed, raw, polished, seconds, feasible in sorted(rows, key=lambda r: (r[0], r[1])):
                writer.writerow([args.problem, args.stops, name, seed, f"{raw:.4f}", f"{polished:.4f}", f"{seconds:.2f}", int(feasible)])

    print(
        f"\n{args.problem.upper()} ({args.decoder} decoder) with {args.stops} stops, {args.instances} instances (seeds {seeds[0]}-{seeds[-1]}), "
        f"{args.particles} particles x {args.iterations} iterations, algo seed {args.algo_seed}  [{elapsed:.0f}s wall]"
    )
    print(f"cells: win/tie/loss against {reference}, mean improvement (positive = better than {reference}), sign-test p\n")
    gap_header = f"{'above best':>11}" if best_known is not None else ""
    header = f"{'variant':<12}{'raw':>9}  {'raw vs ref':<26}{'+polish':>9}  {'+polish vs ref':<26}{gap_header}{'s/run':>7}"
    print(header)
    print("-" * len(header))
    ref_raw, ref_pol = column(reference, 0), column(reference, 1)
    for name in [*names, "nn"]:
        raw, polished, seconds = column(name, 0), column(name, 1), column(name, 2)
        if name == reference:
            r_cmp = p_cmp = "(reference)"
        else:
            r_cmp, p_cmp = compare(raw, ref_raw), compare(polished, ref_pol)
        gap = f"{100 * np.mean((polished - best_known) / best_known):>10.1f}%" if best_known is not None else ""
        label = "nn (+polish)" if name == "nn" else name
        print(f"{label:<12}{raw.mean():>9.0f}  {r_cmp:<26}{polished.mean():>9.0f}  {p_cmp:<26}{gap}{seconds.mean():>7.1f}")


if __name__ == "__main__":
    main()
