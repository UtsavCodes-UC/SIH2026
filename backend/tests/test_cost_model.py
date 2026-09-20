"""The weighted objective: time, distance and congestion, and what each weighting does to a plan."""

import math
import random

import pytest

from app.core.baselines.exact_held_karp import held_karp
from app.core.cost_model import CostWeights, path_metrics
from app.core.graph_model import TrafficGraph
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot
from app.data.synthetic_graph_generator import generate_synthetic_graph

TIME, DISTANCE, CONGESTION = CostWeights(1, 0, 0), CostWeights(0, 1, 0), CostWeights(0, 0, 1)


def two_ways() -> TrafficGraph:
    """0 -> 1 directly: 1 km, but jammed (2 min free flow, x3 = 6 min, of which 4 are delay).
    0 -> 2 -> 1: 3 km round the back, free flowing (3 min, no delay)."""
    g = TrafficGraph()
    for n in (0, 1, 2):
        g.add_node(n, lat=0.0, lon=0.0)
    g.add_edge(0, 1, distance_km=1.0, base_travel_time_min=2.0, congestion_factor=3.0)
    g.add_edge(0, 2, distance_km=1.5, base_travel_time_min=1.5, congestion_factor=1.0)
    g.add_edge(2, 1, distance_km=1.5, base_travel_time_min=1.5, congestion_factor=1.0)
    g.add_edge(1, 0, distance_km=1.0, base_travel_time_min=2.0, congestion_factor=1.0)
    return g


class TestWeights:
    def test_default_is_plain_travel_time(self):
        assert CostWeights().is_default and CostWeights(1, 0, 0).is_default
        assert not CostWeights(2, 0, 0).is_default and not CostWeights(1, 0.1, 0).is_default

    @pytest.mark.parametrize("bad", [(-1, 1, 0), (1, -0.5, 0), (1, 0, -1), (0, 0, 0), (math.nan, 0, 0), (math.inf, 0, 0)])
    def test_rejects_weights_that_mean_nothing(self, bad):
        with pytest.raises(ValueError):
            CostWeights(*bad)

    def test_an_arc_costs_the_blend_of_its_three_quantities(self):
        edge = {"base_travel_time_min": 2.0, "congestion_factor": 3.0, "distance_km": 1.0}  # 6 min, 1 km, 4 min of delay
        assert TIME.arc_cost(edge) == pytest.approx(6.0)
        assert DISTANCE.arc_cost(edge) == pytest.approx(1.0)
        assert CONGESTION.arc_cost(edge) == pytest.approx(4.0)
        assert CostWeights(0.5, 2.0, 0.25).arc_cost(edge) == pytest.approx(0.5 * 6 + 2 * 1 + 0.25 * 4)

    def test_a_road_faster_than_free_flow_has_no_delay(self):
        edge = {"base_travel_time_min": 2.0, "congestion_factor": 0.8, "distance_km": 1.0}
        assert CONGESTION.arc_cost(edge) == 0.0 and TIME.arc_cost(edge) == pytest.approx(1.6)


