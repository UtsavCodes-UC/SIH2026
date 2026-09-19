"""
QPSO vs classical PSO on the multi-vehicle capacitated problem, raw cost (no local
search), using the decoder in app/core/vrp_formulation.py: the visiting order is cut
into per-vehicle routes by capacity, with leg costs from shortest paths over the
directed congested graph. See docs/BENCHMARKS.md, Finding 9.

Random instances: `customers` stops with demands 5-25, vehicle capacity 100, and a
fleet just large enough that total demand is at most `max_fleet_utilization` of total
capacity. The reported feasibility says how often each algorithm's best solution
respects every vehicle's capacity.

Usage (from backend/, with the venv active):
    python scripts/compare_multi_vehicle.py                                   # the Finding 9 table
    python scripts/compare_multi_vehicle.py --configs 100:0.85 --instances 10 --iterations 2400
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.baselines.classical_pso import ClassicalPSO  # noqa: E402
from app.core.benchmark import sign_test_p_value  # noqa: E402
from app.core.qpso import QPSO  # noqa: E402
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot  # noqa: E402
from app.data.synthetic_graph_generator import generate_synthetic_graph  # noqa: E402

CAPACITY = 100
PSO_PRESETS = {
    "ours": {},
    "teammate": dict(w_start=0.7, w_end=0.7, c1=1.5, c2=1.5, v_max=0.2),
}


def run_config(n_customers, utilization, n_instances, n_iterations, first_seed):
    t0 = time.perf_counter()
    q_cost, q_feasible, fleet_util = [], [], []
    p_cost = {name: [] for name in PSO_PRESETS}
    p_feasible = {name: [] for name in PSO_PRESETS}

    for k in range(n_instances):
        seed = first_seed + k
        graph = generate_synthetic_graph(n_nodes=2 * n_customers, seed=seed)
        rng = random.Random(seed)
        customers = list(range(1, n_customers + 1))
        demands = {c: rng.randint(5, 25) for c in customers}
        total = sum(demands.values())
        n_vehicles = math.ceil(total / (utilization * CAPACITY))
        fleet_util.append(total / (n_vehicles * CAPACITY))
        request = RouteRequest(
            depot=0, stops=customers, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=n_vehicles
        )
        problem = RoutingProblem(graph, request)

        def feasible(result):
            return problem.evaluate_routes(split_at_depot(result.best_route, 0)).feasible

        result = QPSO(graph, request, n_iterations=n_iterations, seed=1).run()
        q_cost.append(result.best_cost)
        q_feasible.append(feasible(result))

        for name, kwargs in PSO_PRESETS.items():
            result = ClassicalPSO(graph, request, n_iterations=n_iterations, seed=1, **kwargs).run()
            p_cost[name].append(result.best_cost)
            p_feasible[name].append(feasible(result))

    print(
        f"\n=== {n_customers} customers, fleet sized for <= {utilization:.0%} utilization "
        f"(actual mean {np.mean(fleet_util):.0%}), {n_instances} instances, {n_iterations} iterations "
        f"({time.perf_counter() - t0:.0f}s) ==="
    )
    q = np.array(q_cost)
    for name in PSO_PRESETS:
        p = np.array(p_cost[name])
        wins, losses = int((q < p - 1e-6).sum()), int((p < q - 1e-6).sum())
        improvement = (100 * (p - q) / p).mean()
        print(
            f"vs PSO {name:<8}: win {wins:>2}/tie {n_instances - wins - losses:>2}/loss {losses:>2}  "
            f"mean improvement {improvement:+7.2f}%  sign-test p={sign_test_p_value(wins, losses):.4f}  "
            f"| feasible: QPSO {np.mean(q_feasible):.0%} PSO {np.mean(p_feasible[name]):.0%}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--configs", nargs="+", default=["20:0.85", "50:0.85", "100:0.85", "50:0.93"],
        help="customers:max_fleet_utilization pairs",
    )
    parser.add_argument("--instances", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=800)
    parser.add_argument("--first-instance-seed", type=int, default=500)
    args = parser.parse_args()

    for config in args.configs:
        n_customers, utilization = config.split(":")
        run_config(int(n_customers), float(utilization), args.instances, args.iterations, args.first_instance_seed)


if __name__ == "__main__":
    main()
