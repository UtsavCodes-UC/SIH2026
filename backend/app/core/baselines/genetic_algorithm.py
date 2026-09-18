"""
Genetic Algorithm baseline for the routing problem. Unlike QPSO/PSO (which
optimize a continuous random-key vector and decode it into a permutation),
the GA operates directly on the permutation of stops:

    selection  : tournament selection (size k)
    crossover  : order crossover (OX) -- preserves a contiguous slice from one
                 parent, fills the rest from the other in relative order, so
                 every child stays a valid permutation
    mutation   : swap-mutation with probability `mutation_rate`
    elitism    : the single best individual always survives to the next generation
"""

from __future__ import annotations

import time

import numpy as np

from app.core.graph_model import TrafficGraph
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RouteRequest, RoutingProblem


class GeneticAlgorithm:
    def __init__(
        self,
        graph: TrafficGraph,
        request: RouteRequest,
        population_size: int = 40,
        n_generations: int = 150,
        tournament_size: int = 3,
        mutation_rate: float = 0.15,
        penalty_weight: float = 1000.0,
        seed: int | None = None,
    ):
        self.problem = RoutingProblem(graph, request)
        self.stops = list(dict.fromkeys(request.stops))
        self.n = len(self.stops)
        self.population_size = population_size
        self.n_generations = n_generations
        self.tournament_size = tournament_size
        self.mutation_rate = mutation_rate
        self.penalty_weight = penalty_weight
        self.rng = np.random.default_rng(seed)

    def _fitness(self, individual: np.ndarray) -> float:
        order = [self.stops[i] for i in individual]
        return self.problem.cost(order, self.penalty_weight)

    def _tournament_select(self, population: np.ndarray, fitness: np.ndarray) -> np.ndarray:
        contenders = self.rng.integers(0, len(population), self.tournament_size)
        winner = contenders[np.argmin(fitness[contenders])]
        return population[winner]

    def _order_crossover(self, parent_a: np.ndarray, parent_b: np.ndarray) -> np.ndarray:
        n = self.n
        i, j = sorted(self.rng.choice(n, size=2, replace=False))
        child = np.full(n, -1, dtype=int)
        child[i : j + 1] = parent_a[i : j + 1]

        fill_values = [gene for gene in parent_b if gene not in child[i : j + 1]]
        fill_positions = [p for p in range(n) if child[p] == -1]
        for pos, value in zip(fill_positions, fill_values):
            child[pos] = value
        return child

    def _mutate(self, individual: np.ndarray) -> np.ndarray:
        if self.rng.random() < self.mutation_rate and self.n > 1:
            i, j = self.rng.choice(self.n, size=2, replace=False)
            individual[i], individual[j] = individual[j], individual[i]
        return individual

    def run(self) -> OptimizationResult:
        start = time.perf_counter()

        population = np.array(
            [self.rng.permutation(self.n) for _ in range(self.population_size)]
        )
        fitness = np.array([self._fitness(ind) for ind in population])

        best_idx = int(np.argmin(fitness))
        best_individual = population[best_idx].copy()
        best_fit = float(fitness[best_idx])
        history = [best_fit]

        for _ in range(self.n_generations):
            new_population = [best_individual.copy()]  # elitism

            while len(new_population) < self.population_size:
                parent_a = self._tournament_select(population, fitness)
                parent_b = self._tournament_select(population, fitness)
                child = self._order_crossover(parent_a, parent_b)
                child = self._mutate(child)
                new_population.append(child)

            population = np.array(new_population)
            fitness = np.array([self._fitness(ind) for ind in population])

            gen_best_idx = int(np.argmin(fitness))
            if fitness[gen_best_idx] < best_fit:
                best_fit = float(fitness[gen_best_idx])
                best_individual = population[gen_best_idx].copy()

            history.append(best_fit)

        runtime_sec = time.perf_counter() - start
        best_order = [self.stops[i] for i in best_individual]
        best_route = self.problem.evaluate(best_order).route

        return OptimizationResult(
            best_route=best_route,
            best_cost=best_fit,
            convergence_history=history,
            runtime_sec=runtime_sec,
            iterations=self.n_generations,
            n_particles=self.population_size,
        )
