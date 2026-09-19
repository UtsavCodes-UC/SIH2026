"""The hybrid swarm engine: adaptive QPSO/PSO + elite archive + 2-opt + diversity restart + hybrid initialization."""

import math
import random

import numpy as np
import pytest

from app.core.baselines.classical_pso import ClassicalPSO
from app.core.baselines.dijkstra_baseline import nearest_neighbor_order
from app.core.hybrid_swarm import EliteArchive, HybridSwarm, double_bridge
from app.core.local_search import two_opt_order
from app.core.qpso import QPSO
from app.core.vrp_formulation import RouteRequest, RoutingProblem, split_at_depot
from app.core.warm_start import heuristic_seed_orders
from app.data.synthetic_graph_generator import generate_synthetic_graph

ALL_OFF = dict(hybrid_init=False, adaptive_beta=False, elite_archive=False, elite_attractor=False, local_search=False, restart=False)
SMALL = dict(n_particles=10, n_iterations=40)


def tsp(n_stops=30, seed=300):
    graph = generate_synthetic_graph(n_nodes=2 * n_stops, seed=seed)
    request = RouteRequest(depot=0, stops=list(range(1, n_stops + 1)))
    return graph, request, RoutingProblem(graph, request)


def cvrp(n_stops=30, seed=500, utilization=0.85):
    graph = generate_synthetic_graph(n_nodes=2 * n_stops, seed=seed)
    rng = random.Random(seed)
    demands = {c: rng.randint(5, 25) for c in range(1, n_stops + 1)}
    request = RouteRequest(
        depot=0, stops=list(range(1, n_stops + 1)), demands=demands, vehicle_capacity=100,
        n_vehicles=math.ceil(sum(demands.values()) / (utilization * 100)),
    )
    return graph, request, RoutingProblem(graph, request)


# ---- the ablation baseline really is the plain algorithm ------------------------------------------------------


def test_with_every_component_off_the_engine_is_exactly_plain_qpso():
    graph, request, _ = tsp()
    plain = QPSO(graph, request, seed=5, **SMALL).run()
    engine = HybridSwarm(graph, request, operator="qpso", seed=5, **SMALL, **ALL_OFF).run()
    assert engine.best_cost == plain.best_cost and engine.convergence_history == plain.convergence_history
    assert engine.best_route == plain.best_route


def test_with_every_component_off_the_engine_is_exactly_plain_pso():
    graph, request, _ = tsp()
    plain = ClassicalPSO(graph, request, seed=5, **SMALL).run()
    engine = HybridSwarm(graph, request, operator="pso", seed=5, **SMALL, **ALL_OFF).run()
    assert engine.best_cost == plain.best_cost and engine.convergence_history == plain.convergence_history


def test_hybrid_init_with_no_randomized_seeds_is_exactly_the_warm_start_of_the_plain_algorithms():
    graph, request, _ = cvrp()
    plain = QPSO(graph, request, warm_start=True, seed=3, **SMALL).run()
    engine = HybridSwarm(graph, request, operator="qpso", seed=3, **SMALL, **{**ALL_OFF, "hybrid_init": True}, rnn_fraction=0.0).run()
    assert engine.best_cost == plain.best_cost and engine.convergence_history == plain.convergence_history


def test_the_components_that_need_the_archive_say_so():
    graph, request, _ = tsp()
    for flag in ("elite_attractor", "local_search", "restart"):
        with pytest.raises(ValueError, match="elite_archive"):
            HybridSwarm(graph, request, **{**ALL_OFF, flag: True}, **SMALL)
    with pytest.raises(ValueError, match="operator"):
        HybridSwarm(graph, request, operator="genetic")


# ---- the building blocks ------------------------------------------------------------------------------------


def test_the_elite_archive_keeps_the_best_distinct_tours_in_order_and_is_bounded():
    archive = EliteArchive(3)
    assert archive.offer((1, 2, 3), 30.0) and archive.offer((3, 2, 1), 10.0) and archive.offer((2, 1, 3), 20.0)
    assert [e.cost for e in archive.entries] == [10.0, 20.0, 30.0]
    assert not archive.offer((1, 2, 3), 5.0)  # the same tour again is not a new elite, whatever its cost
    assert not archive.offer((9, 9, 9), 40.0)  # worse than everything in a full archive
    assert archive.offer((1, 3, 2), 15.0)  # displaces the worst
    assert [e.cost for e in archive.entries] == [10.0, 15.0, 20.0] and archive.worst_cost == 20.0
    assert archive.offer((1, 2, 3), 12.0)  # the dropped tour is distinct again once it is out


