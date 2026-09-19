"""Scaling to larger problems: moving stops between vehicles, warm start, and QPSO's size-aware jump."""

import math
import random

import pytest
from fastapi.testclient import TestClient

from app.core.baselines.classical_pso import ClassicalPSO
from app.core.baselines.dijkstra_baseline import nearest_neighbor
from app.core.baselines.genetic_algorithm import GeneticAlgorithm
from app.core.local_search import improve_routes, polish_result
from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot
from app.core.warm_start import heuristic_seed_orders
from app.data.synthetic_graph_generator import generate_synthetic_graph
from app.main import app
from app.services.graph_store import get_store

CAPACITY = 100
client = TestClient(app)
FAST = {"n_particles": 10, "n_iterations": 30}


def instance(n_customers: int, seed: int, utilization: float = 0.85):
    graph = generate_synthetic_graph(n_nodes=2 * n_customers, seed=seed)
    rng = random.Random(seed)
    demands = {c: rng.randint(5, 25) for c in range(1, n_customers + 1)}
    n_vehicles = math.ceil(sum(demands.values()) / (utilization * CAPACITY))
    request = RouteRequest(
        depot=0, stops=list(range(1, n_customers + 1)), demands=demands, vehicle_capacity=CAPACITY, n_vehicles=n_vehicles
    )
    return graph, request, RoutingProblem(graph, request)


def penalized(problem: RoutingProblem, routes) -> float:
    evaluation = problem.evaluate_routes(routes)
    return evaluation.total_time_min + 1000.0 * evaluation.capacity_violation


# ---- moving stops between vehicles -------------------------------------------------------------------


@pytest.mark.parametrize("n_customers,seed", [(20, 500), (30, 501), (50, 502), (40, 503)])
def test_improve_routes_only_ever_helps_and_keeps_every_stop_exactly_once(n_customers, seed):
    # Costs are directed and congested per direction. If any move's cost change were computed wrongly the
    # total would sometimes go UP, so "never worse" on random asymmetric instances is a real exactness test.
    graph, request, problem = instance(n_customers, seed)
    start = problem.split(heuristic_seed_orders(problem)[0])

    result = improve_routes(problem, start)

    assert sorted(s for route in result for s in route[1:-1]) == list(range(1, n_customers + 1))
    assert all(route[0] == route[-1] == 0 for route in result)
    assert problem.evaluate_routes(result).feasible
    assert penalized(problem, result) <= penalized(problem, start) + 1e-9
    assert len(result) <= len(start)  # vehicles are never added


def test_moving_stops_between_vehicles_finds_gains_that_2_opt_inside_routes_cannot():
    total_two_opt = total_full = 0.0
    for seed in range(500, 506):
        _, request, problem = instance(40, seed)
        raw = nearest_neighbor(*instance(40, seed)[:2])
        total_two_opt += polish_result(problem, raw).best_cost
        total_full += polish_result(problem, raw, inter_route=True).best_cost
    assert total_full < 0.95 * total_two_opt  # measured about 10-18% at 20-100 customers; asserting a safe margin


def test_an_overloaded_vehicle_is_relieved_when_the_others_have_room():
    graph, request, problem = instance(12, 500, utilization=0.5)
    stops = list(range(1, 13))
    overloaded = [[0, *stops, 0], [0, 0], [0, 0]]  # everything on one van, two idle ones (room for all of it)
    assert not problem.evaluate_routes(overloaded).feasible

    fixed = improve_routes(problem, overloaded)

    assert problem.evaluate_routes(fixed).feasible
    assert sorted(s for r in fixed for s in r[1:-1]) == stops


def test_when_the_fleet_is_too_tight_to_be_feasible_the_overload_still_shrinks():
    graph, request, problem = instance(12, 500, utilization=0.5)
    stops = list(range(1, 13))
    overloaded = [[0, *stops, 0], [0, 0]]  # total demand is close to the two vans' combined capacity
    before = problem.evaluate_routes(overloaded).capacity_violation

    fixed = improve_routes(problem, overloaded)

    assert problem.evaluate_routes(fixed).capacity_violation < before / 10
    assert sorted(s for r in fixed for s in r[1:-1]) == stops


