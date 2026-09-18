"""
Classical (velocity-based) PSO baseline. Same random-key particle encoding and
fitness function as QPSO (see core/qpso.py) so the comparison isolates the
effect of the quantum update rule from everything else:

    v = w*v + c1*r1*(pbest - x) + c2*r2*(gbest - x)
    x = x + v

`w` (inertia) is annealed 0.9 -> 0.4 across iterations, the standard schedule
that balances early exploration against late convergence -- the classical
counterpart to QPSO's beta annealing.

`memetic_interval` mirrors QPSO's mid-search 2-opt polish of personal bests
(see core/qpso.py, core/local_search.py) -- opt-in and off by default here
too, for the same reason: see docs/BENCHMARKS.md, it ended up hurting QPSO's
relative advantage rather than helping it.
"""

from __future__ import annotations

import time

import numpy as np

from app.core.graph_model import TrafficGraph
from app.core.local_search import refine_positions_with_two_opt
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem


class ClassicalPSO:
    def __init__(
        self,
        graph: TrafficGraph,
        request: RouteRequest,
        n_particles: int = 40,
        n_iterations: int = 800,
        w_start: float = 0.9,
        w_end: float = 0.4,
        c1: float = 2.0,
        c2: float = 2.0,
        v_max: float = 0.5,
        penalty_weight: float = 1000.0,
        memetic_interval: int | None = None,
        memetic_max_passes: int = 10,
        seed: int | None = None,
    ):
        self.problem = RoutingProblem(graph, request)
        self.stops = list(dict.fromkeys(request.stops))
        self.n = len(self.stops)
        self.n_particles = n_particles
        self.n_iterations = n_iterations
        self.w_start = w_start
        self.w_end = w_end
        self.c1 = c1
        self.c2 = c2
        self.v_max = v_max
        self.penalty_weight = penalty_weight
        self.memetic_interval = memetic_interval
        self.memetic_max_passes = memetic_max_passes
        self.rng = np.random.default_rng(seed)

    def _decode(self, position: np.ndarray) -> list:
        order = np.argsort(position)
        return [self.stops[i] for i in order]

    def _fitness(self, position: np.ndarray) -> float:
        return self.problem.cost(self._decode(position), self.penalty_weight)

    def _fitness_batch(self, positions: np.ndarray) -> np.ndarray:
        return np.array([self._fitness(pos) for pos in positions])

    def run(self) -> OptimizationResult:
        start = time.perf_counter()

        positions = self.rng.random((self.n_particles, self.n))
        velocities = self.rng.uniform(-self.v_max, self.v_max, (self.n_particles, self.n))

        pbest = positions.copy()
        pbest_fit = self._fitness_batch(positions)

        gbest_idx = int(np.argmin(pbest_fit))
        gbest = pbest[gbest_idx].copy()
        gbest_fit = float(pbest_fit[gbest_idx])

        history = [gbest_fit]

        for iteration in range(self.n_iterations):
            progress = iteration / max(1, self.n_iterations - 1)
            w = self.w_start - (self.w_start - self.w_end) * progress

            r1 = self.rng.random((self.n_particles, self.n))
            r2 = self.rng.random((self.n_particles, self.n))

            velocities = (
                w * velocities
                + self.c1 * r1 * (pbest - positions)
                + self.c2 * r2 * (gbest - positions)
            )
            velocities = np.clip(velocities, -self.v_max, self.v_max)

            positions = np.clip(positions + velocities, 0.0, 1.0)

            fitness = self._fitness_batch(positions)
            improved = fitness < pbest_fit
            pbest[improved] = positions[improved]
            pbest_fit[improved] = fitness[improved]

            if self.memetic_interval and (iteration + 1) % self.memetic_interval == 0:
                pbest, pbest_fit = refine_positions_with_two_opt(
                    pbest, self.stops, self.problem, self.penalty_weight, self.memetic_max_passes
                )

            iter_best_idx = int(np.argmin(pbest_fit))
            if pbest_fit[iter_best_idx] < gbest_fit:
                gbest_fit = float(pbest_fit[iter_best_idx])
                gbest = pbest[iter_best_idx].copy()

            history.append(gbest_fit)

        runtime_sec = time.perf_counter() - start
        best_route = self.problem.evaluate(self._decode(gbest)).route

        return OptimizationResult(
            best_route=best_route,
            best_cost=gbest_fit,
            convergence_history=history,
            runtime_sec=runtime_sec,
            iterations=self.n_iterations,
            n_particles=self.n_particles,
        )
