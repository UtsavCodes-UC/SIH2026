"""Soft time windows: the clock, the lateness penalty, and what supports windows and what steps aside."""

import itertools
import math
import random

import pytest

from app.core.baselines.dijkstra_baseline import nearest_neighbor
from app.core.baselines.exact_held_karp import held_karp
from app.core.cost_model import CostWeights
from app.core.graph_model import TrafficGraph
from app.core.local_search import polish_result
from app.core.qpso import QPSO
from app.core.route_search import RouteSearch, solve_with_search
from app.core.time_windows import TimeWindow, random_time_windows, schedule_route
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot
from app.data.synthetic_graph_generator import generate_synthetic_graph


def problem_with_windows(n_stops=10, seed=21, vehicles=3, service=0.0, penalty=10.0, weights=None):
    graph = generate_synthetic_graph(n_nodes=40, area_size_km=8.0, seed=seed)
    rng = random.Random(seed)
    stops = rng.sample([n for n in graph.graph.nodes if n != 0], n_stops)
    demands = {s: rng.randint(5, 25) for s in stops}
    quickest = graph.all_pairs_shortest_time([0])[0]
    windows = random_time_windows(stops, quickest, random.Random(f"{seed}-windows"))
    request = RouteRequest(
        depot=0, stops=stops, demands=demands, vehicle_capacity=100, n_vehicles=vehicles, time_windows=windows,
        service_time_min=service, time_window_penalty=penalty, cost_weights=weights,
    )
    return graph, request, RoutingProblem(graph, request)


class TestWindow:
    @pytest.mark.parametrize("bad", [(-1, 5), (10, 5), (0, math.inf), (math.nan, 3)])
    def test_rejects_windows_that_make_no_sense(self, bad):
        with pytest.raises(ValueError):
            TimeWindow(*bad)

    def test_a_window_may_be_a_single_instant(self):
        assert TimeWindow(30, 30).latest == 30


class TestSchedule:
    # driving minutes: depot(0) -> 1 = 10, 1 -> 2 = 5, 2 -> 0 = 8
    MINUTES = {0: {1: 10.0, 2: 12.0}, 1: {2: 5.0, 0: 9.0}, 2: {0: 8.0, 1: 5.0}}

    def test_early_arrival_waits_late_arrival_is_counted_and_service_time_moves_the_clock(self):
        windows = {1: TimeWindow(20, 40), 2: TimeWindow(0, 12)}
        timing = schedule_route([0, 1, 2, 0], self.MINUTES, windows, service_time_min=3.0)

        first, second = timing.stops
        assert (first.arrival_min, first.start_min, first.wait_min, first.late_min) == (10.0, 20.0, 10.0, 0.0)  # waits for 20
        # leaves at 20 + 3 = 23, arrives at 28: 16 minutes after the window closed at 12
        assert (second.arrival_min, second.start_min, second.wait_min, second.late_min) == (28.0, 28.0, 0.0, 16.0)
        assert timing.end_min == 28 + 3 + 8  # service at the last stop, then the drive home
        assert timing.late_min == 16.0 and timing.wait_min == 10.0

    def test_a_stop_without_a_window_is_always_on_time(self):
        timing = schedule_route([0, 1, 2, 0], self.MINUTES, {2: TimeWindow(0, 100)})
        assert [s.late_min for s in timing.stops] == [0.0, 0.0] and timing.stops[0].earliest is None

    def test_an_empty_route_takes_no_time(self):
        assert schedule_route([0, 0], self.MINUTES, {}).end_min == 0.0


