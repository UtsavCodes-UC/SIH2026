import csv

import pytest

from app.core.benchmark import (
    BenchmarkConfig,
    iterations_to_reach,
    run_benchmark,
    run_qpso_vs_pso,
    run_scalability_sweep,
    sign_test_p_value,
)
from app.core.vrp_formulation import RouteRequest
from app.data.synthetic_graph_generator import generate_synthetic_graph


def test_run_benchmark_includes_exact_and_computes_gaps():
    graph = generate_synthetic_graph(n_nodes=20, seed=42)
    request = RouteRequest(depot=0, stops=[3, 7, 11, 15, 2])
    config = BenchmarkConfig(n_particles=20, n_iterations=40, ga_population_size=20, ga_generations=40, seed=1)

    report = run_benchmark(graph, request, config)

    names = {algo.name for algo in report.algorithms}
    assert names == {"nearest_neighbor", "classical_pso", "genetic_algorithm", "qpso", "held_karp_exact"}
    assert report.exact_cost is not None

    exact = next(a for a in report.algorithms if a.name == "held_karp_exact")
    assert exact.raw_gap_pct == 0.0
    assert exact.polished_gap_pct is None  # the exact solver is never polished

    for algo in report.algorithms:
        assert algo.raw_gap_pct >= -1e-6  # nothing should beat the exact optimum
        if algo.polished:
            assert algo.polished_gap_pct >= -1e-6
            assert algo.result.best_cost <= algo.raw_cost + 1e-6  # 2-opt never makes a route worse


def test_run_benchmark_skips_exact_when_too_many_stops():
    graph = generate_synthetic_graph(n_nodes=30, seed=1)
    request = RouteRequest(depot=0, stops=list(range(1, 20)))
    config = BenchmarkConfig(n_particles=10, n_iterations=10, ga_population_size=10, ga_generations=10, seed=1)

    report = run_benchmark(graph, request, config)

    names = {algo.name for algo in report.algorithms}
    assert "held_karp_exact" not in names
    assert report.exact_cost is None
    assert all(algo.raw_gap_pct is None and algo.polished_gap_pct is None for algo in report.algorithms)


def test_run_benchmark_without_polish_reports_raw_only():
    graph = generate_synthetic_graph(n_nodes=15, seed=1)
    request = RouteRequest(depot=0, stops=[1, 2, 3, 4])
    config = BenchmarkConfig(n_particles=10, n_iterations=10, seed=1, polish_with_two_opt=False)

    report = run_benchmark(graph, request, config)

    assert all(not algo.polished for algo in report.algorithms)
    assert all(algo.polished_gap_pct is None for algo in report.algorithms)


def test_summary_table_renders_without_error():
    graph = generate_synthetic_graph(n_nodes=15, seed=1)
    request = RouteRequest(depot=0, stops=[1, 2, 3])
    report = run_benchmark(graph, request, BenchmarkConfig(n_particles=10, n_iterations=10, seed=1))

    table = report.summary_table()
    assert "qpso" in table
    assert "held_karp_exact" in table
    assert "raw gap %" in table
    assert "+2-opt" in table


def test_scalability_sweep_runs_across_sizes():
    reports = run_scalability_sweep(
        node_counts=[10, 15],
        n_stops_fraction=0.3,
        config=BenchmarkConfig(n_particles=10, n_iterations=10, ga_population_size=10, ga_generations=10, seed=1),
        seed=1,
    )

    assert len(reports) == 2
    assert reports[0].n_nodes == 10
    assert reports[1].n_nodes == 15


# ---- paired QPSO vs PSO comparison ------------------------------------------


def test_sign_test_p_value_matches_hand_computed_values():
    assert sign_test_p_value(0, 0) == 1.0  # nothing decisive
    assert sign_test_p_value(5, 0) == pytest.approx(1 / 32)
    assert sign_test_p_value(0, 5) == 1.0
    assert sign_test_p_value(23, 7) == pytest.approx(0.0026, abs=1e-4)  # the teammate's 23-7 result
    assert sign_test_p_value(5, 5) == pytest.approx(0.623, abs=1e-3)


def test_iterations_to_reach():
    history = [10.0, 8.0, 8.0, 5.0, 4.0]
    assert iterations_to_reach(history, 8.0) == 1
    assert iterations_to_reach(history, 4.5) == 4
    assert iterations_to_reach(history, 10.0) == 0
    assert iterations_to_reach(history, 3.0) is None


def test_run_qpso_vs_pso_reports_consistent_paired_statistics(tmp_path):
    config = BenchmarkConfig(n_particles=10, n_iterations=30)
    report = run_qpso_vs_pso(
        n_stops=6, instance_seeds=range(300, 304), algo_seeds=(1, 2), nodes_per_stop=3, config=config
    )

    assert report.n_instances == 4
    for stats in (report.raw, report.polished):
        assert stats.wins + stats.ties + stats.losses == 4
        assert 0.0 <= stats.sign_test_p <= 1.0
        assert stats.worst_improvement_pct <= stats.mean_improvement_pct + 1e-9
    assert report.qpso_seed_std is not None and report.pso_seed_std is not None
    assert 0.0 <= report.convergence.reached_fraction <= 1.0

    assert len(report.rows) == 4 * 2 * 2  # instances x seeds x {QPSO, PSO}
    table = report.summary_table()
    assert "raw (no local search)" in table
    assert "sign-test" in table

    csv_path = tmp_path / "nested" / "run.csv"
    report.to_csv(csv_path)
    with csv_path.open() as f:
        written = list(csv.DictReader(f))
    assert len(written) == len(report.rows)
    assert {"algorithm", "raw_cost", "polished_cost", "iterations_to_match_pso_final"} <= set(written[0])


def test_run_qpso_vs_pso_single_seed_has_no_seed_std():
    report = run_qpso_vs_pso(
        n_stops=5, instance_seeds=range(300, 303), nodes_per_stop=3, config=BenchmarkConfig(n_particles=8, n_iterations=10)
    )
    assert report.qpso_seed_std is None and report.pso_seed_std is None


def test_pso_kwargs_change_the_baseline():
    config = BenchmarkConfig(n_particles=10, n_iterations=30)
    common = dict(n_stops=6, instance_seeds=range(300, 303), nodes_per_stop=3, config=config)

    default = run_qpso_vs_pso(**common)
    frozen = run_qpso_vs_pso(**common, pso_kwargs=dict(v_max=1e-9))  # a PSO that cannot move

    assert frozen.raw.pso_mean_cost != default.raw.pso_mean_cost
