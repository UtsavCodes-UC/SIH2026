from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Algorithm = Literal["qpso", "pso", "ga", "nearest_neighbor"]


class ProblemSpec(BaseModel):
    """Which routing problem to solve on a stored graph. Anything left out is filled
    in deterministically from `seed`, and the resolved values are echoed back in the
    response so the same problem can be re-run (e.g. after the traffic changes)."""

    graph_id: str
    depot: int | None = Field(None, description="node id; default: the node nearest the network centre")
    stops: list[int] | None = Field(None, description="node ids to visit; default: `n_stops` random nodes")
    n_stops: int = Field(15, ge=1, le=150)
    demands: dict[int, float] | None = Field(None, description="load per stop; default: random 5-25")
    n_vehicles: int | None = Field(None, ge=1, le=40, description="default: enough vehicles for ~85% fleet utilization")
    vehicle_capacity: float = Field(100.0, gt=0)
    seed: int | None = 1


class OptimizeRequest(ProblemSpec):
    algorithm: Algorithm = "qpso"
    n_particles: int = Field(40, ge=5, le=200, description="swarm size (GA: population size)")
    n_iterations: int = Field(800, ge=10, le=3000, description="iterations (GA: generations)")
    polish: bool = Field(True, description="apply a 2-opt polish to each vehicle's route")


class BenchmarkRequest(ProblemSpec):
    n_particles: int = Field(40, ge=5, le=200)
    n_iterations: int = Field(800, ge=10, le=3000)
    polish: bool = True


class RouteOut(BaseModel):
    vehicle: int
    nodes: list[int]  # [depot, stop, ..., depot]
    path: list[list[float]]  # [lat, lon] polyline along the road network
    load: float
    time_min: float
    distance_km: float


class ResolvedProblem(BaseModel):
    depot: int
    stops: list[int]
    demands: dict[int, float]
    n_vehicles: int
    vehicle_capacity: float


class OptimizeResponse(BaseModel):
    graph_id: str
    algorithm: Algorithm
    problem: ResolvedProblem
    routes: list[RouteOut]
    total_time_min: float
    total_distance_km: float
    capacity_violation: float
    feasible: bool
    raw_cost: float  # the algorithm's own result, before the polish
    cost: float  # final cost (after the polish when `polished`)
    polished: bool
    convergence: list[float]  # best raw cost per iteration
    runtime_sec: float
    iterations: int
    warnings: list[str] = []


class BenchmarkAlgorithmOut(BaseModel):
    name: str
    raw_cost: float  # travel time + overload penalty, the quantity the algorithms minimize
    time_min: float  # the raw result's travel time alone
    capacity_violation: float  # the raw result's total overload (0 = every vehicle within capacity)
    polished_cost: float | None
    raw_gap_pct: float | None  # vs the exact optimum, when one exists
    polished_gap_pct: float | None
    runtime_sec: float
    iterations: int
    convergence: list[float]


class BenchmarkResponse(BaseModel):
    graph_id: str
    problem: ResolvedProblem
    n_nodes: int
    n_stops: int
    exact_cost: float | None
    algorithms: list[BenchmarkAlgorithmOut]
    warnings: list[str] = []