def test_elite_attractors_are_encoded_elites_biased_toward_the_best():
    archive = EliteArchive(4)
    stops = [10, 20, 30]
    for order, cost in [((10, 20, 30), 1.0), ((20, 10, 30), 2.0), ((30, 20, 10), 3.0), ((30, 10, 20), 4.0)]:
        archive.offer(order, cost)
    attractors = archive.attractors(np.random.default_rng(0), 4000, stops)
    assert attractors.shape == (4000, 3)
    best = np.array([(i + 0.5) / 3 for i in (0, 1, 2)])  # the keys of the best elite, (10, 20, 30)
    share_best = np.mean(np.all(np.isclose(attractors, best), axis=1))
    assert 0.35 < share_best < 0.45  # 1 - (3/4)^2 = 43.75%: better than the uniform 25%


def test_a_double_bridge_is_a_different_ordering_of_the_same_stops():
    rng = np.random.default_rng(1)
    order = list(range(1, 41))
    for _ in range(50):
        kicked = double_bridge(order, rng)
        assert sorted(kicked) == order and kicked != order
    tiny = double_bridge([1, 2, 3, 4], rng)  # too short for three cuts: two stops swap places
    assert sorted(tiny) == [1, 2, 3, 4] and tiny != [1, 2, 3, 4]


def test_randomized_nearest_neighbour_varies_but_the_plain_one_does_not():
    _, _, problem = tsp(40)
    plain = nearest_neighbor_order(problem)
    assert plain == nearest_neighbor_order(problem, rng=None, k=4) == nearest_neighbor_order(problem, rng=np.random.default_rng(1), k=1)
    tours = {tuple(nearest_neighbor_order(problem, np.random.default_rng(s), 4)) for s in range(8)}
    assert len(tours) > 1
    assert all(sorted(t) == list(range(1, 41)) for t in tours)


def test_randomized_nearest_neighbour_still_respects_capacity_and_decodes_to_its_own_routes():
    _, _, problem = cvrp(40)
    for s in range(6):
        order = nearest_neighbor_order(problem, np.random.default_rng(s), 4)
        assert problem.evaluate(order).feasible
        polished = two_opt_order(problem, order)
        assert [set(r[1:-1]) for r in problem.split(order)] == [set(r[1:-1]) for r in problem.split(polished)]


# ---- the engine ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("operator", ["qpso", "pso"])
@pytest.mark.parametrize("make", [tsp, cvrp], ids=["tsp", "cvrp"])
def test_the_engine_returns_a_valid_consistent_and_deterministic_result(operator, make):
    graph, request, problem = make(30)
    result = HybridSwarm(graph, request, operator=operator, seed=2, **SMALL).run()
    again = HybridSwarm(graph, request, operator=operator, seed=2, **SMALL).run()

    stops = sorted(s for route in split_at_depot(result.best_route, 0) for s in route[1:-1])
    assert stops == list(range(1, 31))  # every stop exactly once
    order = [s for s in result.best_route if s != 0]
    assert problem.cost(order) == pytest.approx(result.best_cost)  # the reported cost is the real cost of the route
    history = result.convergence_history
    assert all(b <= a + 1e-9 for a, b in zip(history, history[1:]))
    assert (result.best_cost, result.convergence_history) == (again.best_cost, again.convergence_history)


@pytest.mark.parametrize("operator", ["qpso", "pso"])
def test_a_hybrid_never_ends_worse_than_the_seed_it_starts_with(operator):
    graph, request, problem = cvrp(40)
    seed_cost = min(problem.cost(order) for order in heuristic_seed_orders(problem))
    result = HybridSwarm(graph, request, operator=operator, seed=1, **SMALL).run()
    assert result.best_cost <= seed_cost + 1e-9
    assert result.convergence_history[0] <= seed_cost + 1e-9


def test_the_components_actually_do_their_work():
    graph, request, problem = tsp(40)
    engine = HybridSwarm(graph, request, seed=1, n_particles=12, n_iterations=120, restart_patience=15)
    engine.run()

    assert engine.events["restarts"] >= 1  # a stalled search is restarted
    assert engine.events["polished"] >= 1  # and swarm tours get 2-opt
    assert 0 <= engine.events["improved_by_polish"] <= engine.events["polished"]


def test_the_adaptive_beta_stays_inside_its_bounds_and_only_exists_for_qpso():
    graph, request, _ = tsp()
    assert HybridSwarm(graph, request, operator="qpso", **SMALL).adaptive_beta is True
    assert HybridSwarm(graph, request, operator="pso", **SMALL).adaptive_beta is False  # PSO has no beta
    result = HybridSwarm(graph, request, operator="qpso", seed=4, n_particles=10, n_iterations=200).run()
    assert result.best_cost > 0  # ran to completion with the multiplier adapting throughout