class TestPaths:
    def test_each_weighting_picks_the_road_that_is_best_for_it(self):
        g = two_ways()
        assert g.shortest_path(0, 1) == [0, 2, 1]  # quickest: 3 min against 6
        assert g.shortest_path(0, 1, TIME) == [0, 2, 1]
        assert g.shortest_path(0, 1, DISTANCE) == [0, 1]  # shortest: 1 km against 3
        assert g.shortest_path(0, 1, CONGESTION) == [0, 2, 1]  # no delay against 4 minutes of it
        assert g.shortest_path(0, 1, CostWeights(1, 3, 0)) == [0, 1]  # 6 + 3 = 9 beats 3 + 9 = 12
        assert g.shortest_path(0, 1, CostWeights(1, 1, 0)) == [0, 2, 1]  # 6 + 1 = 7 loses to 3 + 3 = 6

    def test_real_metrics_of_a_path_do_not_depend_on_the_weights(self):
        g = two_ways()
        direct, detour = path_metrics(g, [0, 1]), path_metrics(g, [0, 2, 1])
        assert (direct.time_min, direct.distance_km, direct.delay_min) == pytest.approx((6.0, 1.0, 4.0))
        assert (detour.time_min, detour.distance_km, detour.delay_min) == pytest.approx((3.0, 3.0, 0.0))

    def test_leg_costs_are_the_cheapest_path_costs(self):
        g = two_ways()
        assert g.all_pairs_shortest_cost([0, 1], DISTANCE)[0][1] == pytest.approx(1.0)
        assert g.all_pairs_shortest_cost([0, 1], CONGESTION)[0][1] == pytest.approx(0.0)
        assert g.all_pairs_shortest_cost([0, 1], CostWeights(1, 3, 0))[0][1] == pytest.approx(9.0)

    def test_default_weights_give_exactly_the_old_leg_times(self):
        graph = generate_synthetic_graph(n_nodes=30, seed=3)
        nodes = list(graph.graph.nodes)[:8]
        assert graph.all_pairs_shortest_cost(nodes, CostWeights()) == graph.all_pairs_shortest_time(nodes)

    def test_leg_costs_still_obey_the_triangle_inequality(self):
        graph = generate_synthetic_graph(n_nodes=25, seed=4)
        nodes = list(graph.graph.nodes)[:10]
        legs = graph.all_pairs_shortest_cost(nodes, CostWeights(0.5, 0.3, 0.2))
        for a in nodes:
            for b in nodes:
                for c in nodes:
                    assert legs[a][c] <= legs[a][b] + legs[b][c] + 1e-9

    def test_congestion_alone_costs_nothing_on_a_free_flowing_network(self):
        graph = generate_synthetic_graph(n_nodes=15, seed=5)
        for u, v in list(graph.graph.edges()):
            graph.update_congestion(u, v, 1.0)
        legs = graph.all_pairs_shortest_cost(list(graph.graph.nodes)[:5], CONGESTION)
        assert all(cost == 0.0 for row in legs.values() for cost in row.values())


class TestProblem:
    def test_legs_and_plan_cost_use_the_weights(self):
        g = two_ways()
        for weights, leg in ((TIME, 3.0), (DISTANCE, 1.0), (CONGESTION, 0.0)):
            problem = RoutingProblem(g, RouteRequest(depot=0, stops=[1], cost_weights=weights))
            assert problem.leg_time(0, 1) == pytest.approx(leg)
        problem = RoutingProblem(g, RouteRequest(depot=0, stops=[1], cost_weights=DISTANCE))
        assert problem.cost([1]) == pytest.approx(1.0 + 1.0)  # 0 -> 1 and back, 1 km each way

    def test_no_weights_means_plain_time_as_before(self):
        graph = generate_synthetic_graph(n_nodes=20, seed=6)
        stops = list(graph.graph.nodes)[1:7]
        plain = RoutingProblem(graph, RouteRequest(depot=0, stops=stops))
        explicit = RoutingProblem(graph, RouteRequest(depot=0, stops=stops, cost_weights=CostWeights()))
        assert plain.legs == explicit.legs


def plan_metrics(graph, routes, weights):
    """Real time, distance and delay of a plan whose legs follow the cheapest path under `weights`."""
    time = distance = delay = 0.0
    for route in routes:
        for u, v in zip(route, route[1:]):
            m = path_metrics(graph, graph.shortest_path(u, v, weights))
            time, distance, delay = time + m.time_min, distance + m.distance_km, delay + m.delay_min
    return time, distance, delay


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_with_the_exact_solver_each_weighting_wins_on_its_own_measure(seed):
    """Held-Karp finds the true optimum of each blend, so the plan optimized for distance drives no more kilometres than
    the plan optimized for time, and so on. That is a theorem, not a tendency, so it is asserted exactly."""
    graph = generate_synthetic_graph(n_nodes=24, seed=seed)  # random congestion between 0.8x and 2.5x
    rng = random.Random(seed)
    stops = rng.sample([n for n in graph.graph.nodes if n != 0], 7)

    plans = {}
    for name, weights in (("time", TIME), ("distance", DISTANCE), ("congestion", CONGESTION)):
        request = RouteRequest(depot=0, stops=stops, cost_weights=weights)
        routes = split_at_depot(held_karp(graph, request).best_route, 0)
        plans[name] = plan_metrics(graph, routes, weights)

    assert plans["time"][0] <= plans["distance"][0] + 1e-9 and plans["time"][0] <= plans["congestion"][0] + 1e-9
    assert plans["distance"][1] <= plans["time"][1] + 1e-9 and plans["distance"][1] <= plans["congestion"][1] + 1e-9
    assert plans["congestion"][2] <= plans["time"][2] + 1e-9 and plans["congestion"][2] <= plans["distance"][2] + 1e-9
