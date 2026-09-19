"""Shared result type for every route-finding algorithm (QPSO, baselines, exact
solvers) so the benchmark harness and API can treat them interchangeably."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptimizationResult:
    best_route: list  # flat depot-delimited route, e.g. [0, a, b, 0, c, 0]; see vrp_formulation.split_at_depot
    best_cost: float
    convergence_history: list[float]
    runtime_sec: float
    iterations: int
    n_particles: int  # population size for population-based methods; 1 for constructive/exact ones
