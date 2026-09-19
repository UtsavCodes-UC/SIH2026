import math
import random

import pytest

from app.core.baselines.classical_pso import ClassicalPSO
from app.core.baselines.dijkstra_baseline import nearest_neighbor
from app.core.baselines.exact_held_karp import held_karp
from app.core.baselines.genetic_algorithm import GeneticAlgorithm
from app.core.benchmark import BenchmarkConfig, run_benchmark
from app.core.graph_model import TrafficGraph
from app.core.local_search import polish_result
from app.core.qpso import QPSO
from app.core.vrp_formulation import (
    RouteRequest,
    RoutingProblem,
    UnreachableStopError,
    split_at_depot,
)
from app.data.synthetic_graph_generator import generate_synthetic_graph

CAPACITY = 100


def build(n_stops=12, utilization=0.85, seed=3):
    """A feasible multi-vehicle instance: fleet sized so total demand fits within `utilization` of capacity."""
    graph = generate_synthetic_graph(n_nodes=n_stops * 3, seed=seed)
    rng = random.Random(seed)
    stops = list(range(1, n_stops + 1))
    demands = {s: rng.randint(5, 25) for s in stops}
    n_vehicles = math.ceil(sum(demands.values()) / (utilization * CAPACITY))
    request = RouteRequest(
        depot=0, stops=stops, demands=demands, vehicle_capacity=CAPACITY, n_vehicles=n_vehicles
    )
    return graph, request


def reference_cost(problem, order, penalty=1000.0):
    """Independent, deliberately naive re-implementation of the split + scoring."""
    req = problem.request
    routes, current, load = [], [], 0
    for stop in order:
        d = req.demands[stop]
        if current and load + d > req.vehicle_capacity and len(routes) < req.n_vehicles - 1:
            routes.append(current)
            current, load = [], 0
        current.append(stop)
        load += d
    routes.append(current)
    time_total, violation = 0.0, 0.0
    for r in routes:
        path = [req.depot, *r, req.depot]
        time_total += sum(problem.leg_time(path[i], path[i + 1]) for i in range(len(path) - 1))
        violation += max(0, sum(req.demands[s] for s in r) - req.vehicle_capacity)
    return time_total + penalty * violation


def test_split_visits_every_stop_once_within_the_fleet_size():
    graph, request = build()
    problem = RoutingProblem(graph, request)
    rng = random.Random(0)
    for _ in range(200):
        order = rng.sample(request.stops, len(request.stops))
        routes = problem.split(order)

        assert len(routes) <= request.n_vehicles
        assert all(r[0] == request.depot and r[-1] == request.depot and len(r) > 2 for r in routes)
        assert sorted(s for r in routes for s in r if s != request.depot) == sorted(request.stops)
        for load in problem.route_loads(routes)[:-1]:  # every vehicle but the last is within capacity
            assert load <= CAPACITY


def test_fast_cost_matches_evaluate_and_an_independent_reference():
    for n_vehicles_override in (None, 1):
        graph, request = build()
        if n_vehicles_override:
            request = RouteRequest(**{**request.__dict__, "n_vehicles": n_vehicles_override})
        problem = RoutingProblem(graph, request)
        rng = random.Random(1)
        for _ in range(200):
            order = rng.sample(request.stops, len(request.stops))
            evaluation = problem.evaluate(order)
            expected = evaluation.total_time_min + 1000.0 * evaluation.capacity_violation

            assert problem.cost(order) == pytest.approx(expected, abs=1e-9)
            assert problem.cost(order) == pytest.approx(reference_cost(problem, order), abs=1e-9)


def test_single_vehicle_flat_route_is_the_plain_tour():
    graph, request = build()
    single = RouteRequest(depot=0, stops=request.stops)
    problem = RoutingProblem(graph, single)
    order = list(reversed(request.stops))

    evaluation = problem.evaluate(order)

    assert evaluation.route == [0, *order, 0]
    assert len(evaluation.routes) == 1


