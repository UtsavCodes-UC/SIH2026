import random

from app.core.local_search import polish_result, two_opt
from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph


def _tour_cost(order, leg):
    route = [0, *order, 0]
    return sum(leg(route[k], route[k + 1]) for k in range(len(route) - 1))


def test_two_opt_is_exact_for_asymmetric_costs():
    # Regression: the textbook 2-opt delta assumes leg(u, v) == leg(v, u). Our graphs are
    # directed with per-direction congestion, and the old formula returned a longer tour in
    # ~4% of random asymmetric cases (up to +46%). Random asymmetric instances must never
    # get worse, and the result must be a genuine local optimum (no single reversal helps).
    rng = random.Random(0)
    for _ in range(300):
        n_stops = rng.randint(3, 9)
        nodes = list(range(n_stops + 1))
        cost = {(u, v): rng.uniform(1, 10) for u in nodes for v in nodes if u != v}

        def leg(u, v):
            return cost[(u, v)]

        order = rng.sample(nodes[1:], n_stops)
        polished = two_opt(order, leg, depot=0)

        assert sorted(polished) == sorted(order)
        assert _tour_cost(polished, leg) <= _tour_cost(order, leg) + 1e-9

        route = [0, *polished, 0]
        for i in range(1, len(route) - 2):
            for j in range(i + 1, len(route) - 1):
                reversed_segment = route[:i] + route[i : j + 1][::-1] + route[j + 1 :]
                assert _tour_cost(reversed_segment[1:-1], leg) >= _tour_cost(polished, leg) - 1e-9


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
