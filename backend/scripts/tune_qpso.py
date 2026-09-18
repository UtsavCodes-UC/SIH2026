"""
Hyperparameter sweep for QPSO's beta annealing schedule / swarm size, scored
against classical PSO on the same instances (both polished with 2-opt, since
that's how they'll actually run via benchmark.py).

Held-Karp exact is required as ground truth, so every tuning instance is kept
small (<= 12 stops). Sweep and validation use disjoint seeds so a combo that
wins isn't just overfit to the instances it was picked on.

Usage (from backend/, with the venv active):
    python scripts/tune_qpso.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.baselines.classical_pso import ClassicalPSO  # noqa: E402
from app.core.baselines.exact_held_karp import held_karp  # noqa: E402
from app.core.local_search import polish_result  # noqa: E402
from app.core.qpso import QPSO  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402


@dataclass
class Instance:
    graph: object
    request: RouteRequest
    exact_cost: float


def build_instances(n_stops_options: list[int], seeds: list[int]) -> list[Instance]:
    instances = []
    for n_stops in n_stops_options:
        for seed in seeds:
            graph = generate_synthetic_graph(n_nodes=n_stops * 3, seed=seed)
            stops = list(range(1, n_stops + 1))
            request = RouteRequest(depot=0, stops=stops)
            exact_cost = held_karp(graph, request).best_cost
            instances.append(Instance(graph=graph, request=request, exact_cost=exact_cost))
    return instances


def avg_gap_qpso(instances: list[Instance], beta_start, beta_end, n_particles, n_iterations, seed=1) -> float:
    gaps = []
    for inst in instances:
        problem = RoutingProblem(inst.graph, inst.request)
        result = QPSO(
            inst.graph, inst.request,
            n_particles=n_particles, n_iterations=n_iterations,
            beta_start=beta_start, beta_end=beta_end, seed=seed,
        ).run()
        polished = polish_result(problem, result)
        gaps.append(100.0 * (polished.best_cost - inst.exact_cost) / inst.exact_cost)
    return sum(gaps) / len(gaps)


def avg_gap_classical_pso(instances: list[Instance], n_particles, n_iterations, seed=1) -> float:
    gaps = []
    for inst in instances:
        problem = RoutingProblem(inst.graph, inst.request)
        result = ClassicalPSO(
            inst.graph, inst.request,
            n_particles=n_particles, n_iterations=n_iterations, seed=seed,
        ).run()
        polished = polish_result(problem, result)
        gaps.append(100.0 * (polished.best_cost - inst.exact_cost) / inst.exact_cost)
    return sum(gaps) / len(gaps)


def main() -> None:
    tuning_instances = build_instances(n_stops_options=[8, 10, 12], seeds=[1, 2, 3, 4, 5])
    validation_instances = build_instances(n_stops_options=[8, 10, 12], seeds=[101, 102, 103, 104, 105])

    print(f"tuning on {len(tuning_instances)} instances, validating on {len(validation_instances)}\n")

    grid = [
        (beta_start, beta_end, n_particles, n_iterations)
        for beta_start in (0.8, 1.0, 1.3)
        for beta_end in (0.2, 0.35)
        for n_particles in (20, 40)
        for n_iterations in (100, 200)
    ]

    results = []
    for beta_start, beta_end, n_particles, n_iterations in grid:
        gap = avg_gap_qpso(tuning_instances, beta_start, beta_end, n_particles, n_iterations)
        results.append((gap, beta_start, beta_end, n_particles, n_iterations))
        print(f"beta=({beta_start},{beta_end}) particles={n_particles} iters={n_iterations} -> avg gap {gap:.2f}%")

    results.sort(key=lambda r: r[0])
    best_gap, beta_start, beta_end, n_particles, n_iterations = results[0]

    print(f"\nbest on tuning set: beta=({beta_start},{beta_end}) particles={n_particles} "
          f"iters={n_iterations} -> avg gap {best_gap:.2f}%")

    pso_reference_gap = avg_gap_classical_pso(tuning_instances, n_particles=40, n_iterations=200)
    print(f"classical PSO reference (40 particles, 200 iters) on tuning set: avg gap {pso_reference_gap:.2f}%")

    val_qpso_gap = avg_gap_qpso(validation_instances, beta_start, beta_end, n_particles, n_iterations)
    val_pso_gap = avg_gap_classical_pso(validation_instances, n_particles=40, n_iterations=200)

    print(f"\n--- validation set (unseen seeds) ---")
    print(f"QPSO   (tuned): avg gap {val_qpso_gap:.2f}%")
    print(f"PSO (reference): avg gap {val_pso_gap:.2f}%")
    print(f"QPSO wins: {val_qpso_gap < val_pso_gap}")


if __name__ == "__main__":
    main()
