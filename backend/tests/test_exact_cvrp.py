"""The exact solver used to measure the heuristics: it must agree with exhaustive search before any gap to it means anything."""

import functools
import itertools
import math
import random

import pytest

from app.core.baselines.exact_cvrp import exact_solve
from app.core.baselines.exact_held_karp import held_karp
from app.core.cost_model import CostWeights
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph
from app.services.solver import solve


def make(n_stops, vehicles, capacity, seed=11, demand_range=(5, 25), weights=None):
    graph = generate_synthetic_graph(n_nodes=max(30, 2 * n_stops), seed=seed)
    rng = random.Random(seed)
    stops = list(range(1, n_stops + 1))
    demands = {s: rng.randint(*demand_range) for s in stops}
    request = RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=capacity, n_vehicles=vehicles, cost_weights=weights)
    return graph, request, RoutingProblem(graph, request)


def exhaustive(problem, penalty=1000.0):
    """Every assignment of stops to vehicles, and for each vehicle every visiting order: the cheapest total."""
    request, stops = problem.request, request_stops(problem)
    leg, depot = problem.leg_time, request.depot

    @functools.lru_cache(maxsize=None)
    def tour(group):
        if not group:
            return 0.0
        return min(
            leg(depot, order[0]) + sum(leg(a, b) for a, b in zip(order, order[1:])) + leg(order[-1], depot)
            for order in itertools.permutations(group)
        )

    best = math.inf
    for assignment in itertools.product(range(request.n_vehicles), repeat=len(stops)):
        groups = [[s for s, v in zip(stops, assignment) if v == k] for k in range(request.n_vehicles)]
        overload = sum(max(0.0, sum(request.demands[s] for s in g) - request.vehicle_capacity) for g in groups)
        best = min(best, sum(tour(tuple(g)) for g in groups) + penalty * overload)
    return best


def request_stops(problem):
    return list(problem.request.stops)


@pytest.mark.parametrize("vehicles,capacity", [(1, 1000), (2, 60), (3, 45), (3, 30), (2, 25)])  # the last two cannot avoid overload
def test_matches_exhaustive_search(vehicles, capacity):
    _, _, problem = make(6, vehicles, capacity)

    assert exact_solve(problem).cost == pytest.approx(exhaustive(problem), abs=1e-9)


@pytest.mark.parametrize("vehicles,capacity", [(3, 45), (3, 30), (2, 60)])
def test_matches_exhaustive_search_at_eight_stops(vehicles, capacity):
    _, _, problem = make(8, vehicles, capacity, seed=31)

    assert exact_solve(problem).cost == pytest.approx(exhaustive(problem), abs=1e-9)


def test_overload_is_priced_when_it_cannot_be_avoided():
    _, request, problem = make(6, 2, 25)  # about 90 units of demand for 50 units of capacity
    solution = exact_solve(problem)

    evaluation = problem.evaluate_routes(solution.routes)
    assert not evaluation.feasible and evaluation.capacity_violation > 0
    assert solution.cost == pytest.approx(problem.penalized_cost(evaluation))


@pytest.mark.parametrize("vehicles,capacity", [(1, 1000), (2, 70), (3, 45)])
def test_routes_reproduce_the_reported_cost_and_serve_every_stop_once(vehicles, capacity):
    _, request, problem = make(9, vehicles, capacity)
    solution = exact_solve(problem)

    assert len(solution.routes) <= vehicles
    assert all(route[0] == request.depot == route[-1] for route in solution.routes)
    assert sorted(s for route in solution.routes for s in route[1:-1]) == sorted(request.stops)
    assert solution.cost == pytest.approx(problem.penalized_cost(problem.evaluate_routes(solution.routes)), abs=1e-9)


def test_one_vehicle_is_held_karp():
    graph, request, problem = make(8, 1, 1000)
    single = RouteRequest(depot=0, stops=request.stops, n_vehicles=1)  # no demands: a plain tour

    assert exact_solve(RoutingProblem(graph, single)).cost == pytest.approx(held_karp(graph, single).best_cost, abs=1e-9)


def test_blended_cost_weights_are_respected():
    _, request, problem = make(7, 2, 60, weights=CostWeights(0.4, 0.3, 0.3))
    solution = exact_solve(problem)

    assert solution.cost == pytest.approx(exhaustive(problem), abs=1e-9)
    assert solution.cost == pytest.approx(problem.penalized_cost(problem.evaluate_routes(solution.routes)), abs=1e-9)


def test_no_heuristic_ever_beats_the_exact_optimum():
    graph, request, problem = make(10, 3, 100, seed=21)
    optimum = exact_solve(problem).cost

    for algorithm, kwargs in [
        ("qpso", dict(n_particles=20, n_iterations=100, polish=True, warm_start=True)),
        ("pso", dict(n_particles=20, n_iterations=100, polish=True, warm_start=True)),
        ("ga", dict(n_particles=20, n_iterations=60, polish=True, warm_start=True)),
        ("nearest_neighbor", dict(n_particles=1, n_iterations=1, polish=True)),
        ("route_search", dict(n_particles=1, n_iterations=1, polish=False, time_limit_sec=1.0)),
    ]:
        solution = solve(graph, request, algorithm, seed=1, **kwargs)
        assert problem.penalized_cost(problem.evaluate_routes(_routes(solution))) >= optimum - 1e-6, algorithm


def _routes(solution):
    from app.core.vrp_formulation import split_at_depot

    return split_at_depot(solution.final.best_route, solution.problem.request.depot)


def test_refuses_what_it_cannot_do():
    graph, request, problem = make(6, 2, 60)
    with pytest.raises(ValueError, match="exponential"):
        exact_solve(RoutingProblem(*_big()))

    windowed = RouteRequest(depot=0, stops=request.stops, demands=request.demands, vehicle_capacity=60, n_vehicles=2, time_windows={1: _window()})
    with pytest.raises(ValueError, match="time windows"):
        exact_solve(RoutingProblem(graph, windowed))


def _window():
    from app.core.time_windows import TimeWindow

    return TimeWindow(0.0, 30.0)


def _big():
    graph = generate_synthetic_graph(n_nodes=60, seed=3)
    stops = list(range(1, 17))
    return graph, RouteRequest(depot=0, stops=stops, demands={s: 10 for s in stops}, vehicle_capacity=100, n_vehicles=3)
