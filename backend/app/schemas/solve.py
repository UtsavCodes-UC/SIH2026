from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.graph import TrafficInfo

Algorithm = Literal["qpso", "pso", "ga", "nearest_neighbor", "route_search"]

TIME_LIMIT_DESCRIPTION = (
    "route search only: how long the iterated search may run, in seconds (it stops sooner on a small problem "
    "that has stopped improving). Ignored by the other algorithms"
)


class CostWeightsSpec(BaseModel):
    """What the optimizer minimizes, as a blend: time x minutes driven + distance x km + congestion x minutes lost to
    congestion (extra time compared with free flow). Only the ratios matter. The default, time alone, is plain travel time."""

    time: float = Field(1.0, ge=0, le=1000)
    distance: float = Field(0.0, ge=0, le=1000)
    congestion: float = Field(0.0, ge=0, le=1000)

    @model_validator(mode="after")
    def _something_to_minimize(self):
        if self.time + self.distance + self.congestion <= 0:
            raise ValueError("at least one weight must be positive")
        return self


class TimeWindowSpec(BaseModel):
    """A stop may be served between `earliest` and `latest`, in minutes after the vans leave the depot. A van that
    arrives early waits; one that arrives late still serves the stop and the lateness is penalized (soft window)."""

    earliest: float = Field(0.0, ge=0, le=100_000)
    latest: float = Field(..., ge=0, le=100_000)

    @model_validator(mode="after")
    def _ordered(self):
        if self.latest < self.earliest:
            raise ValueError("a time window needs earliest <= latest")
        return self


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
    cost_weights: CostWeightsSpec = Field(default_factory=CostWeightsSpec, description="what to minimize: time, distance and congestion weights")
    time_windows: dict[int, TimeWindowSpec] | None = Field(None, description="stop id -> window; stops left out have none")
    random_windows: bool = Field(False, description="give every stop that has no window a demo window, drawn from `seed`")
    service_time_min: float = Field(0.0, ge=0, le=240, description="minutes spent at each stop (moves the clock the windows run on)")
    time_window_penalty: float = Field(10.0, ge=0, le=1000, description="cost per minute a van arrives after a window closes")
    seed: int | None = 1


class OptimizeRequest(ProblemSpec):
    algorithm: Algorithm = "qpso"
    n_particles: int = Field(40, ge=5, le=200, description="swarm size (GA: population size)")
    n_iterations: int = Field(800, ge=10, le=3000, description="iterations (GA: generations)")
    polish: bool = Field(True, description="polish the result: 2-opt inside each route, then move stops between vehicles")
    warm_start: bool = Field(
        True,
        description="PSO, GA and QPSO begin with the nearest-neighbour solution in their population. Essential from "
        "about 50 stops, where a random start loses to nearest neighbour itself; turn it off to compare the algorithms from scratch",
    )
    time_limit_sec: float = Field(10.0, ge=1, le=60, description=TIME_LIMIT_DESCRIPTION)


class BenchmarkRequest(ProblemSpec):
    n_particles: int = Field(40, ge=5, le=200)
    n_iterations: int = Field(800, ge=10, le=3000)
    polish: bool = True
    warm_start: bool = Field(True, description="every metaheuristic starts from the same nearest-neighbour seed (fair; differences shrink)")
    include_route_search: bool = Field(False, description="also run the route search (nearest neighbour, local search between vehicles, iterated search) and add it to the comparison")
    time_limit_sec: float = Field(10.0, ge=1, le=60, description=TIME_LIMIT_DESCRIPTION)


class StopTimingOut(BaseModel):
    stop: int
    arrival_min: float
    start_min: float  # when service begins: the arrival, or the window's opening if the van arrived early
    wait_min: float
    late_min: float
    earliest: float | None
    latest: float | None


class RouteOut(BaseModel):
    vehicle: int
    nodes: list[int]  # [depot, stop, ..., depot]
    path: list[list[float]]  # [lat, lon] polyline along the road network
    load: float
    time_min: float
    distance_km: float
    delay_min: float = 0.0  # of the time_min, the minutes lost to congestion compared with free flow
    late_min: float = 0.0  # minutes this van arrives after windows closed (time windows only)
    wait_min: float = 0.0  # minutes it waits for windows to open
    end_min: float | None = None  # back at the depot, waiting and service time included (time windows only)
    schedule: list[StopTimingOut] | None = None  # arrival at each stop against its window (time windows only)


class ResolvedProblem(BaseModel):
    depot: int
    stops: list[int]
    demands: dict[int, float]
    n_vehicles: int
    vehicle_capacity: float
    cost_weights: CostWeightsSpec = CostWeightsSpec()
    time_windows: dict[int, TimeWindowSpec] | None = None
    service_time_min: float = 0.0
    time_window_penalty: float = 10.0


class OptimizeResponse(BaseModel):
    graph_id: str
    algorithm: Algorithm
    problem: ResolvedProblem
    routes: list[RouteOut]
    total_time_min: float  # real minutes driven, added over all vehicles, whatever the weights were
    total_distance_km: float
    total_delay_min: float = 0.0  # of total_time_min, the minutes lost to congestion
    total_late_min: float = 0.0  # minutes vans arrived after a window closed, over all stops (0 without time windows)
    total_wait_min: float = 0.0  # minutes vans waited for a window to open
    late_stops: int = 0  # stops served after their window closed
    capacity_violation: float
    feasible: bool
    raw_cost: float  # the algorithm's own result, before the polish
    cost: float  # final cost (after the polish when `polished`): the WEIGHTED cost, plus the overload penalty
    polished: bool
    warm_start: bool  # the swarm began with the nearest-neighbour solution in it
    convergence: list[float]  # best raw cost per iteration
    runtime_sec: float
    iterations: int
    warnings: list[str] = []
    traffic: TrafficInfo  # the traffic conditions this plan was computed under


class BenchmarkAlgorithmOut(BaseModel):
    name: str
    raw_cost: float  # travel time + overload penalty, the quantity the algorithms minimize
    time_min: float  # the raw result's travel time alone
    capacity_violation: float  # the raw result's total overload (0 = every vehicle within capacity)
    lateness_min: float = 0.0  # the raw result's total lateness against the time windows (0 without windows)
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
    warm_start: bool
    warnings: list[str] = []
    traffic: TrafficInfo