def test_a_vehicle_emptied_by_the_search_is_dropped_and_none_is_added():
    graph, request, problem = instance(15, 504, utilization=0.3)  # lots of spare capacity: consolidating pays
    start = problem.split(heuristic_seed_orders(problem)[0])
    result = improve_routes(problem, start)
    assert all(len(route) > 2 for route in result)  # no empty [depot, depot] routes returned
    assert len(result) <= request.n_vehicles


def test_polish_by_default_still_leaves_every_vehicles_stops_alone():
    _, request, problem = instance(30, 500)
    raw = nearest_neighbor(*instance(30, 500)[:2])
    before = [set(r[1:-1]) for r in split_at_depot(raw.best_route, 0)]
    after = [set(r[1:-1]) for r in split_at_depot(polish_result(problem, raw).best_route, 0)]
    assert before == after


# ---- warm start ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("n_customers,seed,utilization", [(20, 500, 0.85), (50, 501, 0.85), (60, 502, 0.95)])
def test_warm_start_seeds_decode_back_to_the_routes_they_came_from(n_customers, seed, utilization):
    _, _, problem = instance(n_customers, seed, utilization)
    nearest, polished = heuristic_seed_orders(problem)

    assert sorted(nearest) == sorted(polished) == list(range(1, n_customers + 1))
    assert problem.cost(polished) <= problem.cost(nearest) + 1e-9
    # 2-opt reorders inside a route only, so the greedy split must cut at the same places
    assert [set(r[1:-1]) for r in problem.split(nearest)] == [set(r[1:-1]) for r in problem.split(polished)]
    assert problem.evaluate(nearest).feasible and problem.evaluate(polished).feasible


@pytest.mark.parametrize(
    "make",
    [
        lambda g, r, warm: QPSO(g, r, n_particles=10, n_iterations=30, warm_start=warm, seed=1),
        lambda g, r, warm: ClassicalPSO(g, r, n_particles=10, n_iterations=30, warm_start=warm, seed=1),
        lambda g, r, warm: GeneticAlgorithm(g, r, population_size=10, n_generations=30, warm_start=warm, seed=1),
    ],
    ids=["qpso", "pso", "ga"],
)
def test_a_warm_started_search_never_ends_worse_than_the_seed_it_was_given(make):
    graph, request, problem = instance(40, 500)
    seed_cost = min(problem.cost(order) for order in heuristic_seed_orders(problem))

    warm = make(graph, request, True).run()
    cold = make(graph, request, False).run()

    assert warm.best_cost <= seed_cost + 1e-9
    assert warm.best_cost < cold.best_cost  # from a tiny random start the head start decides the outcome
    assert warm.convergence_history[0] <= seed_cost + 1e-9  # the seed is in the swarm from iteration 0


def test_warm_start_off_leaves_every_search_exactly_as_it_was():
    graph, request, _ = instance(25, 500)
    a = QPSO(graph, request, n_particles=10, n_iterations=25, seed=3).run()
    b = QPSO(graph, request, n_particles=10, n_iterations=25, warm_start=False, seed=3).run()
    assert a.best_cost == b.best_cost and a.convergence_history == b.convergence_history


# ---- QPSO's jump shrinks with problem size -------------------------------------------------------------


@pytest.mark.parametrize("n_customers,expected", [(10, (1.0, 0.2)), (50, (1.0, 0.2)), (100, (0.5, 0.1)), (200, (0.25, 0.05))])
def test_the_default_jump_is_unchanged_up_to_50_stops_and_shrinks_in_proportion_beyond(n_customers, expected):
    graph = generate_synthetic_graph(n_nodes=2 * n_customers, seed=1)
    request = RouteRequest(depot=0, stops=list(range(1, n_customers + 1)))
    qpso = QPSO(graph, request, n_particles=5, n_iterations=5, seed=1)
    assert (qpso.beta_start, qpso.beta_end) == pytest.approx(expected)


def test_explicit_beta_values_are_always_respected():
    graph = generate_synthetic_graph(n_nodes=200, seed=1)
    request = RouteRequest(depot=0, stops=list(range(1, 101)))
    qpso = QPSO(graph, request, n_particles=5, n_iterations=5, beta_start=0.9, beta_end=0.3, seed=1)
    assert (qpso.beta_start, qpso.beta_end) == (0.9, 0.3)


