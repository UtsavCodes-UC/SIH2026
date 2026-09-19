"""POST /benchmark: run every algorithm on one problem and compare them (raw and 2-opt-polished)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.graph import lookup
from app.core.benchmark import BenchmarkConfig, run_benchmark
from app.core.vrp_formulation import RoutingProblem, split_at_depot
from app.schemas.solve import BenchmarkAlgorithmOut, BenchmarkRequest, BenchmarkResponse
from app.services.graph_store import GraphStore, get_store
from app.services.problem_builder import resolve_problem
from app.services.views import problem_warnings, resolved_problem

router = APIRouter(tags=["benchmark"])


@router.post("/benchmark", response_model=BenchmarkResponse)
def benchmark(req: BenchmarkRequest, store: GraphStore = Depends(get_store)) -> BenchmarkResponse:
    stored = lookup(store, req.graph_id)
    with stored.lock:
        request = resolve_problem(stored, req)
        routing_problem = RoutingProblem(stored.graph, request)  # validates reachability first
        config = BenchmarkConfig(
            n_particles=req.n_particles,
            n_iterations=req.n_iterations,
            ga_population_size=req.n_particles,
            ga_generations=req.n_iterations,
            seed=req.seed,
            polish_with_two_opt=req.polish,
            inter_route_polish=True,
            warm_start=req.warm_start,
        )
        report = run_benchmark(stored.graph, request, config)

        algorithms = []
        for algo in report.algorithms:
            # split the penalized cost into travel time and overload, so a constant penalty can't hide the comparison
            raw = routing_problem.evaluate_routes(split_at_depot(algo.raw_result.best_route, request.depot))
            algorithms.append(
                BenchmarkAlgorithmOut(
                    name=algo.name,
                    raw_cost=algo.raw_cost,
                    time_min=raw.total_time_min,
                    capacity_violation=raw.capacity_violation,
                    polished_cost=algo.result.best_cost if algo.polished else None,
                    raw_gap_pct=algo.raw_gap_pct,
                    polished_gap_pct=algo.polished_gap_pct,
                    runtime_sec=algo.raw_result.runtime_sec,
                    iterations=algo.raw_result.iterations,
                    convergence=algo.raw_result.convergence_history,
                )
            )

        return BenchmarkResponse(
            graph_id=stored.graph_id,
            problem=resolved_problem(routing_problem),
            n_nodes=report.n_nodes,
            n_stops=report.n_stops,
            exact_cost=report.exact_cost,
            algorithms=algorithms,
            warm_start=req.warm_start,
            warnings=problem_warnings(routing_problem),
            traffic=stored.traffic,
        )
