"""Shortest path between two points: Dijkstra as the exact reference and the priority-encoded QPSO / PSO / GA searches."""

import random

import networkx as nx
import numpy as np
import pytest

from app.core.cost_model import CostWeights
from app.core.graph_model import TrafficGraph
from app.core.shortest_path import NoPathError, PathProblem, dijkstra_path, find_path, path_cost, search_path
from app.data.synthetic_graph_generator import generate_synthetic_graph


def small_map() -> TrafficGraph:
    """0 -> 1 leads to a dead end (2). The way to the target 5 is 0 -> 3 -> 4 -> 5 (3 + 3 + 3 = 9 min), or 0 -> 1 -> 5 (2 + 20)."""
    g = TrafficGraph()
    for n in range(6):
        g.add_node(n, lat=0.0, lon=0.0, pos=(float(n), 0.0))
    for u, v, minutes, km in [(0, 1, 2, 1), (1, 2, 1, 1), (1, 5, 20, 2), (0, 3, 3, 3), (3, 4, 3, 3), (4, 5, 3, 3)]:
        g.add_edge(u, v, distance_km=km, base_travel_time_min=minutes, congestion_factor=1.0)
    return g


def random_pairs(graph, count, seed, min_hops=4):
    rng = random.Random(seed)
    nodes, pairs = list(graph.graph.nodes), []
    while len(pairs) < count:
        s, t = rng.sample(nodes, 2)
        if nx.has_path(graph.graph, s, t) and len(nx.shortest_path(graph.graph, s, t)) >= min_hops:
            pairs.append((s, t))
    return pairs


def is_valid_path(graph, result, source, target):
    g = graph.graph
    return result.nodes[0] == source and result.nodes[-1] == target and len(set(result.nodes)) == len(result.nodes) and all(g.has_edge(a, b) for a, b in zip(result.nodes, result.nodes[1:]))


class TestExact:
    def test_dijkstra_finds_the_cheapest_path_and_prices_it(self):
        g = small_map()
        result = dijkstra_path(g, 0, 5)
        assert result.nodes == [0, 3, 4, 5] and result.cost == pytest.approx(9.0)
        assert path_cost(g, result.nodes) == pytest.approx(9.0) and result.algorithm == "dijkstra"

    def test_the_weights_change_which_path_is_cheapest(self):
        g = small_map()
        assert dijkstra_path(g, 0, 5, CostWeights(1, 0, 0)).nodes == [0, 3, 4, 5]
        assert dijkstra_path(g, 0, 5, CostWeights(0, 1, 0)).nodes == [0, 1, 5]  # 3 km against 9

    def test_the_same_node_is_a_path_of_one_and_a_missing_route_is_an_error(self):
        g = small_map()
        assert dijkstra_path(g, 3, 3).nodes == [3]
        with pytest.raises(NoPathError):
            dijkstra_path(g, 5, 0)  # nothing leaves node 5
        with pytest.raises(NoPathError):
            dijkstra_path(g, 0, 99)


class TestDecoder:
    def test_it_follows_the_priorities_and_backs_out_of_a_dead_end(self):
        problem = PathProblem(small_map(), 0, 5, corridor=10)
        priority = np.zeros(problem.dimension)
        priority[problem.index[1]] = 0.9  # tempting: the dead-end branch first
        priority[problem.index[2]] = 0.8
        priority[problem.index[3]] = 0.5
        priority[problem.index[4]] = 0.4
        priority[problem.index[5]] = 0.1
        path, cost = problem.decode(priority)
        # 0 -> 1 first; from 1 it prefers node 2 (a dead end), backs out, then 1 -> 5 directly (2 + 20 minutes)
        assert problem.nodes_of(path) == [0, 1, 5] and cost == pytest.approx(22.0)

        priority[problem.index[1]] = 0.1  # now the route through 3 and 4 wins the first step
        assert problem.nodes_of(problem.decode(priority)[0]) == [0, 3, 4, 5]

    def test_every_priority_vector_reaches_the_target(self):
        graph = generate_synthetic_graph(n_nodes=40, area_size_km=8.0, seed=5)
        (s, t), = random_pairs(graph, 1, seed=2)
        problem = PathProblem(graph, s, t)
        rng = np.random.default_rng(0)
        for _ in range(50):
            path, cost = problem.decode(rng.random(problem.dimension))
            nodes = problem.nodes_of(path)
            assert nodes[0] == s and nodes[-1] == t and cost < float("inf")
            assert cost == pytest.approx(path_cost(graph, nodes))

    def test_the_corridor_is_smaller_than_the_map_and_keeps_both_ends(self):
        graph = generate_synthetic_graph(n_nodes=160, area_size_km=8.0, seed=5)
        (s, t), = random_pairs(graph, 1, seed=3)
        problem = PathProblem(graph, s, t, corridor=1.3)
        assert problem.dimension < graph.node_count and s in problem.index and t in problem.index

    def test_a_target_that_cannot_be_reached_is_reported(self):
        with pytest.raises(NoPathError):
            PathProblem(small_map(), 5, 0)
        with pytest.raises(ValueError, match="different"):
            PathProblem(small_map(), 0, 0)

    def test_the_walk_towards_the_target_particle_exists_and_decodes(self):
        graph = generate_synthetic_graph(n_nodes=40, area_size_km=8.0, seed=5)
        (s, t), = random_pairs(graph, 1, seed=4)
        problem = PathProblem(graph, s, t)
        assert problem.toward_target is not None and problem.toward_target.shape == (problem.dimension,)
        assert problem.toward_target[problem.goal] == pytest.approx(1.0)  # the target itself is the most attractive
        assert problem.decode(problem.toward_target)[1] < float("inf")


