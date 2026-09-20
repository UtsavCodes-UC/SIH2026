"""POST /shortest-path: the cheapest way between two points, exact and searched."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.graph import lookup
from app.core.cost_model import CostWeights, path_metrics
from app.core.shortest_path import NoPathError, PathProblem, dijkstra_path, search_path
from app.schemas.path import PathOut, ShortestPathRequest, ShortestPathResponse
from app.services.graph_store import GraphStore, get_store
from app.services.problem_builder import InvalidProblemError
from app.services.views import path_points

router = APIRouter(tags=["shortest-path"])


@router.post("/shortest-path", response_model=ShortestPathResponse)
def shortest_path(req: ShortestPathRequest, store: GraphStore = Depends(get_store)) -> ShortestPathResponse:
    stored = lookup(store, req.graph_id)
    weights = CostWeights(req.cost_weights.time, req.cost_weights.distance, req.cost_weights.congestion)
    with stored.lock:  # edge weights must not change mid-solve
        graph = stored.graph
        for name, node in (("source", req.source), ("target", req.target)):
            if node not in graph.graph:
                raise InvalidProblemError(f"{name} {node} is not a node of this graph")
        if req.source == req.target:
            raise InvalidProblemError("choose two different points")
        try:
            exact = dijkstra_path(graph, req.source, req.target, weights)
            results = []
            for algorithm in req.algorithms:
                if algorithm == "dijkstra":
                    found = exact
                else:
                    problem = PathProblem(graph, req.source, req.target, weights)
                    found = search_path(problem, algorithm, req.n_particles, req.n_iterations, req.seed, req.warm_start)
                metrics = path_metrics(graph, found.nodes)
                results.append(
                    PathOut(
                        algorithm=algorithm,
                        nodes=list(found.nodes),
                        path=path_points(graph, found.nodes),
                        cost=found.cost,
                        time_min=metrics.time_min,
                        distance_km=metrics.distance_km,
                        delay_min=metrics.delay_min,
                        hops=len(found.nodes) - 1,
                        runtime_sec=found.runtime_sec,
                        iterations=found.iterations,
                        convergence=found.convergence,
                        gap_pct=100.0 * (found.cost - exact.cost) / exact.cost if exact.cost > 0 else 0.0,
                    )
                )
        except NoPathError as error:
            hint = f" ({len(stored.closed)} closed road(s) may have cut it off; reopen one to restore the route)" if stored.closed else ""
            raise InvalidProblemError(f"{error}{hint}") from error
        traffic = stored.traffic

    return ShortestPathResponse(
        graph_id=stored.graph_id,
        source=req.source,
        target=req.target,
        cost_weights=req.cost_weights,
        exact_cost=exact.cost,
        results=results,
        traffic=traffic,
    )
