import numpy as np

from app.core.local_search import encode_order, refine_positions_with_two_opt
from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph


def test_encode_order_roundtrips_through_argsort():
    stops = [10, 20, 30, 40, 50]
    order = [40, 10, 50, 20, 30]

    position = encode_order(order, stops)
    decoded = [stops[i] for i in np.argsort(position)]

    assert decoded == order


def test_refine_positions_never_increases_cost():
    graph = generate_synthetic_graph(n_nodes=30, seed=9)
    stops = [2, 5, 9, 13, 17, 21]
    request = RouteRequest(depot=0, stops=stops)
    problem = RoutingProblem(graph, request)

    rng = np.random.default_rng(1)
    positions = rng.random((10, len(stops)))
    original_costs = np.array(
        [problem.cost([stops[i] for i in np.argsort(p)]) for p in positions]
    )

    _, refined_costs = refine_positions_with_two_opt(positions, stops, problem)

    assert np.all(refined_costs <= original_costs + 1e-6)


def test_qpso_with_memetic_returns_valid_route():
    graph = generate_synthetic_graph(n_nodes=30, seed=12)
    stops = [1, 4, 7, 10, 13, 16, 19]
    request = RouteRequest(depot=0, stops=stops)

    result = QPSO(graph, request, n_particles=15, n_iterations=60, memetic_interval=20, seed=2).run()

    assert result.best_route[0] == request.depot
    assert result.best_route[-1] == request.depot
    assert sorted(result.best_route[1:-1]) == sorted(stops)


def test_qpso_memetic_off_still_works():
    graph = generate_synthetic_graph(n_nodes=20, seed=4)
    stops = [1, 3, 5, 7]
    request = RouteRequest(depot=0, stops=stops)

    result = QPSO(graph, request, n_particles=10, n_iterations=30, memetic_interval=None, seed=1).run()

    assert sorted(result.best_route[1:-1]) == sorted(stops)
