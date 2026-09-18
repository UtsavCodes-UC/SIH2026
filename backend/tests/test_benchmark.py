from app.core.benchmark import BenchmarkConfig, run_benchmark, run_scalability_sweep
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
    assert exact.optimality_gap_pct == 0.0

    for algo in report.algorithms:
        assert algo.optimality_gap_pct >= -1e-6  # nothing should beat the exact optimum


def test_run_benchmark_skips_exact_when_too_many_stops():
    graph = generate_synthetic_graph(n_nodes=30, seed=1)
    request = RouteRequest(depot=0, stops=list(range(1, 20)))
    config = BenchmarkConfig(n_particles=10, n_iterations=10, ga_population_size=10, ga_generations=10, seed=1)

    report = run_benchmark(graph, request, config)

    names = {algo.name for algo in report.algorithms}
    assert "held_karp_exact" not in names
    assert report.exact_cost is None
    assert all(algo.optimality_gap_pct is None for algo in report.algorithms)


def test_summary_table_renders_without_error():
    graph = generate_synthetic_graph(n_nodes=15, seed=1)
    request = RouteRequest(depot=0, stops=[1, 2, 3])
    report = run_benchmark(graph, request, BenchmarkConfig(n_particles=10, n_iterations=10, seed=1))

    table = report.summary_table()
    assert "qpso" in table
    assert "held_karp_exact" in table


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
