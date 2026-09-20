"""The optimal Split decoder: the cheapest way to cut a visiting order into capacity-respecting routes."""

import math
import random

import pytest

from app.core.baselines.dijkstra_baseline import nearest_neighbor_order
from app.core.baselines.genetic_algorithm import GeneticAlgorithm
from app.core.local_search import improve_routes
from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot
from app.data.synthetic_graph_generator import generate_synthetic_graph


def make(n_customers, seed=500, capacity=100, vehicles=None, decoder="optimal", demand_range=(5, 25), utilization=0.85):
    graph = generate_synthetic_graph(n_nodes=2 * n_customers, seed=seed)
    rng = random.Random(seed)
    stops = list(range(1, n_customers + 1))
    demands = {c: rng.randint(*demand_range) for c in stops}
    if vehicles is None:
        vehicles = math.ceil(sum(demands.values()) / (utilization * capacity))
    request = RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=capacity, n_vehicles=vehicles, decoder=decoder)
    return graph, request, RoutingProblem(graph, request)


def brute_force(problem, order):
    """The cheapest partition of `order` into at most n_vehicles capacity-respecting pieces, by trying every cut set."""
    request, n = problem.request, len(order)
    best = math.inf
    for mask in range(1 << (n - 1)):
        cuts = [i + 1 for i in range(n - 1) if mask >> i & 1]
        pieces = [order[a:b] for a, b in zip([0, *cuts], [*cuts, n])]
        if len(pieces) > request.n_vehicles:
            continue
        if any(sum(request.demands[s] for s in piece) > request.vehicle_capacity for piece in pieces):
            continue
        cost = sum(problem.leg_time(0, piece[0]) + sum(problem.leg_time(a, b) for a, b in zip(piece, piece[1:])) + problem.leg_time(piece[-1], 0) for piece in pieces)
        best = min(best, cost)
    return best


# ---- correctness against exhaustive search -----------------------------------------------------------------


@pytest.mark.parametrize("vehicles,min_feasible", [(3, 5), (4, 15), (6, 30)])
def test_the_optimal_split_is_the_true_minimum_over_all_partitions(vehicles, min_feasible):
    checked = infeasible = 0
    for seed in range(600, 606):
        graph, request, problem = make(9, seed=seed, capacity=40, vehicles=vehicles, demand_range=(5, 20))
        rng = random.Random(seed)
        for _ in range(8):
            order = rng.sample(request.stops, len(request.stops))
            expected = brute_force(problem, order)
            found = problem._optimal_split(order, want_cuts=True)
            if expected == math.inf:
                assert found is None  # no partition fits the fleet
                infeasible += 1
                continue
            cost, cuts = found
            assert cost == pytest.approx(expected)
            routes = problem.split(order)
            assert sum(len(r) - 2 for r in routes) == 9 and len(routes) <= vehicles
            assert problem.evaluate_routes(routes).total_time_min == pytest.approx(expected)
            assert problem.evaluate_routes(routes).feasible
            checked += 1
    assert checked >= min_feasible  # feasible orders were compared with exhaustive search
    assert infeasible > 0 or vehicles > 3  # and, for a tight fleet, infeasible ones were correctly reported as None


def test_the_layered_search_for_a_binding_fleet_limit_is_exercised_and_exact(monkeypatch):
    calls = []
    original = RoutingProblem._optimal_split_limited

    def spy(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RoutingProblem, "_optimal_split_limited", spy)
    matched = 0
    for seed in range(700, 720):
        graph, request, problem = make(9, seed=seed, capacity=40, vehicles=3, demand_range=(6, 18))
        rng = random.Random(seed)
        for _ in range(6):
            order = rng.sample(request.stops, 9)
            expected = brute_force(problem, order)
            found = problem._optimal_split(order)
            assert (found is None) == (expected == math.inf)
            if found is not None:
                assert found[0] == pytest.approx(expected)
                matched += 1
    assert calls, "no order needed the fleet-limited search, so this test would not prove anything"
    assert matched > 10


# ---- what the decoder guarantees ------------------------------------------------------------------------------


def test_every_permutation_is_scored_at_its_best_partition_never_worse_than_greedy():
    graph, request, optimal = make(30, decoder="optimal")
    greedy = RoutingProblem(graph, RouteRequest(**{**request.__dict__, "decoder": "greedy"}))
    rng = random.Random(1)
    strictly_better = 0
    for _ in range(300):
        order = rng.sample(request.stops, 30)
        assert optimal.cost(order) <= greedy.cost(order) + 1e-9
        strictly_better += optimal.cost(order) < greedy.cost(order) - 1e-6
        routes = optimal.split(order)
        assert optimal.evaluate_routes(routes).feasible
        assert sorted(s for r in routes for s in r[1:-1]) == request.stops
    assert strictly_better > 250  # a greedy cut is almost never the best cut


