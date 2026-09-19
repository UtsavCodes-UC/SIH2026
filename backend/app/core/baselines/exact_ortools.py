"""
Near-exact ground-truth baseline for larger instances via Google OR-Tools'
routing solver, for when exact_held_karp's exponential DP is no longer
practical (n > MAX_STOPS_FOR_EXACT). OR-Tools uses its own metaheuristic
search internally (guided local search) with a time limit, so it is
"near-exact" rather than provably optimal at scale -- good enough as an
upper bound to compare QPSO against on Day 3 scalability runs.

`ortools` is a heavy optional dependency (not installed by default in this
sprint's venv); the import is guarded so the rest of the app works without it.
Install with: pip install ortools
"""

from __future__ import annotations

import time

from app.core.graph_model import TrafficGraph
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    ORTOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when ortools isn't installed
    ORTOOLS_AVAILABLE = False


def ortools_solve(
    graph: TrafficGraph,
    request: RouteRequest,
    time_limit_sec: int = 10,
) -> OptimizationResult:
    if not ORTOOLS_AVAILABLE:
        raise ImportError("ortools is not installed. Run: pip install ortools")
    if request.n_vehicles > 1:
        raise NotImplementedError("the OR-Tools wrapper models one vehicle; add a capacity dimension for a fleet")

    start = time.perf_counter()
    problem = RoutingProblem(graph, request)
    stops = list(dict.fromkeys(request.stops))
    nodes = [request.depot, *stops]  # index 0 = depot

    manager = pywrapcp.RoutingIndexManager(len(nodes), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def cost_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        # OR-Tools requires integer costs; travel times are minutes, scale for precision.
        return int(round(problem.leg_time(nodes[from_node], nodes[to_node]) * 100))

    transit_callback_index = routing.RegisterTransitCallback(cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_params.time_limit.FromSeconds(time_limit_sec)

    solution = routing.SolveWithParameters(search_params)
    if solution is None:
        raise RuntimeError("OR-Tools failed to find a solution within the time limit")

    order_indices = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if node != 0:  # skip depot
            order_indices.append(node)
        index = solution.Value(routing.NextVar(index))

    stop_order = [nodes[i] for i in order_indices]
    evaluation = problem.evaluate(stop_order)
    cost = evaluation.total_time_min + 1000.0 * evaluation.capacity_violation
    runtime_sec = time.perf_counter() - start

    return OptimizationResult(
        best_route=evaluation.route,
        best_cost=cost,
        convergence_history=[cost],
        runtime_sec=runtime_sec,
        iterations=1,
        n_particles=1,
    )