class TestCost:
    @pytest.mark.parametrize("seed", [21, 22, 23])
    def test_the_fast_cost_agrees_with_the_reporting_path_on_random_plans(self, seed):
        """`cost` is a hand-inlined pass for speed; `evaluate` builds routes and schedules. They must agree exactly."""
        _, request, problem = problem_with_windows(seed=seed, service=4.0, weights=CostWeights(0.5, 0.3, 0.2))
        rng = random.Random(seed)
        for _ in range(40):
            order = rng.sample(request.stops, len(request.stops))
            assert problem.cost(order) == pytest.approx(problem.penalized_cost(problem.evaluate(order)))

    def test_lateness_is_priced_and_waiting_is_not(self):
        graph, request, problem = problem_with_windows(vehicles=1, penalty=10.0)
        order = list(request.stops)
        evaluation = problem.evaluate(order)
        assert problem.cost(order) == pytest.approx(
            evaluation.total_time_min + 1000.0 * evaluation.capacity_violation + 10.0 * evaluation.lateness_min
        )
        with_double_penalty = RoutingProblem(graph, RouteRequest(**{**request.__dict__, "time_window_penalty": 20.0}))
        assert with_double_penalty.cost(order) - problem.cost(order) == pytest.approx(10.0 * evaluation.lateness_min)

    def test_no_windows_changes_nothing(self):
        graph, request, _ = problem_with_windows()
        plain = RoutingProblem(graph, RouteRequest(**{**request.__dict__, "time_windows": None}))
        assert not plain.has_time_windows
        order = list(request.stops)
        evaluation = plain.evaluate(order)
        assert plain.cost(order) == pytest.approx(evaluation.total_time_min + 1000.0 * evaluation.capacity_violation)
        assert (evaluation.lateness_min, evaluation.waiting_min, evaluation.late_stops) == (0.0, 0.0, 0)

    def test_the_clock_runs_in_real_minutes_even_when_the_cost_is_a_blend(self):
        g = TrafficGraph()
        for n in (0, 1, 2):
            g.add_node(n, lat=0.0, lon=0.0)
        g.add_edge(0, 1, distance_km=1.0, base_travel_time_min=2.0, congestion_factor=3.0)  # direct: 1 km, 6 min
        g.add_edge(0, 2, distance_km=1.5, base_travel_time_min=1.5, congestion_factor=1.0)
        g.add_edge(2, 1, distance_km=1.5, base_travel_time_min=1.5, congestion_factor=1.0)  # round the back: 3 km, 3 min
        g.add_edge(1, 0, distance_km=1.0, base_travel_time_min=2.0, congestion_factor=1.0)
        by_distance = RoutingProblem(g, RouteRequest(depot=0, stops=[1], cost_weights=CostWeights(0, 1, 0)))
        assert by_distance.leg_time(0, 1) == pytest.approx(1.0)  # the cost is kilometres
        assert by_distance.minutes[0][1] == pytest.approx(6.0)  # the clock is the 6 real minutes of the road it takes

    def test_windows_are_checked_against_the_stops(self):
        graph = generate_synthetic_graph(n_nodes=20, seed=1)
        with pytest.raises(ValueError, match="not stops"):
            RoutingProblem(graph, RouteRequest(depot=0, stops=[1, 2], time_windows={5: TimeWindow(0, 10)}))
        with pytest.raises(ValueError, match="non-negative"):
            RoutingProblem(graph, RouteRequest(depot=0, stops=[1, 2], service_time_min=-1))


