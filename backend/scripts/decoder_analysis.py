"""
Is the greedy split decoder what holds the multi-vehicle search back?  See docs/BENCHMARKS.md, Finding 12.

Three analyses on the 20 multi-vehicle instances of Findings 10-11 (100 customers, capacity 100, fleet for at most
85% utilization, seeds 500-519):

  1. the same methods with the greedy and the optimal decoder, paired by instance (reads the CSVs that
     `hybrid_experiments.py --decoder greedy|optimal` wrote), and their gap to the OR-Tools reference;
  2. re-cutting FINISHED routes optimally: does the decoder's gain come from the final routes?
  3. the local search's sensitivity to its starting routes: nearest neighbour with each cut, and the best of 10
     randomized starts, to see whether "a different decoder" is more than "a different start".

    python scripts/decoder_analysis.py            # all three (analysis 2 and 3 take about 20 seconds)
    python scripts/decoder_analysis.py --only 1
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.baselines.classical_pso import ClassicalPSO  # noqa: E402
from app.core.baselines.dijkstra_baseline import nearest_neighbor, nearest_neighbor_order  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.local_search import improve_routes, polish_result  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402

RESULTS = Path(__file__).resolve().parent.parent / "results"
SEEDS = list(range(500, 520))


def load(path: Path, column: str = "polished_cost") -> dict[str, dict[int, float]]:
    rows: dict[str, dict[int, float]] = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        rows.setdefault(r["variant"], {})[int(r["instance_seed"])] = float(r[column])
    return rows


def paired_decoders() -> None:
    greedy = load(RESULTS / "hybrid" / "cvrp100.csv")
    optimal = load(RESULTS / "hybrid" / "cvrp100_optimal.csv")
    greedy["ga_warm"] = load(RESULTS / "scaling" / "scaling_100customers.csv", "cost_full_polish")["ga_warm"]  # same instances and polish
    reference = {int(r["instance_seed"]): float(r["cost"]) for r in csv.DictReader((RESULTS / "hybrid" / "cvrp100_best_known.csv").open(encoding="utf-8"))}
    ref = np.array([reference[s] for s in SEEDS])

    print("1. Same method, greedy vs optimal decoder, cost after the final polish (20 instances)")
    print(f"{'method':<10}{'greedy':>8}{'optimal':>9}{'change':>8}   opt wins/ties/losses  p(opt better)  above OR-Tools: optimal / greedy")
    for name in ("nn", "pso_warm", "qpso_warm", "ga_warm", "h_qpso", "h_pso"):
        g = np.array([greedy[name][s] for s in SEEDS])
        o = np.array([optimal[name][s] for s in SEEDS])
        wins, losses = int((o < g - 1e-6).sum()), int((g < o - 1e-6).sum())
        print(
            f"{name:<10}{g.mean():>8.0f}{o.mean():>9.0f}{100 * (g.mean() - o.mean()) / g.mean():>+7.1f}%   "
            f"{wins:>7}/{20 - wins - losses}/{losses:<8}   {sign_test_p_value(wins, losses):>8.3f}        "
            f"{100 * np.mean((o - ref) / ref):>+8.1f}% / {100 * np.mean((g - ref) / ref):+.1f}%"
        )
    print(f"OR-Tools reference (guided local search, 60 s): mean {ref.mean():.1f}\n")


def instance(seed: int, n: int = 100):
    graph = generate_synthetic_graph(n_nodes=2 * n, seed=seed)
    rng = random.Random(seed)
    stops = list(range(1, n + 1))
    demands = {c: rng.randint(5, 25) for c in stops}
    common = dict(depot=0, stops=stops, demands=demands, vehicle_capacity=100, n_vehicles=math.ceil(sum(demands.values()) / 85))
    return graph, RoutingProblem(graph, RouteRequest(**common, decoder="greedy")), RoutingProblem(graph, RouteRequest(**common, decoder="optimal"))


def cost(problem: RoutingProblem, routes) -> float:
    e = problem.evaluate_routes(routes)
    return e.total_time_min + 1000.0 * e.capacity_violation


def recut_task(seed: int) -> dict:
    graph, greedy, optimal = instance(seed)
    request = greedy.request
    out = {}
    for name, result in (("nn", nearest_neighbor(graph, request)), ("pso_warm", ClassicalPSO(graph, request, warm_start=True, seed=1).run())):
        polished = polish_result(greedy, result, 1000.0, inter_route=True)
        routes = split_at_depot(polished.best_route, 0)
        recut = optimal.split([s for r in routes for s in r[1:-1]])  # concatenate the finished routes, cut them optimally
        out[name] = (polished.best_cost, cost(greedy, recut))
    return out


def recut() -> None:
    with ProcessPoolExecutor(max_workers=10) as pool:
        rows = list(pool.map(recut_task, SEEDS))
    print("2. Re-cutting the FINISHED routes optimally (greedy decoder used in the search)")
    for name in ("nn", "pso_warm"):
        before = np.mean([r[name][0] for r in rows])
        after = np.mean([r[name][1] for r in rows])
        print(f"   {name:<9} polished {before:7.1f} -> after an optimal re-cut {after:7.1f}  ({100 * (before - after) / before:.2f}% lower)")
    print()


def start_task(seed: int) -> dict:
    graph, greedy, optimal = instance(seed)
    nn = nearest_neighbor_order(greedy)
    out = {
        "A nearest neighbour, greedy cut": cost(greedy, improve_routes(greedy, greedy.split(nn))),
        "B nearest neighbour, optimal cut": cost(greedy, improve_routes(greedy, optimal.split(nn))),
    }
    from_greedy, from_optimal = [], []
    for k in range(10):
        order = nearest_neighbor_order(greedy, np.random.default_rng(k), 4)
        from_greedy.append(cost(greedy, improve_routes(greedy, greedy.split(order))))
        from_optimal.append(cost(greedy, improve_routes(greedy, optimal.split(order))))
    out["C mean of 10 randomized starts, greedy cut"] = float(np.mean(from_greedy))
    out["C' best of 10 randomized starts, greedy cut"] = float(np.min(from_greedy))
    out["D mean of 10 randomized starts, optimal cut"] = float(np.mean(from_optimal))
    out["D' best of 10 randomized starts, optimal cut"] = float(np.min(from_optimal))
    return out


def start_effect() -> None:
    with ProcessPoolExecutor(max_workers=10) as pool:
        rows = list(pool.map(start_task, SEEDS))
    print("3. What the inter-route local search reaches from different starting routes (mean cost, 20 instances)")
    base = np.mean([r["A nearest neighbour, greedy cut"] for r in rows])
    for key in rows[0]:
        mean = np.mean([r[key] for r in rows])
        print(f"   {key:<46} {mean:7.1f}  {100 * (base - mean) / base:+5.2f}% vs A")
    wins = sum(r["B nearest neighbour, optimal cut"] < r["A nearest neighbour, greedy cut"] - 1e-6 for r in rows)
    print(f"   B is better than A on {wins} of 20 instances")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", type=int, choices=[1, 2, 3])
    args = parser.parse_args()
    for number, step in ((1, paired_decoders), (2, recut), (3, start_effect)):
        if args.only in (None, number):
            step()


if __name__ == "__main__":
    main()
