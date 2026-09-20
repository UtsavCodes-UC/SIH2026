"""
How close do the searches get to the exact shortest path, and what do they cost? See docs/BENCHMARKS.md, Finding 18.

For maps of several sizes (the app's synthetic road network with random congestion), random pairs of intersections at least four
road segments apart (fewest segments) are solved by Dijkstra (exact) and by the priority-encoded searches of core/shortest_path.py:

    QPSO            30 particles x 200 iterations, with the walk-towards-the-target starting particle (the app default)
    QPSO, cold      the same without that starting particle
    QPSO, big       60 particles x 500 iterations
    PSO, GA         30 x 200 like QPSO, the same encoding, decoder and starting particle

Each search sees the same pairs and the same seed. Dijkstra is exact, so a search's gap is how far above the optimum its
path is. Also run once with blended cost weights (time 0.4, distance 0.3, congestion 0.3).

Usage (from backend/, venv active):
    python scripts/shortest_path_experiment.py --csv results/shortest_path/paths.csv
    python scripts/shortest_path_experiment.py --from-csv results/shortest_path/paths.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.cost_model import CostWeights  # noqa: E402
from app.core.shortest_path import PathProblem, dijkstra_path, search_path  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402

SEARCHES = {
    "qpso": ("qpso", 30, 200, True),
    "qpso cold": ("qpso", 30, 200, False),
    "qpso big": ("qpso", 60, 500, True),
    "pso": ("pso", 30, 200, True),
    "ga": ("ga", 30, 200, True),
}
SIZES = (40, 80, 160, 300)
CONDITIONS = {"time": CostWeights(1, 0, 0), "blend": CostWeights(0.4, 0.3, 0.3)}
GRAPH_SEED = 5
FIELDS = ["nodes", "weights", "pair", "hops", "algorithm", "cost", "exact_cost", "gap_pct", "seconds", "dimension"]


def pairs_for(graph, count, seed, min_hops=5):
    rng = random.Random(seed)
    nodes, pairs = list(graph.graph.nodes), []
    while len(pairs) < count:
        s, t = rng.sample(nodes, 2)
        if nx.has_path(graph.graph, s, t) and len(nx.shortest_path(graph.graph, s, t)) >= min_hops:
            pairs.append((s, t))
    return pairs


def run(job):
    n_nodes, weights_name, pair_index, source, target = job
    weights = CONDITIONS[weights_name]
    graph = generate_synthetic_graph(n_nodes=n_nodes, area_size_km=8.0, seed=GRAPH_SEED)
    exact = dijkstra_path(graph, source, target, weights)
    rows = [{"nodes": n_nodes, "weights": weights_name, "pair": pair_index, "hops": len(exact.nodes) - 1, "algorithm": "dijkstra",
             "cost": exact.cost, "exact_cost": exact.cost, "gap_pct": 0.0, "seconds": exact.runtime_sec, "dimension": 0}]
    problem = PathProblem(graph, source, target, weights)
    for label, (algorithm, particles, iterations, warm) in SEARCHES.items():
        found = search_path(problem, algorithm, particles, iterations, seed=pair_index, warm_start=warm)
        assert found.cost >= exact.cost - 1e-9, "a search beat the exact solver"
        rows.append({"nodes": n_nodes, "weights": weights_name, "pair": pair_index, "hops": len(exact.nodes) - 1, "algorithm": label,
                     "cost": found.cost, "exact_cost": exact.cost, "gap_pct": 100.0 * (found.cost - exact.cost) / exact.cost,
                     "seconds": found.runtime_sec, "dimension": problem.dimension})
    return rows


def report(rows) -> None:
    for weights_name in ("time", "blend"):
        for n in sorted({r["nodes"] for r in rows if r["weights"] == weights_name}):
            sub = [r for r in rows if r["nodes"] == n and r["weights"] == weights_name]
            pairs = sorted({r["pair"] for r in sub})
            hops = statistics.fmean(r["hops"] for r in sub if r["algorithm"] == "dijkstra")
            dim = statistics.fmean(r["dimension"] for r in sub if r["algorithm"] == "qpso")
            print(f"\n{n} nodes, {len(pairs)} pairs, cost = {weights_name} (mean {hops:.1f} road segments, corridor of {dim:.0f} nodes)")
            print(f"{'':<12}{'optimal on':>12}{'mean gap':>10}{'median':>8}{'worst':>8}{'median time':>13}")
            for algorithm in ["dijkstra", *SEARCHES]:
                a = [r for r in sub if r["algorithm"] == algorithm]
                gaps = [r["gap_pct"] for r in a]
                optimal = sum(g <= 1e-9 for g in gaps)
                print(f"{algorithm:<12}{f'{optimal}/{len(a)}':>12}{statistics.fmean(gaps):>9.2f}%{statistics.median(gaps):>7.2f}%{max(gaps):>7.1f}%{1000 * statistics.median(r['seconds'] for r in a):>10.1f} ms")
            cost = {(r["algorithm"], r["pair"]): r["cost"] for r in sub}
            for other in ("pso", "ga", "qpso cold"):
                wins = sum(cost[("qpso", p)] < cost[(other, p)] - 1e-9 for p in pairs)
                losses = sum(cost[("qpso", p)] > cost[(other, p)] + 1e-9 for p in pairs)
                print(f"  QPSO against {other:<10} {wins}/{len(pairs) - wins - losses}/{losses} wins/ties/losses, p = {sign_test_p_value(wins, losses):.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pairs", type=int, default=50)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--from-csv", type=Path)
    args = parser.parse_args()

    if args.from_csv:
        rows = [{**r, "nodes": int(r["nodes"]), "pair": int(r["pair"]), "hops": int(r["hops"]), "dimension": int(r["dimension"]),
                 **{k: float(r[k]) for k in ("cost", "exact_cost", "gap_pct", "seconds")}} for r in csv.DictReader(args.from_csv.open(encoding="utf-8"))]
        report(rows)
        return
    jobs = []
    for weights_name, sizes in (("time", SIZES), ("blend", (80,))):
        for n in sizes:
            graph = generate_synthetic_graph(n_nodes=n, area_size_km=8.0, seed=GRAPH_SEED)
            jobs += [(n, weights_name, i, s, t) for i, (s, t) in enumerate(pairs_for(graph, args.pairs, seed=n))]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = [row for chunk in pool.map(run, jobs, chunksize=1) for row in chunk]
    print(f"[{time.perf_counter() - started:.0f} s wall, {args.workers} processes]")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    report(rows)


if __name__ == "__main__":
    main()
