"""
Regression guard for QPSO's advantage over classical PSO.

Asserts on the RAW metaheuristic output (no local search): same encoding,
same fitness, same 40-particle / 800-iteration budget, so this is a
like-for-like algorithm comparison. On raw cost QPSO wins ~90% of instances
by ~17-27% (30 instances/size, three PSO parameter sets -- see
docs/BENCHMARKS.md Finding 7 and scripts/compare_qpso_vs_pso.py). This test
uses a small fixed sample so it stays fast; the margins below are loose
enough to tolerate one unlucky instance but not a real regression.

It deliberately does NOT assert on the 2-opt-polished cost: a uniform polish
shrinks the gap to ~1-2% with p-values that are often not significant, so it
would be a flaky guard rather than a meaningful one.
"""

from app.core.benchmark import run_qpso_vs_pso


def test_qpso_beats_classical_pso_on_raw_cost_across_sizes():
    for n_stops in (20, 30):
        report = run_qpso_vs_pso(n_stops, instance_seeds=range(300, 304))
        raw = report.raw

        assert raw.wins >= 3, (
            f"{n_stops} stops: QPSO won only {raw.wins}/4 instances on raw cost "
            f"(mean improvement {raw.mean_improvement_pct:+.1f}%). "
            "See scripts/compare_qpso_vs_pso.py and scripts/tune_qpso.py to investigate."
        )
        assert raw.mean_improvement_pct > 5.0, (
            f"{n_stops} stops: QPSO's mean raw improvement over PSO fell to {raw.mean_improvement_pct:+.1f}% "
            "(expected ~17-27%)."
        )
