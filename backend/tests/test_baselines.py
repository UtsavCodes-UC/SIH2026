import itertools

from app.core.baselines.classical_pso import ClassicalPSO
from app.core.baselines.dijkstra_baseline import nearest_neighbor
from app.core.baselines.exact_held_karp import held_karp
from app.core.baselines.genetic_algorithm import GeneticAlgorithm
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph


def _build_problem(seed: int = 42):
    graph = generate_synthetic_graph(n_nodes=20, seed=seed)
    stops = [3, 7, 11, 15, 2]
    request = RouteRequest(depot=0, stops=stops)
    return graph, request, stops


def _assert_valid_route(result, depot, stops):
    assert result.best_route[0] == depot
    assert result.best_route[-1] == depot
    assert sorted(result.best_route[1:-1]) == sorted(stops)
    assert result.best_cost > 0


def test_nearest_neighbor_returns_valid_route():
    graph, request, stops = _build_problem()
    result = nearest_neighbor(graph, request)
    _assert_valid_route(result, request.depot, stops)


def test_classical_pso_returns_valid_route_and_converges():
    graph, request, stops = _build_problem()
    result = ClassicalPSO(graph, request, n_particles=20, n_iterations=40, seed=1).run()

    _assert_valid_route(result, request.depot, stops)
    history = result.convergence_history
    assert all(later <= earlier for earlier, later in zip(history, history[1:]))


def test_genetic_algorithm_returns_valid_route_and_converges():
    graph, request, stops = _build_problem()
    result = GeneticAlgorithm(graph, request, population_size=20, n_generations=40, seed=1).run()

    _assert_valid_route(result, request.depot, stops)
    history = result.convergence_history
    assert all(later <= earlier for earlier, later in zip(history, history[1:]))


def test_held_karp_matches_brute_force_optimum():
    graph, request, stops = _build_problem()

    problem = RoutingProblem(graph, request)
    brute_force_best = min(problem.cost(list(p)) for p in itertools.permutations(stops))

    result = held_karp(graph, request)

    _assert_valid_route(result, request.depot, stops)
    assert abs(result.best_cost - brute_force_best) < 1e-6


def test_held_karp_rejects_too_many_stops():
    graph = generate_synthetic_graph(n_nodes=25, seed=1)
    request = RouteRequest(depot=0, stops=list(range(1, 20)))

    try:
        held_karp(graph, request)
        assert False, "expected ValueError for too many stops"
    except ValueError:
        pass


def test_exact_is_at_least_as_good_as_every_heuristic():
    graph, request, stops = _build_problem()

    exact = held_karp(graph, request)
    nn = nearest_neighbor(graph, request)
    pso = ClassicalPSO(graph, request, n_particles=20, n_iterations=60, seed=1).run()
    ga = GeneticAlgorithm(graph, request, population_size=20, n_generations=60, seed=1).run()

    assert exact.best_cost <= nn.best_cost + 1e-6
    assert exact.best_cost <= pso.best_cost + 1e-6
    assert exact.best_cost <= ga.best_cost + 1e-6
