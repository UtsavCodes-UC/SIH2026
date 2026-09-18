import numpy as np

from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest
from app.data.synthetic_graph_generator import generate_synthetic_graph


def _build_qpso(weighted_mbest: bool, seed: int = 42) -> QPSO:
    graph = generate_synthetic_graph(n_nodes=20, seed=seed)
    request = RouteRequest(depot=0, stops=[3, 7, 11, 15, 2])
    return QPSO(graph, request, n_particles=10, n_iterations=20, weighted_mbest=weighted_mbest, seed=1)


def test_weighted_mbest_matches_plain_mean_when_disabled():
    qpso = _build_qpso(weighted_mbest=False)
    pbest = qpso.rng.random((10, qpso.n))
    pbest_fit = qpso._fitness_batch(pbest)

    mbest = qpso._compute_mbest(pbest, pbest_fit)

    assert np.allclose(mbest, pbest.mean(axis=0))


def test_weighted_mbest_biases_toward_better_particles():
    qpso = _build_qpso(weighted_mbest=True)

    # two particles: index 0 is much better (lower cost) than index 1
    pbest = np.array([[0.1, 0.9], [0.9, 0.1]])
    pbest_fit = np.array([1.0, 100.0])

    mbest = qpso._compute_mbest(pbest, pbest_fit)
    plain_mean = pbest.mean(axis=0)

    # weighted mbest should sit closer to the better particle (index 0) than the plain mean does
    assert np.linalg.norm(mbest - pbest[0]) < np.linalg.norm(plain_mean - pbest[0])


def test_qpso_with_weighted_mbest_returns_valid_route():
    graph = generate_synthetic_graph(n_nodes=20, seed=8)
    stops = [1, 4, 7, 10, 13]
    request = RouteRequest(depot=0, stops=stops)

    result = QPSO(graph, request, n_particles=15, n_iterations=40, weighted_mbest=True, seed=3).run()

    assert result.best_route[0] == request.depot
    assert result.best_route[-1] == request.depot
    assert sorted(result.best_route[1:-1]) == sorted(stops)
