from app.core.local_search import polish_result, two_opt
from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph


def test_two_opt_never_makes_a_route_worse():
    graph = generate_synthetic_graph(n_nodes=20, seed=5)
    stops = [2, 5, 9, 13, 17]
    request = RouteRequest(depot=0, stops=stops)
    problem = RoutingProblem(graph, request)

    # a deliberately bad, unoptimized order
    bad_order = list(stops)
    before = problem.cost(bad_order)

    polished_order = two_opt(bad_order, problem.leg_time, depot=0)
    after = problem.cost(polished_order)

    assert sorted(polished_order) == sorted(bad_order)
    assert after <= before


def test_polish_result_improves_or_matches_qpso_output():
    graph = generate_synthetic_graph(n_nodes=25, seed=11)
    stops = [1, 4, 8, 12, 16, 20]
    request = RouteRequest(depot=0, stops=stops)
    problem = RoutingProblem(graph, request)

    result = QPSO(graph, request, n_particles=15, n_iterations=25, seed=3).run()
    polished = polish_result(problem, result)

    assert polished.best_cost <= result.best_cost + 1e-6
    assert sorted(polished.best_route[1:-1]) == sorted(stops)
    assert polished.convergence_history[-1] == polished.best_cost
