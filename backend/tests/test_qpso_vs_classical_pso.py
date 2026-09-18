"""
Regression guard for the Day-1 tuning pass (see scripts/tune_qpso.py):
with the tuned defaults (particles=40, iterations=800, beta=(1.0, 0.2)) and
a 2-opt polish applied to both, QPSO should beat classical PSO on average
across a range of instance sizes. This was validated with 30 instances per
size in scripts/tune_qpso.py output; this test uses a smaller fixed sample
so it stays fast, with a tolerance margin against single-run noise.
"""

from app.core.baselines.classical_pso import ClassicalPSO
from app.core.local_search import polish_result
from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph


def test_qpso_beats_classical_pso_on_average_across_sizes():
    instance_specs = [(20, 300), (20, 301), (30, 300), (30, 301)]

    qpso_costs, pso_costs = [], []
    for n_stops, seed in instance_specs:
        graph = generate_synthetic_graph(n_nodes=n_stops * 2, seed=seed)
        stops = list(range(1, n_stops + 1))
        request = RouteRequest(depot=0, stops=stops)
        problem = RoutingProblem(graph, request)

        qpso_result = polish_result(problem, QPSO(graph, request, seed=1).run())
        pso_result = polish_result(problem, ClassicalPSO(graph, request, seed=1).run())

        qpso_costs.append(qpso_result.best_cost)
        pso_costs.append(pso_result.best_cost)

    avg_qpso = sum(qpso_costs) / len(qpso_costs)
    avg_pso = sum(pso_costs) / len(pso_costs)

    assert avg_qpso <= avg_pso, (
        f"QPSO regressed against classical PSO: avg cost {avg_qpso:.2f} vs {avg_pso:.2f}. "
        "See scripts/tune_qpso.py to re-tune if this starts failing after an algorithm change."
    )