class TestSearching:
    def test_a_window_aware_search_finds_the_best_order_by_brute_force(self):
        graph = generate_synthetic_graph(n_nodes=30, area_size_km=8.0, seed=31)
        rng = random.Random(31)
        stops = rng.sample([n for n in graph.graph.nodes if n != 0], 6)
        quickest = graph.all_pairs_shortest_time([0])[0]
        request = RouteRequest(depot=0, stops=stops, time_windows=random_time_windows(stops, quickest, random.Random(5), horizon_min=40), service_time_min=2.0)
        problem = RoutingProblem(graph, request)

        best = min(problem.cost(list(p)) for p in itertools.permutations(stops))
        found = QPSO(graph, request, n_particles=40, n_iterations=300, seed=3).run().best_cost

        assert found == pytest.approx(best, rel=1e-9)
        # and windows genuinely matter here: the plan that ignores them is later than the one that respects them
        ignoring = RoutingProblem(graph, RouteRequest(depot=0, stops=stops, service_time_min=2.0))
        ignoring_order = min(itertools.permutations(stops), key=lambda p: ignoring.cost(list(p)))
        assert problem.cost(list(ignoring_order)) > best

    def test_the_optimal_split_steps_aside_when_there_are_windows(self):
        graph, request, _ = problem_with_windows(vehicles=3)
        asked = RoutingProblem(graph, RouteRequest(**{**request.__dict__, "decoder": "optimal"}))
        greedy = RoutingProblem(graph, request)
        order = list(request.stops)
        assert asked.cost(order) == pytest.approx(greedy.cost(order))  # the greedy cut, as documented

    def test_the_polish_is_only_kept_when_it_does_not_make_things_worse(self):
        for seed in (21, 22, 23, 24):
            graph, request, problem = problem_with_windows(seed=seed, n_stops=12, vehicles=4)
            raw = nearest_neighbor(graph, request)
            polished = polish_result(problem, raw, 1000.0, inter_route=True)
            assert polished.best_cost <= raw.best_cost + 1e-9
            plan = problem.evaluate_routes(split_at_depot(polished.best_route, 0))
            assert problem.penalized_cost(plan) == pytest.approx(polished.best_cost)

    def test_nearest_neighbour_reports_the_windowed_cost(self):
        graph, request, problem = problem_with_windows()
        result = nearest_neighbor(graph, request)
        assert result.best_cost == pytest.approx(problem.penalized_cost(problem.evaluate_routes(split_at_depot(result.best_route, 0))))

    def test_the_route_search_and_the_exact_solver_refuse_windows(self):
        graph, request, problem = problem_with_windows(vehicles=1)
        with pytest.raises(ValueError, match="time windows"):
            RouteSearch(problem)
        with pytest.raises(ValueError, match="time windows"):
            solve_with_search(problem)
        with pytest.raises(ValueError, match="time windows"):
            held_karp(graph, request)


class TestRandomWindows:
    def test_reproducible_well_formed_and_reachable(self):
        stops = list(range(1, 9))
        quickest = {s: 5.0 + 3 * s for s in stops}
        a = random_time_windows(stops, quickest, random.Random(7))
        b = random_time_windows(stops, quickest, random.Random(7))
        assert a == b and set(a) == set(stops)
        for stop, window in a.items():
            assert 0 <= window.earliest <= window.latest
            assert 30 - 0.2 <= window.latest - window.earliest <= 60 + 0.2 or window.earliest == 0  # 30-60 wide, unless clipped at 0
            assert window.latest >= quickest[stop] - 1e-9  # a van driving straight there can make the window's end


class TestWindowAwareSeed:
    def test_it_visits_every_stop_once_and_decodes_into_routes(self):
        from app.core.warm_start import window_aware_order

        _, request, problem = problem_with_windows(n_stops=14, vehicles=4)
        order = window_aware_order(problem)
        assert sorted(order) == sorted(request.stops)
        routes = problem.split(order)
        assert len(routes) <= request.n_vehicles and sorted(s for r in routes for s in r[1:-1]) == sorted(request.stops)

    def test_it_is_later_than_nothing_but_far_less_late_than_plain_nearest_neighbour(self):
        from app.core.baselines.dijkstra_baseline import nearest_neighbor_order
        from app.core.warm_start import window_aware_order

        plain = aware = 0.0
        for seed in range(21, 29):
            _, request, problem = problem_with_windows(n_stops=14, vehicles=4, seed=seed, service=5.0)
            plain += problem.evaluate(nearest_neighbor_order(problem)).lateness_min
            aware += problem.evaluate(window_aware_order(problem)).lateness_min
        assert aware < 0.6 * plain  # on the same problems, the window-aware order arrives far less late

    def test_the_seed_is_offered_only_when_there_are_windows_and_the_switch_is_on(self, monkeypatch):
        from app.core import warm_start

        graph, request, problem = problem_with_windows()
        assert len(warm_start.heuristic_seed_orders(problem)) == 3
        monkeypatch.setattr(warm_start, "WINDOW_AWARE_SEED", False)
        assert len(warm_start.heuristic_seed_orders(problem)) == 2
        monkeypatch.setattr(warm_start, "WINDOW_AWARE_SEED", True)
        plain = RoutingProblem(graph, RouteRequest(**{**request.__dict__, "time_windows": None}))
        assert len(warm_start.heuristic_seed_orders(plain)) == 2
