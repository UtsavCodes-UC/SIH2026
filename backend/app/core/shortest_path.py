"""
Shortest path between two points: the exact answer (Dijkstra) and a quantum-inspired search for it (QPSO).

The problem statement asks for a framework that solves large-scale routing AND shortest-path problems. For a single
source and target on a graph with non-negative arc costs Dijkstra is exact and fast, so it is the reference every
search here is measured against, not a competitor to beat. What the metaheuristics show is that the same machinery
(random-key particles, the QPSO update) handles a second kind of problem.

Encoding (priority-based, Gen and Cheng): a particle is a vector of one priority in [0, 1] per node of a corridor around
the source and target. To decode it, start at the source and repeatedly step to the not-yet-visited out-neighbour with the
highest priority; when a node has no such neighbour it is a dead end, so step back and never return to it. This always
reaches the target if the target can be reached at all, and a path's cost is the sum of its arc costs under the same
`CostWeights` blend the vehicle-routing solvers use (time, distance, congestion; default plain travel time). The search
minimizes that cost; the priorities that make the decoder follow the cheapest route are what it has to find.

The corridor keeps the dimension small on big maps: nodes whose detour through them, measured as straight-line distance
source -> node -> target, is within `corridor` times the straight-line source -> target distance (grown until the target
is reachable inside it; the whole graph if the nodes have no positions). It is an approximation: the best path may leave
the corridor, which the comparison with Dijkstra would show.

QPSO and classical PSO use exactly the update rules of core/qpso.py and core/baselines/classical_pso.py; the genetic
algorithm works on the same real-valued priority vectors (tournament selection, uniform crossover, Gaussian mutation,
elitism), so the three are compared like for like.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.core.cost_model import CostWeights, path_metrics
from app.core.graph_model import TrafficGraph

JUMP_REFERENCE_DIMENSION = 50  # as in qpso.py: beyond this many dimensions the QPSO jump shrinks in proportion


class NoPathError(ValueError):
    """The target cannot be reached from the source on this directed graph."""


@dataclass
class PathResult:
    algorithm: str
    nodes: list  # source ... target
    cost: float  # sum of arc costs under the weights
    convergence: list[float]  # best cost per iteration (one entry for the exact solver)
    runtime_sec: float
    iterations: int


def path_cost(graph: TrafficGraph, nodes, weights: CostWeights | None = None) -> float:
    """Cost of a node path: the sum of its arc costs under `weights` (plain travel time when None)."""
    weights = weights or CostWeights()
    g = graph.graph
    return sum(weights.arc_cost(g[a][b]) for a, b in zip(nodes, nodes[1:]))


def dijkstra_path(graph: TrafficGraph, source, target, weights: CostWeights | None = None) -> PathResult:
    """The exact cheapest path (Dijkstra, through networkx)."""
    started = time.perf_counter()
    if source == target:
        nodes = [source]
    else:
        try:
            nodes = graph.shortest_path(source, target, weights)
        except Exception as error:  # networkx raises NetworkXNoPath (or a node-not-found error)
            raise NoPathError(f"no route from node {source!r} to node {target!r}") from error
    cost = path_cost(graph, nodes, weights)
    return PathResult("dijkstra", nodes, cost, [cost], time.perf_counter() - started, 1)


class PathProblem:
    """A source, a target and the corridor of nodes a swarm searches over, with the arcs inside it."""

    def __init__(self, graph: TrafficGraph, source, target, weights: CostWeights | None = None, corridor: float = 1.6):
        g = graph.graph
        for node in (source, target):
            if node not in g:
                raise NoPathError(f"node {node!r} is not in the graph")
        if source == target:
            raise ValueError("source and target must be different nodes")
        self.graph, self.source, self.target = graph, source, target
        self.weights = weights or CostWeights()

        nodes = list(g.nodes)
        allowed = self._corridor(g, nodes, source, target, corridor)
        self.nodes = [n for n in nodes if n in allowed]
        self.index = {n: i for i, n in enumerate(self.nodes)}
        self.dimension = len(self.nodes)
        self.adjacency = [
            [(self.index[v], self.weights.arc_cost(data)) for v, data in g[u].items() if v in self.index] for u in self.nodes
        ]
        self.start, self.goal = self.index[source], self.index[target]
        self.toward_target = self._toward_target(g)
        if not self._reachable():
            raise NoPathError(f"no route from node {source!r} to node {target!r}")

    def _toward_target(self, g) -> np.ndarray | None:
        """A starting particle that needs no graph search: nodes nearer the target (straight line, from node positions)
        get higher priority, so decoding it walks greedily towards the target. None if the nodes have no positions."""
        positions = [g.nodes[n].get("pos") for n in self.nodes]
        if any(p is None for p in positions):
            return None
        pts = np.asarray(positions, dtype=float)
        away = np.linalg.norm(pts - pts[self.goal], axis=1)
        return 1.0 - away / max(float(away.max()), 1e-9)

    def _corridor(self, g, nodes, source, target, factor: float) -> set:
        positions = {n: g.nodes[n].get("pos") for n in nodes}
        if any(p is None for p in positions.values()):
            return set(nodes)  # no geometry to build a corridor from
        pts = {n: np.asarray(p, dtype=float) for n, p in positions.items()}
        direct = float(np.linalg.norm(pts[source] - pts[target]))
        detour = {n: float(np.linalg.norm(pts[source] - pts[n]) + np.linalg.norm(pts[n] - pts[target])) for n in nodes}
        while True:
            inside = {n for n in nodes if detour[n] <= factor * max(direct, 1e-9)} | {source, target}
            if len(inside) == len(nodes) or self._connected(g, inside, source, target):
                return inside
            factor *= 1.25

    @staticmethod
    def _connected(g, inside, source, target) -> bool:
        seen, frontier = {source}, [source]
        while frontier:
            u = frontier.pop()
            if u == target:
                return True
            for v in g[u]:
                if v in inside and v not in seen:
                    seen.add(v)
                    frontier.append(v)
        return False

    def _reachable(self) -> bool:
        seen, frontier = {self.start}, [self.start]
        while frontier:
            u = frontier.pop()
            if u == self.goal:
                return True
            for v, _ in self.adjacency[u]:
                if v not in seen:
                    seen.add(v)
                    frontier.append(v)
        return False

    def decode(self, priority: np.ndarray) -> tuple[list[int], float]:
        """Walk from the source to the target following the highest priorities, stepping back out of dead ends. Returns the
        path as corridor indices and its cost."""
        visited = np.zeros(self.dimension, dtype=bool)
        visited[self.start] = True
        path, cost_to = [self.start], [0.0]
        adjacency, goal = self.adjacency, self.goal
        while path:
            u = path[-1]
            if u == goal:
                return path, cost_to[-1]
            best, best_priority, best_cost = -1, -1.0, 0.0
            for v, c in adjacency[u]:
                if not visited[v] and priority[v] > best_priority:
                    best, best_priority, best_cost = v, priority[v], c
            if best < 0:  # dead end: back out of it, and never come back
                path.pop()
                cost_to.pop()
                continue
            visited[best] = True
            path.append(best)
            cost_to.append(cost_to[-1] + best_cost)
        return [], float("inf")  # cannot happen once the target is known to be reachable

    def nodes_of(self, indices: list[int]) -> list:
        return [self.nodes[i] for i in indices]


def _beta_schedule(dimension: int) -> tuple[float, float]:
    scale = min(1.0, JUMP_REFERENCE_DIMENSION / dimension)
    return 1.0 * scale, 0.2 * scale


def search_path(
    problem: PathProblem,
    algorithm: str = "qpso",
    n_particles: int = 30,
    n_iterations: int = 200,
    seed: int | None = None,
    warm_start: bool = True,
) -> PathResult:
    """QPSO, classical PSO or a genetic algorithm searching for the cheapest path over `problem`'s priority vectors.
    With `warm_start` one particle begins as the "walk towards the target" priorities (`PathProblem.toward_target`); the
    rest are random, as in core/warm_start.py for the routing problem."""
    if algorithm not in ("qpso", "pso", "ga"):
        raise ValueError(f"unknown path search {algorithm!r}")
    started = time.perf_counter()
    rng = np.random.default_rng(seed)
    n, d = n_particles, problem.dimension

    def fitness_of(batch: np.ndarray) -> np.ndarray:
        return np.array([problem.decode(x)[1] for x in batch])

    positions = rng.random((n, d))
    if warm_start and problem.toward_target is not None:
        positions[0] = problem.toward_target
    fitness = fitness_of(positions)
    best_i = int(np.argmin(fitness))
    best_x, best_f = positions[best_i].copy(), float(fitness[best_i])
    history = [best_f]

    if algorithm == "ga":
        for _ in range(n_iterations):
            new = [best_x.copy()]  # elitism
            while len(new) < n:
                pick = lambda: positions[min(rng.integers(0, n, 3), key=lambda i: fitness[i])]  # noqa: E731 tournament of 3
                a, b = pick(), pick()
                child = np.where(rng.random(d) < 0.5, a, b)  # uniform crossover
                mutate = rng.random(d) < 1.0 / d
                child = np.clip(child + mutate * rng.normal(0.0, 0.2, d), 0.0, 1.0)  # Gaussian mutation
                new.append(child)
            positions = np.array(new)
            fitness = fitness_of(positions)
            i = int(np.argmin(fitness))
            if fitness[i] < best_f:
                best_x, best_f = positions[i].copy(), float(fitness[i])
            history.append(best_f)
    else:
        pbest, pbest_f = positions.copy(), fitness.copy()
        beta0, beta1 = _beta_schedule(d)
        velocities = rng.uniform(-0.5, 0.5, (n, d))
        for t in range(n_iterations):
            progress = t / max(1, n_iterations - 1)
            if algorithm == "qpso":  # core/qpso.py
                beta = beta0 - (beta0 - beta1) * progress
                mbest = pbest.mean(axis=0)
                phi = rng.random((n, d))
                attractor = phi * pbest + (1 - phi) * best_x
                u = np.clip(rng.random((n, d)), 1e-9, 1 - 1e-9)
                sign = rng.choice([-1.0, 1.0], size=(n, d))
                positions = np.clip(attractor + sign * beta * np.abs(mbest - positions) * np.log(1.0 / u), 0.0, 1.0)
            else:  # core/baselines/classical_pso.py
                w = 0.9 - 0.5 * progress
                r1, r2 = rng.random((n, d)), rng.random((n, d))
                velocities = np.clip(w * velocities + 2.0 * r1 * (pbest - positions) + 2.0 * r2 * (best_x - positions), -0.5, 0.5)
                positions = np.clip(positions + velocities, 0.0, 1.0)
            fitness = fitness_of(positions)
            better = fitness < pbest_f
            pbest[better], pbest_f[better] = positions[better], fitness[better]
            i = int(np.argmin(pbest_f))
            if pbest_f[i] < best_f - 1e-12:
                best_x, best_f = pbest[i].copy(), float(pbest_f[i])
            history.append(best_f)

    indices, cost = problem.decode(best_x)
    return PathResult(algorithm, problem.nodes_of(indices), cost, history, time.perf_counter() - started, n_iterations)


def find_path(
    graph: TrafficGraph,
    source,
    target,
    algorithm: str = "dijkstra",
    weights: CostWeights | None = None,
    n_particles: int = 30,
    n_iterations: int = 200,
    seed: int | None = None,
    corridor: float = 1.6,
    warm_start: bool = True,
) -> PathResult:
    """One entry point for the API: the exact solver or one of the three searches."""
    if algorithm == "dijkstra":
        return dijkstra_path(graph, source, target, weights)
    return search_path(PathProblem(graph, source, target, weights, corridor), algorithm, n_particles, n_iterations, seed, warm_start)


def describe(graph: TrafficGraph, nodes) -> dict:
    """Real minutes, kilometres and congestion delay along a node path."""
    m = path_metrics(graph, nodes)
    return {"time_min": m.time_min, "distance_km": m.distance_km, "delay_min": m.delay_min}