def test_split_at_depot_inverts_the_flat_route():
    graph, request = build()
    problem = RoutingProblem(graph, request)
    order = random.Random(2).sample(request.stops, len(request.stops))
    routes = problem.split(order)

    flat = problem.evaluate(order).route

    assert split_at_depot(flat, request.depot) == routes
    assert flat[0] == flat[-1] == request.depot
    assert len(routes) > 1  # the fixture really does need several vehicles


def test_multi_vehicle_request_needs_demands_and_capacity():
    graph, _ = build()
    with pytest.raises(ValueError):
        RoutingProblem(graph, RouteRequest(depot=0, stops=[1, 2, 3], n_vehicles=2))


def test_depot_cannot_be_a_stop():
    graph, _ = build()
    with pytest.raises(ValueError):
        RoutingProblem(graph, RouteRequest(depot=0, stops=[0, 1, 2]))


def test_unreachable_stop_raises_a_clear_error():
    g = TrafficGraph()
    g.add_edge("depot", "a", 1, 1)
    g.add_edge("a", "depot", 1, 1)
    g.add_edge("a", "sink", 1, 1)  # "sink" can be entered but never left
    with pytest.raises(UnreachableStopError):
        RoutingProblem(g, RouteRequest(depot="depot", stops=["a", "sink"]))


def test_nearest_neighbor_is_feasible_and_decodes_to_its_own_routes():
    graph, request = build()
    result = nearest_neighbor(graph, request)
    problem = RoutingProblem(graph, request)
    routes = split_at_depot(result.best_route, request.depot)

    assert sorted(s for r in routes for s in r if s != request.depot) == sorted(request.stops)
    assert len(routes) <= request.n_vehicles
    assert problem.evaluate_routes(routes).feasible
    assert result.best_cost == pytest.approx(problem.evaluate_routes(routes).total_time_min)


def test_metaheuristics_return_feasible_multi_vehicle_solutions():
    graph, request = build(n_stops=10)
    problem = RoutingProblem(graph, request)
    results = [
        QPSO(graph, request, n_particles=20, n_iterations=60, seed=1).run(),
        ClassicalPSO(graph, request, n_particles=20, n_iterations=60, seed=1).run(),
        GeneticAlgorithm(graph, request, population_size=20, n_generations=60, seed=1).run(),
    ]
    for result in results:
        routes = split_at_depot(result.best_route, request.depot)
        assert sorted(s for r in routes for s in r if s != request.depot) == sorted(request.stops)
        assert len(routes) <= request.n_vehicles
        assert problem.evaluate_routes(routes).total_time_min + 1000 * problem.evaluate_routes(routes).capacity_violation == pytest.approx(result.best_cost)


def test_polish_improves_or_matches_and_keeps_every_vehicles_stops():
    graph, request = build()
    problem = RoutingProblem(graph, request)
    raw = QPSO(graph, request, n_particles=15, n_iterations=25, seed=4).run()

    polished = polish_result(problem, raw)

    assert polished.best_cost <= raw.best_cost + 1e-6
    before = [set(r[1:-1]) for r in split_at_depot(raw.best_route, request.depot)]
    after = [set(r[1:-1]) for r in split_at_depot(polished.best_route, request.depot)]
    assert before == after  # per-route 2-opt never moves a stop to another vehicle


def test_memetic_refinement_is_rejected_for_multi_vehicle():
    graph, request = build()
    with pytest.raises(ValueError):
        QPSO(graph, request, memetic_interval=10)
    with pytest.raises(ValueError):
        ClassicalPSO(graph, request, memetic_interval=10)


def test_exact_solver_rejects_multi_vehicle_and_benchmark_skips_it():
    graph, request = build(n_stops=6)
    with pytest.raises(ValueError):
        held_karp(graph, request)

    report = run_benchmark(
        graph, request, BenchmarkConfig(n_particles=10, n_iterations=20, ga_population_size=10, ga_generations=20, seed=1)
    )
    assert report.exact_cost is None
    assert "held_karp_exact" not in {a.name for a in report.algorithms}
