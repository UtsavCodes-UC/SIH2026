"""
Hybrid swarm engine: random-key QPSO (or classical PSO) with the components that make a metaheuristic
competitive on 100+ stops, each an independent switch so it can be ablated.

    Distance matrix
        -> hybrid initialization      nearest neighbour, nearest neighbour + 2-opt, randomized nearest
                                      neighbour + 2-opt, and the rest random
        -> quantum (or classical) update, with an adaptive contraction coefficient beta
        -> permutation decoder        argsort of the random keys (then the greedy vehicle split)
        -> elite archive              the best distinct tours found; one of them, chosen at random and
                                      biased to the best, is each particle's global attractor
        -> 2-opt on a few particles   every few iterations the best personal bests that are not yet 2-opt
                                      optimal are polished and written back into the swarm
        -> diversity restart          when the search stalls or the swarm collapses, the worst particles
                                      restart from a kicked elite (double bridge) or a randomized nearest
                                      neighbour tour, each followed by 2-opt (an iterated-local-search step)
        -> best tour

The operator is swappable (`operator="qpso"` or `"pso"`) and everything else is shared, so "does the QPSO
update itself matter?" can be answered with equal treatment. With every component switched off the engine
is bit-for-bit the plain QPSO in `qpso.py` (or the plain PSO in `baselines/classical_pso.py`); tests pin that.

Design choices, with the reasons they exist (docs/BENCHMARKS.md, Finding 11):

- 2-opt runs on a few particles at a time, not on the whole swarm. Applying it to every particle made them
  all fall into the same local optima and erased the difference between algorithms (Finding 3). It acts on
  swarm-found tours, not only on elites: the elites are seeded 2-opt optima, so polishing just those can
  never improve anything (the first version of this engine did exactly that and never beat its own seed).
- Restarts kick elite tours and 2-opt them instead of drawing fresh random ones: at 100 stops a random tour
  is far worse than anything the swarm already has.
- The contraction coefficient beta follows the size-aware schedule (`qpso.JUMP_REFERENCE_DIMENSION`) times a
  multiplier steered by the fraction of particles that improved (the classic 1/5 success rule): steps
  that rarely succeed are too big, steps that nearly always succeed are too timid.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.core.baselines.dijkstra_baseline import nearest_neighbor_order
from app.core.graph_model import TrafficGraph
from app.core.local_search import encode_order, two_opt_order
from app.core.qpso import JUMP_REFERENCE_DIMENSION
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.core.warm_start import heuristic_seed_orders

BETA_MULTIPLIER_RANGE = (0.25, 1.5)
BETA_ADAPTATION_RATE = 0.1
SUCCESS_SMOOTHING = 0.1


@dataclass
class Elite:
    order: tuple
    cost: float


class EliteArchive:
    """The best `size` distinct tours found so far, best first. Distinct means a different visiting order."""

    def __init__(self, size: int):
        self.size = size
        self.entries: list[Elite] = []
        self._orders: set[tuple] = set()
        self._keys: np.ndarray | None = None  # cached random-key form of the entries

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def worst_cost(self) -> float:
        return self.entries[-1].cost if len(self.entries) >= self.size else float("inf")

    def offer(self, order: tuple, cost: float) -> bool:
        if order in self._orders or cost >= self.worst_cost:
            return False
        position = next((i for i, e in enumerate(self.entries) if cost < e.cost), len(self.entries))
        self.entries.insert(position, Elite(order, cost))
        self._orders.add(order)
        if len(self.entries) > self.size:
            dropped = self.entries.pop()
            self._orders.discard(dropped.order)
        self._keys = None
        return True

    def attractors(self, rng: np.random.Generator, count: int, stops: list) -> np.ndarray:
        """`count` random-key vectors, each one elite chosen at random, biased toward the better ones."""
        if self._keys is None:
            self._keys = np.array([encode_order(list(e.order), stops) for e in self.entries])
        m = len(self.entries)
        chosen = np.minimum(rng.integers(m, size=count), rng.integers(m, size=count))
        return self._keys[chosen]


def double_bridge(order: list, rng: np.random.Generator) -> list:
    """The standard tour perturbation: cut at three points and swap the two middle pieces."""
    n = len(order)
    if n < 8:
        i, j = rng.choice(n, size=2, replace=False)
        kicked = list(order)
        kicked[i], kicked[j] = kicked[j], kicked[i]
        return kicked
    a, b, c = sorted(int(x) for x in rng.choice(np.arange(1, n), size=3, replace=False))
    return order[:a] + order[b:c] + order[a:b] + order[c:]


class HybridSwarm:
    def __init__(
        self,
        graph: TrafficGraph,
        request: RouteRequest,
        operator: str = "qpso",
        n_particles: int = 40,
        n_iterations: int = 800,
        penalty_weight: float = 1000.0,
        # QPSO: contraction-expansion schedule (None: size-aware default, see qpso.py)
        beta_start: float | None = None,
        beta_end: float | None = None,
        # PSO: the same parameters as baselines/classical_pso.py
        w_start: float = 0.9,
        w_end: float = 0.4,
        c1: float = 2.0,
        c2: float = 2.0,
        v_max: float = 0.5,
        # components
        hybrid_init: bool = True,
        rnn_fraction: float = 0.25,
        rnn_k: int = 4,
        adaptive_beta: bool = True,
        target_success: float = 0.2,
        elite_archive: bool = True,
        elite_size: int = 8,
        elite_attractor: bool = True,
        local_search: bool = True,
        local_search_interval: int = 10,
        local_search_top: int = 3,
        restart: bool = True,
        restart_patience: int | None = None,
        restart_fraction: float = 0.25,
        restart_min_diversity: float | None = None,
        seed: int | None = None,
    ):
        if operator not in ("qpso", "pso"):
            raise ValueError("operator must be 'qpso' or 'pso'")
        if (elite_attractor or local_search or restart) and not elite_archive:
            raise ValueError("elite_attractor, local_search and restart all draw on the elite archive: switch elite_archive on")
        self.problem = RoutingProblem(graph, request)
        self.stops = list(dict.fromkeys(request.stops))
        self.n = len(self.stops)
        self.operator = operator
        self.n_particles = n_particles
        self.n_iterations = n_iterations
        self.penalty_weight = penalty_weight
        jump_scale = min(1.0, JUMP_REFERENCE_DIMENSION / self.n)
        self.beta_start = 1.0 * jump_scale if beta_start is None else beta_start
        self.beta_end = 0.2 * jump_scale if beta_end is None else beta_end
        self.w_start, self.w_end, self.c1, self.c2, self.v_max = w_start, w_end, c1, c2, v_max
        self.hybrid_init, self.rnn_fraction, self.rnn_k = hybrid_init, rnn_fraction, rnn_k
        self.adaptive_beta = adaptive_beta and operator == "qpso"  # PSO has no beta
        self.target_success = target_success
        self.elite_archive, self.elite_size, self.elite_attractor = elite_archive, elite_size, elite_attractor
        self.local_search, self.local_search_interval, self.local_search_top = local_search, local_search_interval, local_search_top
        self.restart = restart
        self.restart_patience = restart_patience if restart_patience is not None else max(30, n_iterations // 20)
        self.restart_fraction = restart_fraction
        self.restart_min_diversity = restart_min_diversity if restart_min_diversity is not None else 1.0 / self.n
        self.rng = np.random.default_rng(seed)
        self.events = {"restarts": 0, "polished": 0, "improved_by_polish": 0}  # what the components did

    # ---- decoding and fitness (identical to qpso.py) ----------------------------------------------------

    def _decode(self, position: np.ndarray) -> list:
        return [self.stops[i] for i in np.argsort(position)]

    def _fitness(self, position: np.ndarray) -> float:
        return self.problem.cost(self._decode(position), self.penalty_weight)

    def _fitness_batch(self, positions: np.ndarray) -> np.ndarray:
        return np.array([self._fitness(pos) for pos in positions])

    # ---- components -------------------------------------------------------------------------------------

    def _seed_population(self, positions: np.ndarray) -> None:
        """Hybrid initialization: greedy and randomized-greedy tours in the first slots, random elsewhere."""
        orders = list(heuristic_seed_orders(self.problem))
        for _ in range(int(round(self.rnn_fraction * self.n_particles))):
            orders.append(two_opt_order(self.problem, nearest_neighbor_order(self.problem, self.rng, self.rnn_k)))
        for i, order in enumerate(orders[: self.n_particles]):
            positions[i] = encode_order(order, self.stops)

    def _offer(self, archive: EliteArchive, order: list, cost: float) -> None:
        archive.offer(tuple(order), cost)

    def _polish_swarm(self, archive: EliteArchive, positions, pbest, pbest_fit, polished: np.ndarray) -> None:
        """2-opt on the best few personal bests that are not yet 2-opt optimal, written back into the swarm.
        These are swarm-found tours, so polishing them reaches local optima the seeds are not in."""
        candidates = [int(i) for i in np.argsort(pbest_fit) if not polished[i]][: self.local_search_top]
        for i in candidates:
            self.events["polished"] += 1
            tour = two_opt_order(self.problem, self._decode(pbest[i]))
            cost = self.problem.cost(tour, self.penalty_weight)
            if cost < pbest_fit[i] - 1e-9:
                self.events["improved_by_polish"] += 1
                positions[i] = encode_order(tour, self.stops)
                pbest[i] = positions[i]
                pbest_fit[i] = cost
                self._offer(archive, tour, cost)
            polished[i] = True

    def _restart_worst(self, archive: EliteArchive, positions, pbest, pbest_fit, polished, velocities) -> None:
        """Replace the worst particles. Half restart from a kicked elite tour, half from randomized nearest
        neighbour, each followed by 2-opt: an iterated-local-search step from a good place. The best
        particles are never touched, so nothing already found is lost."""
        self.events["restarts"] += 1
        n_reset = max(1, int(round(self.restart_fraction * self.n_particles)))
        for i in np.argsort(pbest_fit)[-n_reset:]:
            if len(archive) and self.rng.random() < 0.5:
                order = double_bridge(list(archive.entries[int(self.rng.integers(len(archive)))].order), self.rng)
            else:
                order = nearest_neighbor_order(self.problem, self.rng, self.rnn_k)
            tour = two_opt_order(self.problem, order)
            cost = self.problem.cost(tour, self.penalty_weight)
            positions[i] = encode_order(tour, self.stops)
            pbest[i] = positions[i]
            pbest_fit[i] = cost
            polished[i] = True
            self._offer(archive, tour, cost)
            if velocities is not None:
                velocities[i] = self.rng.uniform(-self.v_max, self.v_max, self.n)

    # ---- the search ------------------------------------------------------------------------------------

    def run(self) -> OptimizationResult:
        start = time.perf_counter()
        P, n = self.n_particles, self.n
        qpso = self.operator == "qpso"

        positions = self.rng.random((P, n))
        if self.hybrid_init:
            self._seed_population(positions)
        velocities = None if qpso else self.rng.uniform(-self.v_max, self.v_max, (P, n))

        pbest = positions.copy()
        pbest_fit = self._fitness_batch(positions)
        polished = np.zeros(P, dtype=bool)  # is this personal best known to be 2-opt optimal?
        if self.hybrid_init:
            polished[: min(P, 2 + int(round(self.rnn_fraction * P)))] = True  # the seeds are
        gbest_idx = int(np.argmin(pbest_fit))
        gbest, gbest_fit = pbest[gbest_idx].copy(), float(pbest_fit[gbest_idx])
        history = [gbest_fit]

        archive = EliteArchive(self.elite_size) if self.elite_archive else None
        if archive is not None:
            for i in np.argsort(pbest_fit)[: self.elite_size]:
                self._offer(archive, self._decode(pbest[i]), float(pbest_fit[i]))

        multiplier, success_ema, stagnation = 1.0, self.target_success, 0

        for iteration in range(self.n_iterations):
            progress = iteration / max(1, self.n_iterations - 1)
            attractor_target = archive.attractors(self.rng, P, self.stops) if (archive is not None and self.elite_attractor and len(archive)) else gbest

            if qpso:
                beta = self.beta_start - (self.beta_start - self.beta_end) * progress
                if self.adaptive_beta:
                    beta *= multiplier
                mbest = pbest.mean(axis=0)
                phi = self.rng.random((P, n))
                attractor = phi * pbest + (1 - phi) * attractor_target
                u = np.clip(self.rng.random((P, n)), 1e-9, 1 - 1e-9)
                sign = self.rng.choice([-1.0, 1.0], size=(P, n))
                positions = np.clip(attractor + sign * beta * np.abs(mbest - positions) * np.log(1.0 / u), 0.0, 1.0)
            else:
                w = self.w_start - (self.w_start - self.w_end) * progress
                r1, r2 = self.rng.random((P, n)), self.rng.random((P, n))
                velocities = w * velocities + self.c1 * r1 * (pbest - positions) + self.c2 * r2 * (attractor_target - positions)
                velocities = np.clip(velocities, -self.v_max, self.v_max)
                positions = np.clip(positions + velocities, 0.0, 1.0)
                mbest = pbest.mean(axis=0)

            fitness = self._fitness_batch(positions)
            improved = fitness < pbest_fit
            pbest[improved] = positions[improved]
            pbest_fit[improved] = fitness[improved]
            polished[improved] = False

            if qpso and self.adaptive_beta:  # the 1/5 success rule, smoothed and bounded
                success_ema = (1 - SUCCESS_SMOOTHING) * success_ema + SUCCESS_SMOOTHING * float(improved.mean())
                multiplier = float(np.clip(multiplier * np.exp(BETA_ADAPTATION_RATE * (success_ema - self.target_success)), *BETA_MULTIPLIER_RANGE))

            if archive is not None:
                for i in np.flatnonzero(improved):
                    if pbest_fit[i] < archive.worst_cost:
                        self._offer(archive, self._decode(pbest[i]), float(pbest_fit[i]))
                if self.local_search and (iteration + 1) % self.local_search_interval == 0:
                    self._polish_swarm(archive, positions, pbest, pbest_fit, polished)

            best_idx = int(np.argmin(pbest_fit))
            better = pbest_fit[best_idx] < (gbest_fit - 1e-9 if qpso else gbest_fit)
            if better:
                gbest_fit, gbest = float(pbest_fit[best_idx]), pbest[best_idx].copy()
                stagnation = 0
            else:
                stagnation += 1

            if self.restart:
                diversity = float(np.abs(pbest.mean(axis=0) - positions).mean())
                if stagnation >= self.restart_patience or diversity < self.restart_min_diversity:
                    self._restart_worst(archive, positions, pbest, pbest_fit, polished, velocities)
                    stagnation = 0

            history.append(gbest_fit)

        best_route = self.problem.evaluate(self._decode(gbest)).route
        return OptimizationResult(
            best_route=best_route,
            best_cost=gbest_fit,
            convergence_history=history,
            runtime_sec=time.perf_counter() - start,
            iterations=self.n_iterations,
            n_particles=P,
        )
