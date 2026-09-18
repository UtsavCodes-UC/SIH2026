from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest
from app.data.synthetic_graph_generator import generate_synthetic_graph


def _build_problem(seed: int = 42):
    graph = generate_synthetic_graph(n_nodes=20, seed=seed)
    stops = [3, 7, 11, 15, 2]
    request = RouteRequest(depot=0, stops=stops)
    return graph, request, stops


def test_qpso_returns_a_valid_route_visiting_every_stop_once():
    graph, request, stops = _build_problem()
    qpso = QPSO(graph, request, n_particles=20, n_iterations=40, seed=1)

    result = qpso.run()

    assert result.best_route[0] == request.depot
    assert result.best_route[-1] == request.depot
    assert sorted(result.best_route[1:-1]) == sorted(stops)
    assert result.best_cost > 0


def test_qpso_convergence_history_never_gets_worse():
    graph, request, _ = _build_problem()
    qpso = QPSO(graph, request, n_particles=20, n_iterations=40, seed=1)

    result = qpso.run()

    history = result.convergence_history
    assert all(later <= earlier for earlier, later in zip(history, history[1:]))
    assert history[-1] <= history[0]


def test_capacity_violation_adds_a_penalty_to_the_cost():
    # A single-vehicle full tour visits every stop regardless of order, so total
    # demand (and thus feasibility) is fixed by the request, not the ordering --
    # this checks RoutingProblem.cost() applies the penalty, not that QPSO can "solve" it.
    graph, _, stops = _build_problem()
    demands = {s: 40 for s in stops}  # total demand 200

    feasible_request = RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=300)
    infeasible_request = RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=100)

    from app.core.vrp_formulation import RoutingProblem

    feasible_eval = RoutingProblem(graph, feasible_request).evaluate(stops)
    infeasible_eval = RoutingProblem(graph, infeasible_request).evaluate(stops)

    assert feasible_eval.feasible
    assert not infeasible_eval.feasible
    assert infeasible_eval.capacity_violation == 100
