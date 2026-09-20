"""Request and response models for POST /api/shortest-path."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.graph import TrafficInfo
from app.schemas.solve import CostWeightsSpec

PathAlgorithm = Literal["dijkstra", "qpso", "pso", "ga"]


class ShortestPathRequest(BaseModel):
    """The cheapest way to drive from `source` to `target`, by the exact solver (Dijkstra) and/or a quantum-inspired
    (QPSO) or classical (PSO, genetic algorithm) search. The cost is the same blend of time, distance and congestion
    as for the vehicle-routing problem; the default is plain travel time."""

    graph_id: str
    source: int
    target: int
    algorithms: list[PathAlgorithm] = Field(default_factory=lambda: ["dijkstra"], min_length=1)
    cost_weights: CostWeightsSpec = Field(default_factory=CostWeightsSpec)
    n_particles: int = Field(30, ge=5, le=200, description="swarm size (GA: population size)")
    n_iterations: int = Field(200, ge=10, le=3000, description="iterations (GA: generations)")
    warm_start: bool = Field(True, description="one particle starts as the walk-towards-the-target priorities")
    seed: int | None = 1

    @field_validator("algorithms")
    @classmethod
    def _no_duplicates(cls, value):
        return list(dict.fromkeys(value))


class PathOut(BaseModel):
    algorithm: PathAlgorithm
    nodes: list[int]  # source ... target
    path: list[list[float]]  # [lat, lon] polyline along the roads
    cost: float  # the weighted cost that was minimized
    time_min: float  # real minutes driven, whatever the weights
    distance_km: float
    delay_min: float  # of time_min, the minutes lost to congestion
    hops: int  # road segments (intersections passed through, minus one)
    runtime_sec: float
    iterations: int
    convergence: list[float]  # best cost per iteration (a single point for the exact solver)
    gap_pct: float  # how far above the exact optimum this path's cost is (0 for the exact solver)


class ShortestPathResponse(BaseModel):
    graph_id: str
    source: int
    target: int
    cost_weights: CostWeightsSpec
    exact_cost: float  # the exact optimum, from Dijkstra, whether or not it was asked for
    results: list[PathOut]
    traffic: TrafficInfo