@pytest.mark.parametrize("decoder", ["greedy", "optimal"])
@pytest.mark.parametrize("tight", [False, True])
def test_the_allocation_free_cost_always_agrees_with_the_routes_it_describes(decoder, tight):
    graph, request, problem = make(25, seed=520, decoder=decoder, utilization=1.3 if tight else 0.85)  # tight: not enough vehicles
    rng = random.Random(2)
    for _ in range(60):
        order = rng.sample(request.stops, 25)
        evaluation = problem.evaluate(order)
        assert problem.cost(order) == pytest.approx(evaluation.total_time_min + 1000.0 * evaluation.capacity_violation)
        if tight:
            assert not evaluation.feasible  # the fleet cannot hold the load, so an overload must be reported


def test_when_the_fleet_cannot_hold_the_load_it_falls_back_to_the_greedy_soft_penalty():
    graph, request, optimal = make(20, decoder="optimal", utilization=1.6)
    greedy = RoutingProblem(graph, RouteRequest(**{**request.__dict__, "decoder": "greedy"}))
    assert sum(request.demands.values()) > request.n_vehicles * request.vehicle_capacity
    order = list(request.stops)
    assert optimal.cost(order) == pytest.approx(greedy.cost(order))
    assert optimal.split(order) == greedy.split(order)
    assert not optimal.evaluate(order).feasible


def test_a_stop_that_cannot_fit_any_vehicle_is_left_to_the_greedy_rule():
    graph, request, _ = make(12, decoder="optimal", capacity=100)
    demands = dict(request.demands)
    demands[5] = 150  # larger than a whole vehicle
    request = RouteRequest(**{**request.__dict__, "demands": demands})
    optimal = RoutingProblem(graph, request)
    greedy = RoutingProblem(graph, RouteRequest(**{**request.__dict__, "decoder": "greedy"}))
    order = list(request.stops)
    assert optimal.cost(order) == pytest.approx(greedy.cost(order))
    assert optimal.split(order) == greedy.split(order)


def test_a_single_vehicle_or_no_capacity_is_not_affected_by_the_decoder():
    graph = generate_synthetic_graph(n_nodes=40, seed=300)
    for kwargs in (dict(), dict(n_vehicles=1, demands={i: 10 for i in range(1, 21)}, vehicle_capacity=1000)):
        a = RoutingProblem(graph, RouteRequest(depot=0, stops=list(range(1, 21)), decoder="optimal", **kwargs))
        b = RoutingProblem(graph, RouteRequest(depot=0, stops=list(range(1, 21)), decoder="greedy", **kwargs))
        order = list(range(20, 0, -1))
        assert a.cost(order) == b.cost(order) and a.split(order) == b.split(order)


def test_writing_improved_routes_back_as_a_permutation_never_makes_them_worse():
    # The reason the optimal split matters for the search: any route set is safe to store as one giant tour.
    graph, request, problem = make(40, decoder="optimal")
    start = problem.split(nearest_neighbor_order(problem))
    improved = improve_routes(problem, start)
    assert len(improved) <= request.n_vehicles

    def cost(routes):
        e = problem.evaluate_routes(routes)
        return e.total_time_min + 1000.0 * e.capacity_violation

    giant_tour = [s for route in improved for s in route[1:-1]]
    assert problem.cost(giant_tour) <= cost(improved) + 1e-9
    assert problem.cost(giant_tour) <= cost(start) + 1e-9


def test_an_unknown_decoder_is_rejected():
    graph = generate_synthetic_graph(n_nodes=20, seed=1)
    with pytest.raises(ValueError, match="decoder"):
        RoutingProblem(graph, RouteRequest(depot=0, stops=[1, 2, 3], decoder="cheapest"))


# ---- the algorithms just use it ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("make_algo", [
    lambda g, r: QPSO(g, r, n_particles=10, n_iterations=25, seed=3),
    lambda g, r: GeneticAlgorithm(g, r, population_size=10, n_generations=25, seed=3),
], ids=["qpso", "ga"])
def test_the_algorithms_work_unchanged_with_the_optimal_decoder(make_algo):
    graph, request, problem = make(30, decoder="optimal")
    result = make_algo(graph, request).run()
    routes = split_at_depot(result.best_route, 0)
    assert sorted(s for r in routes for s in r[1:-1]) == request.stops
    assert problem.evaluate_routes(routes).feasible
    order = [s for s in result.best_route if s != 0]
    assert problem.cost(order) == pytest.approx(result.best_cost)
    assert problem.evaluate(order).total_time_min == pytest.approx(result.best_cost)
