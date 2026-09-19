"""POST /optimize: solve one routing problem with the chosen algorithm."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.graph import lookup
from app.core.vrp_formulation import split_at_depot
from app.schemas.solve import OptimizeRequest, OptimizeResponse
from app.services.graph_store import GraphStore, get_store
from app.services.problem_builder import resolve_problem
from app.services.solver import solve
from app.services.views import problem_warnings, resolved_problem, route_outputs

router = APIRouter(tags=["optimize"])


@router.post("/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest, store: GraphStore = Depends(get_store)) -> OptimizeResponse:
    stored = lookup(store, req.graph_id)
    with stored.lock:  # edge weights must not change mid-solve
        request = resolve_problem(stored, req)
        solution = solve(
            stored.graph, request, req.algorithm, req.n_particles, req.n_iterations, req.seed, req.polish,
            warm_start=req.warm_start,
        )
        routes = split_at_depot(solution.final.best_route, request.depot)
        evaluation = solution.problem.evaluate_routes(routes)
        outputs = route_outputs(stored, solution.problem, routes)
        problem = resolved_problem(solution.problem)
        warnings = problem_warnings(solution.problem)
        traffic = stored.traffic

    return OptimizeResponse(
        graph_id=stored.graph_id,
        algorithm=req.algorithm,
        problem=problem,
        routes=outputs,
        total_time_min=evaluation.total_time_min,
        total_distance_km=sum(r.distance_km for r in outputs),
        capacity_violation=evaluation.capacity_violation,
        feasible=evaluation.feasible,
        raw_cost=solution.raw.best_cost,
        cost=solution.final.best_cost,
        polished=solution.polished,
        warm_start=req.warm_start and req.algorithm != "nearest_neighbor",
        convergence=solution.raw.convergence_history,
        runtime_sec=solution.final.runtime_sec,
        iterations=solution.raw.iterations,
        warnings=warnings,
        traffic=traffic,
    )