class TestSearch:
    @pytest.mark.parametrize("algorithm", ["qpso", "pso", "ga"])
    def test_every_search_returns_a_valid_path_that_is_never_cheaper_than_the_exact_one(self, algorithm):
        graph = generate_synthetic_graph(n_nodes=60, area_size_km=8.0, seed=6)
        for s, t in random_pairs(graph, 5, seed=1):
            exact = dijkstra_path(graph, s, t)
            result = search_path(PathProblem(graph, s, t), algorithm, n_particles=20, n_iterations=60, seed=1)
            assert is_valid_path(graph, result, s, t)
            assert result.cost == pytest.approx(path_cost(graph, result.nodes))  # the reported cost is the path's true cost
            assert result.cost >= exact.cost - 1e-9
            assert all(b <= a + 1e-12 for a, b in zip(result.convergence, result.convergence[1:]))  # best so far never rises
            assert len(result.convergence) == 60 + 1

    def test_qpso_finds_the_exact_optimum_on_a_small_map(self):
        graph = generate_synthetic_graph(n_nodes=40, area_size_km=8.0, seed=5)
        for s, t in random_pairs(graph, 6, seed=1, min_hops=5):
            exact = dijkstra_path(graph, s, t)
            found = search_path(PathProblem(graph, s, t), "qpso", n_particles=30, n_iterations=200, seed=3)
            assert found.cost == pytest.approx(exact.cost)

    def test_the_search_is_repeatable_for_a_seed_and_the_seed_matters(self):
        graph = generate_synthetic_graph(n_nodes=60, area_size_km=8.0, seed=6)
        (s, t), = random_pairs(graph, 1, seed=8, min_hops=6)
        problem = PathProblem(graph, s, t)
        a = search_path(problem, "qpso", 20, 40, seed=5)
        b = search_path(problem, "qpso", 20, 40, seed=5)
        c = search_path(problem, "qpso", 20, 40, seed=6)
        assert a.nodes == b.nodes and a.convergence == b.convergence
        assert a.convergence != c.convergence

    def test_the_weights_are_what_the_search_minimizes(self):
        g = small_map()
        by_distance = search_path(PathProblem(g, 0, 5, CostWeights(0, 1, 0), corridor=10), "qpso", 20, 60, seed=1)
        assert by_distance.nodes == [0, 1, 5] and by_distance.cost == pytest.approx(3.0)

    def test_an_unknown_search_is_refused(self):
        with pytest.raises(ValueError, match="unknown"):
            search_path(PathProblem(small_map(), 0, 5, corridor=10), "annealing")

    def test_find_path_dispatches_to_the_exact_solver_and_the_searches(self):
        graph = generate_synthetic_graph(n_nodes=40, area_size_km=8.0, seed=5)
        (s, t), = random_pairs(graph, 1, seed=1)
        assert find_path(graph, s, t).algorithm == "dijkstra"
        assert find_path(graph, s, t, "qpso", n_particles=10, n_iterations=20, seed=1).algorithm == "qpso"
