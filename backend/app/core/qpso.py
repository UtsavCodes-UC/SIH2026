"""
Quantum Particle Swarm Optimization engine (Day 1 deliverable #3 — the core
optimization algorithm named in the problem statement).

Unlike classical PSO (position/velocity update), QPSO models each particle
as a quantum-mechanical delta-potential-well state around a mean-best
position (mbest). This removes the velocity term entirely:

    mbest      = mean of all particles' personal-best positions
    p          = phi * pbest_i + (1 - phi) * gbest      (phi ~ U(0,1) per dimension)
    x_i_new    = p +/- beta * |mbest - x_i| * ln(1/u)    (u ~ U(0,1), sign ~ 50/50)

`beta` (the contraction-expansion coefficient) is annealed linearly from
`beta_start` to `beta_end` across iterations: larger beta early promotes
exploration, smaller beta late promotes convergence/exploitation.

Particle encoding for routing: a particle is a continuous vector in
[0, 1]^n (n = number of stops). It is decoded into a visiting order via
random-key encoding — argsort the vector to get a permutation of `stops`.
This lets a continuous-update algorithm like QPSO solve a discrete
permutation problem without a custom discrete update rule.

Defaults (n_particles=40, n_iterations=800, beta=(1.0, 0.2)) come from a
hyperparameter sweep + validation against classical PSO (both polished with
core/local_search.two_opt) — see scripts/tune_qpso.py. Below ~400 iterations
QPSO and classical PSO are roughly a coin flip; QPSO's broader per-step
exploration only reliably outperforms PSO's more directed search once given
a longer horizon (~800 iterations validated a consistent win, 20-50 stops).

`memetic_interval` (opt-in, off by default -- see docs/BENCHMARKS.md) can
2-opt-polish every particle's personal best mid-search, not just the final
answer (core/local_search.refine_positions_with_two_opt). The hypothesis was
that this improves both the per-particle attractor AND `mbest` for QPSO at
once, a compounding effect with no equivalent in classical PSO. Ablation
testing (scripts/ablation_memetic.py) showed the opposite when applied
fairly to both algorithms: it homogenizes their personal bests into the same
2-opt basins and *reduces* QPSO's win rate over PSO (e.g. 63%->23% at 50
stops). Left in as an opt-in knob, not a default.

`weighted_mbest` (opt-in, off by default) replaces the plain mean in mbest
with a rank-weighted mean of personal bests, so better particles pull the
shared attractor harder. Unlike memetic_interval, this needs no "fair
treatment" for classical PSO -- PSO has no mbest at all, so this is a change
only QPSO can make. See docs/BENCHMARKS.md for the ablation result.

`stagnation_limit` (opt-in, off by default): if gbest hasn't improved for
this many consecutive iterations, the worst `reinjection_fraction` of
particles are reinitialized to fresh random positions (position AND
personal best), injecting new information into `mbest` rather than letting
it stay anchored to a stale region. Motivated by Findings 3 and 4 both
showing that anything which *accelerates convergence/exploitation* hurts
QPSO's edge (it comes from sustained exploration) -- this instead actively
fights premature convergence, extending exploration rather than cutting it
short. See docs/BENCHMARKS.md for the ablation result.

`adaptive_beta` (opt-in, off by default): instead of one beta shared by the
whole swarm each iteration, gives each particle its own beta based on its
current fitness rank -- worse particles get a higher multiplier (more
exploration), better particles get a lower one (more exploitation), centered
so the swarm-average beta matches the original schedule. Unlike
weighted_mbest (Finding 4), which pushed the *entire* swarm toward
exploitation together and lost, this lets good particles exploit while bad
particles keep exploring -- diversity survives even as the best solution
improves. See docs/BENCHMARKS.md for the ablation result.
"""

from __future__ import annotations

import time

import numpy as np

from app.core.graph_model import TrafficGraph
from app.core.local_search import refine_positions_with_two_opt
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem


