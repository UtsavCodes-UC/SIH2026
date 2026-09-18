import numpy as np

from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest
from app.data.synthetic_graph_generator import generate_synthetic_graph


def test_reinject_diversity_resets_the_worst_fraction():
    graph = generate_synthetic_graph(n_nodes=20, seed=1)
    request = RouteRequest(depot=0, stops=[2, 5, 8, 11])
    qpso = QPSO(graph, request, n_particles=10, reinjection_fraction=0.3, seed=1)

    positions = qpso.rng.random((10, qpso.n))
    pbest = positions.copy()
    pbest_fit = qpso._fitness_batch(pbest)
    worst_before = np.argsort(pbest_fit)[-3:]

    new_positions, new_pbest, new_pbest_fit = qpso._reinject_diversity(
        positions.copy(), pbest.copy(), pbest_fit.copy()
    )

    assert not np.allclose(new_pbest[worst_before], pbest[worst_before])
    # the best 7 particles should be untouched
    best_before = np.argsort(pbest_fit)[:7]
    assert np.allclose(new_pbest[best_before], pbest[best_before])


def test_qpso_with_stagnation_injection_returns_valid_route():
    graph = generate_synthetic_graph(n_nodes=25, seed=6)
    stops = [1, 4, 7, 10, 13, 16]
    request = RouteRequest(depot=0, stops=stops)

    result = QPSO(
        graph, request, n_particles=15, n_iterations=100, stagnation_limit=20, seed=2
    ).run()

    assert result.best_route[0] == request.depot
    assert result.best_route[-1] == request.depot
    assert sorted(result.best_route[1:-1]) == sorted(stops)


def test_qpso_stagnation_off_still_works():
    graph = generate_synthetic_graph(n_nodes=20, seed=4)
    stops = [1, 3, 5, 7]
    request = RouteRequest(depot=0, stops=stops)

    result = QPSO(graph, request, n_particles=10, n_iterations=30, stagnation_limit=None, seed=1).run()

    assert sorted(result.best_route[1:-1]) == sorted(stops)
