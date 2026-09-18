import numpy as np

from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest
from app.data.synthetic_graph_generator import generate_synthetic_graph


def _build_qpso(adaptive_beta: bool, n_particles: int = 10, seed: int = 42) -> QPSO:
    graph = generate_synthetic_graph(n_nodes=20, seed=seed)
    request = RouteRequest(depot=0, stops=[3, 7, 11, 15, 2])
    return QPSO(graph, request, n_particles=n_particles, adaptive_beta=adaptive_beta, seed=1)


def test_beta_is_uniform_when_disabled():
    qpso = _build_qpso(adaptive_beta=False)
    pbest_fit = np.array([5.0, 1.0, 3.0, 9.0, 2.0, 7.0, 4.0, 8.0, 6.0, 0.5])

    beta = qpso._compute_beta(progress=0.5, pbest_fit=pbest_fit)

    assert beta.shape == (10,)
    assert np.allclose(beta, beta[0])


def test_adaptive_beta_gives_worse_particles_larger_beta():
    qpso = _build_qpso(adaptive_beta=True)
    pbest_fit = np.array([5.0, 1.0, 3.0, 9.0, 2.0, 7.0, 4.0, 8.0, 6.0, 0.5])

    beta = qpso._compute_beta(progress=0.5, pbest_fit=pbest_fit)

    best_idx = int(np.argmin(pbest_fit))
    worst_idx = int(np.argmax(pbest_fit))
    assert beta[worst_idx] > beta[best_idx]


def test_adaptive_beta_average_matches_scheduled_beta():
    qpso = _build_qpso(adaptive_beta=True, n_particles=20)
    pbest_fit = np.arange(20, dtype=float)  # evenly spread ranks

    beta_iter = qpso.beta_start - (qpso.beta_start - qpso.beta_end) * 0.5
    beta = qpso._compute_beta(progress=0.5, pbest_fit=pbest_fit)

    assert abs(beta.mean() - beta_iter) < 1e-9


def test_qpso_with_adaptive_beta_returns_valid_route():
    graph = generate_synthetic_graph(n_nodes=25, seed=6)
    stops = [1, 4, 7, 10, 13, 16]
    request = RouteRequest(depot=0, stops=stops)

    result = QPSO(graph, request, n_particles=15, n_iterations=60, adaptive_beta=True, seed=2).run()

    assert result.best_route[0] == request.depot
    assert result.best_route[-1] == request.depot
    assert sorted(result.best_route[1:-1]) == sorted(stops)