def test_results_up_to_50_stops_are_bit_identical_to_the_old_fixed_schedule():
    graph, request, _ = instance(30, 500)
    auto = QPSO(graph, request, n_particles=10, n_iterations=30, seed=2).run()
    fixed = QPSO(graph, request, n_particles=10, n_iterations=30, beta_start=1.0, beta_end=0.2, seed=2).run()
    assert auto.best_cost == fixed.best_cost and auto.convergence_history == fixed.convergence_history


# ---- through the API ---------------------------------------------------------------------------------------


@pytest.fixture
def graph_id():
    get_store().clear()
    response = client.post("/api/graph/synthetic", json={"n_nodes": 80, "seed": 1, "area_size_km": 6})
    assert response.status_code == 200, response.text
    yield response.json()["summary"]["graph_id"]
    get_store().clear()


def test_optimize_starts_warm_by_default_and_says_so(graph_id):
    body = {"graph_id": graph_id, "n_stops": 25, "seed": 4, **FAST}

    default = client.post("/api/optimize", json=body).json()
    cold = client.post("/api/optimize", json={**body, "warm_start": False}).json()
    nearest = client.post("/api/optimize", json={**body, "algorithm": "nearest_neighbor"}).json()

    assert default["warm_start"] is True and cold["warm_start"] is False
    assert nearest["warm_start"] is False  # nothing to seed: it is the seed
    assert default["cost"] <= default["raw_cost"] + 1e-9  # the polish only ever helps
    # raw results: from a 10-particle random swarm the head start decides the outcome (after the polish a cold
    # start can land within a percent either way at this size; the head start matters from about 50 stops)
    assert default["raw_cost"] < cold["raw_cost"]


def test_a_warm_started_benchmark_never_loses_to_its_own_seed(graph_id):
    body = {"graph_id": graph_id, "n_stops": 25, "seed": 4, **FAST}

    warm = client.post("/api/benchmark", json=body).json()
    cold = client.post("/api/benchmark", json={**body, "warm_start": False}).json()

    assert warm["warm_start"] is True and cold["warm_start"] is False
    rows = {a["name"]: a for a in warm["algorithms"]}
    for name in ("classical_pso", "genetic_algorithm", "qpso"):
        assert rows[name]["raw_cost"] <= rows["nearest_neighbor"]["raw_cost"] + 1e-6, name
    assert {a["name"]: a["raw_cost"] for a in cold["algorithms"]}["qpso"] > rows["qpso"]["raw_cost"]
    # the benchmark polishes with the stronger local search too
    assert all(a["polished_cost"] is not None and a["polished_cost"] <= a["raw_cost"] + 1e-9 for a in warm["algorithms"])


# ---- the genetic algorithm's vectorized crossover ---------------------------------------------------------------


def _reference_order_crossover(parent_a, parent_b, i, j):
    """The original, slow formulation: kept here so the fast one is checked against it, gene by gene."""
    import numpy as np

    n = len(parent_a)
    child = np.full(n, -1, dtype=int)
    child[i : j + 1] = parent_a[i : j + 1]
    fill_values = [gene for gene in parent_b if gene not in child[i : j + 1]]
    fill_positions = [p for p in range(n) if child[p] == -1]
    for pos, value in zip(fill_positions, fill_values):
        child[pos] = value
    return child


def test_the_vectorized_crossover_gives_exactly_the_children_of_the_original():
    import numpy as np

    class FixedCut:
        """Stands in for the GA's random generator: it always picks the cut points it was given."""

        def __init__(self, i, j):
            self.cut = np.array([i, j])

        def choice(self, n, size, replace):
            return self.cut

    graph, request, _ = instance(30, 500)
    ga = GeneticAlgorithm(graph, request, population_size=10, n_generations=1, seed=1)
    rng = np.random.default_rng(0)
    for _ in range(300):
        a, b = rng.permutation(ga.n), rng.permutation(ga.n)
        i, j = sorted(rng.choice(ga.n, size=2, replace=False))
        ga.rng = FixedCut(i, j)
        assert list(ga._order_crossover(a, b)) == list(_reference_order_crossover(a, b, i, j))