class QPSO:
    def __init__(
        self,
        graph: TrafficGraph,
        request: RouteRequest,
        n_particles: int = 40,
        n_iterations: int = 800,
        beta_start: float = 1.0,
        beta_end: float = 0.2,
        penalty_weight: float = 1000.0,
        memetic_interval: int | None = None,
        memetic_max_passes: int = 10,
        weighted_mbest: bool = False,
        stagnation_limit: int | None = None,
        reinjection_fraction: float = 0.25,
        adaptive_beta: bool = False,
        seed: int | None = None,
    ):
        self.problem = RoutingProblem(graph, request)
        self.stops = list(dict.fromkeys(request.stops))
        self.n = len(self.stops)
        self.n_particles = n_particles
        self.n_iterations = n_iterations
        self.beta_start = beta_start
        self.beta_end = beta_end
        self.penalty_weight = penalty_weight
        self.memetic_interval = memetic_interval
        self.memetic_max_passes = memetic_max_passes
        self.weighted_mbest = weighted_mbest
        self.stagnation_limit = stagnation_limit
        self.reinjection_fraction = reinjection_fraction
        self.adaptive_beta = adaptive_beta
        self.rng = np.random.default_rng(seed)

    def _decode(self, position: np.ndarray) -> list:
        order = np.argsort(position)
        return [self.stops[i] for i in order]

    def _fitness(self, position: np.ndarray) -> float:
        return self.problem.cost(self._decode(position), self.penalty_weight)

    def _fitness_batch(self, positions: np.ndarray) -> np.ndarray:
        return np.array([self._fitness(pos) for pos in positions])

    def _compute_mbest(self, pbest: np.ndarray, pbest_fit: np.ndarray) -> np.ndarray:
        if not self.weighted_mbest:
            return pbest.mean(axis=0)

        # rank-weighted mean: rank 0 = best particle gets the most weight,
        # falling off linearly to the worst particle (weight 1)
        order = np.argsort(pbest_fit)
        ranks = np.empty(len(pbest_fit))
        ranks[order] = np.arange(len(pbest_fit))
        weights = len(pbest_fit) - ranks
        weights = weights / weights.sum()
        return (weights[:, None] * pbest).sum(axis=0)

    def _reinject_diversity(
        self, positions: np.ndarray, pbest: np.ndarray, pbest_fit: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Reinitialize the worst `reinjection_fraction` of particles (position
        AND personal best) to fresh random points, so mbest and future search
        aren't anchored entirely to a swarm that's stopped improving."""
        n_reset = max(1, int(round(self.reinjection_fraction * self.n_particles)))
        worst_idx = np.argsort(pbest_fit)[-n_reset:]

        fresh = self.rng.random((n_reset, self.n))
        positions[worst_idx] = fresh
        pbest[worst_idx] = fresh
        pbest_fit[worst_idx] = self._fitness_batch(fresh)

        return positions, pbest, pbest_fit

    def _compute_beta(self, progress: float, pbest_fit: np.ndarray) -> np.ndarray:
        """Returns a per-particle beta of shape (n_particles,). Without
        adaptive_beta every entry equals the scheduled beta_iter; with it,
        each particle's beta is beta_iter * (0.5 + rank/(n-1)) -- rank 0
        (best) gets 0.5x (more exploitative), the worst particle gets 1.5x
        (more explorative). The swarm-average multiplier is ~1.0, so the
        validated overall schedule is preserved on average.
        """
        beta_iter = self.beta_start - (self.beta_start - self.beta_end) * progress
        if not self.adaptive_beta:
            return np.full(self.n_particles, beta_iter)

        order = np.argsort(pbest_fit)
        ranks = np.empty(self.n_particles)
        ranks[order] = np.arange(self.n_particles)
        normalized_rank = ranks / max(1, self.n_particles - 1)
        multiplier = 0.5 + normalized_rank
        return beta_iter * multiplier

    def run(self) -> OptimizationResult:
        start = time.perf_counter()

        positions = self.rng.random((self.n_particles, self.n))
        pbest = positions.copy()
        pbest_fit = self._fitness_batch(positions)

        gbest_idx = int(np.argmin(pbest_fit))
        gbest = pbest[gbest_idx].copy()
        gbest_fit = float(pbest_fit[gbest_idx])

        history = [gbest_fit]
        stagnation_counter = 0

        for iteration in range(self.n_iterations):
            progress = iteration / max(1, self.n_iterations - 1)
            beta = self._compute_beta(progress, pbest_fit)
            mbest = self._compute_mbest(pbest, pbest_fit)

            phi = self.rng.random((self.n_particles, self.n))
            attractor = phi * pbest + (1 - phi) * gbest

            u = np.clip(self.rng.random((self.n_particles, self.n)), 1e-9, 1 - 1e-9)
            sign = self.rng.choice([-1.0, 1.0], size=(self.n_particles, self.n))

            positions = attractor + sign * beta[:, None] * np.abs(mbest - positions) * np.log(1.0 / u)
            positions = np.clip(positions, 0.0, 1.0)

            fitness = self._fitness_batch(positions)
            improved = fitness < pbest_fit
            pbest[improved] = positions[improved]
            pbest_fit[improved] = fitness[improved]

            if self.memetic_interval and (iteration + 1) % self.memetic_interval == 0:
                pbest, pbest_fit = refine_positions_with_two_opt(
                    pbest, self.stops, self.problem, self.penalty_weight, self.memetic_max_passes
                )

            iter_best_idx = int(np.argmin(pbest_fit))
            if pbest_fit[iter_best_idx] < gbest_fit - 1e-9:
                gbest_fit = float(pbest_fit[iter_best_idx])
                gbest = pbest[iter_best_idx].copy()
                stagnation_counter = 0
            else:
                stagnation_counter += 1

            if self.stagnation_limit and stagnation_counter >= self.stagnation_limit:
                positions, pbest, pbest_fit = self._reinject_diversity(positions, pbest, pbest_fit)
                stagnation_counter = 0

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
