"""Route-set local search (relocate, swap, 2-opt*, SWAP*, 2-opt) and iterated local search."""

import math
import random

import pytest

from app.core.baselines.dijkstra_baseline import nearest_neighbor_order
from app.core.route_search import ALL_OPERATORS, RouteSearch, improve_with_search
from app.core.vrp_formulation import RouteRequest, RoutingProblem
from app.data.synthetic_graph_generator import generate_synthetic_graph

PENALTY = 1000.0


def make(n_customers, seed=500, capacity=100, vehicles=None, utilization=0.85, demand_range=(5, 25)):
    graph = generate_synthetic_graph(n_nodes=2 * n_customers, seed=seed)
    rng = random.Random(seed)
    stops = list(range(1, n_customers + 1))
    demands = {c: rng.randint(*demand_range) for c in stops}
    if vehicles is None:
        vehicles = math.ceil(sum(demands.values()) / (utilization * capacity))
    request = RouteRequest(depot=0, stops=stops, demands=demands, vehicle_capacity=capacity, n_vehicles=vehicles)
    return RoutingProblem(graph, request)


def evaluate(problem, routes):
    """Independent cost of a route set: what the rest of the code base would report for it."""
    e = problem.evaluate_routes([[0, *r, 0] if r and r[0] != 0 else list(r) for r in routes if r])
    return e.total_time_min + PENALTY * e.capacity_violation


def start_routes(problem):
    return problem.split(nearest_neighbor_order(problem))


# ---- the running cost is exact -------------------------------------------------------------------------------------


@pytest.mark.parametrize("n_customers,seed", [(20, 500), (40, 501), (60, 502)])
def test_the_tracked_cost_always_equals_an_independent_evaluation(n_customers, seed):
    problem = make(n_customers, seed)
    search = RouteSearch(problem, start_routes(problem), seed=1)
    assert search.cost == pytest.approx(evaluate(problem, search.result_routes()))

    search.local_search()
    assert search.cost == pytest.approx(evaluate(problem, search.result_routes()))
    assert search.cost == pytest.approx(search.recompute_cost())

    search.run_ils(25)
    assert search.cost == pytest.approx(evaluate(problem, search.result_routes()))


def test_every_stop_stays_in_exactly_one_route_and_the_fleet_limit_holds():
    problem = make(50, 503)
    search = RouteSearch(problem, start_routes(problem), seed=2)
    search.local_search()
    search.run_ils(30)
    routes = search.result_routes()
    assert sorted(s for r in routes for s in r[1:-1]) == problem.request.stops
    assert len(routes) <= problem.request.n_vehicles and len(search.routes) == problem.request.n_vehicles
    assert all(r[0] == r[-1] == 0 for r in routes)
    assert all(search.route_of[s] == i for i, r in enumerate(search.routes) for s in r)
    assert search.load == pytest.approx([sum(problem.request.demands[s] for s in r) for r in search.routes])


def test_local_search_never_makes_a_solution_worse_and_a_feasible_one_stays_feasible():
    for seed in range(500, 506):
        problem = make(40, seed)
        start = start_routes(problem)
        assert problem.evaluate_routes(start).feasible
        search = RouteSearch(problem, start, seed=seed)
        before = search.cost
        search.local_search()
        assert search.cost <= before + 1e-9
        assert problem.evaluate_routes(search.result_routes()).feasible


# ---- each operator is exhaustive over its neighbourhood -----------------------------------------------------------------
# With every stop counted as a neighbour, a search that uses only one operator must end in a state where NO move of
# that kind still improves the cost. The moves are enumerated here by brute force, independently of the search.
# The instances are ones where the single-operator search really improves the nearest-neighbour start, so a
# broken operator that never moved would leave improving moves behind and fail these tests.


def small_search(operators, seed=510, n=12, vehicles=3, capacity=45, demand_range=(5, 15)):
    problem = make(n, seed, capacity=capacity, vehicles=vehicles, demand_range=demand_range)
    search = RouteSearch(problem, start_routes(problem), neighbours=n, operators=operators, seed=1)
    search.local_search()
    return problem, search


def routes_of(search):
    return [r[:] for r in search.routes]


def cost_of(problem, routes):
    return evaluate(problem, routes)


@pytest.mark.parametrize("seed", [510, 511, 512, 513])
def test_after_relocate_alone_no_relocation_of_one_to_three_stops_improves(seed):
    problem, search = small_search(("relocate",), seed=seed)
    base = search.cost
    routes = routes_of(search)
    for a, A in enumerate(routes):
        for length in (1, 2, 3):
            for p in range(len(A) - length + 1):
                segment, rest = A[p : p + length], A[:p] + A[p + length :]
                for b in range(len(routes)):
                    target = rest if b == a else routes[b]
                    for at in range(len(target) + 1):
                        candidate = [r[:] for r in routes]
                        candidate[a] = rest
                        candidate[b] = target[:at] + segment + target[at:]
                        assert cost_of(problem, candidate) >= base - 1e-6


@pytest.mark.parametrize("seed", [510, 511, 512, 513])
def test_after_two_opt_star_alone_no_tail_exchange_improves(seed):
    problem, search = small_search(("two_opt_star",), seed=seed)
    base = search.cost
    routes = routes_of(search)
    for a, b in ((a, b) for a in range(len(routes)) for b in range(len(routes)) if a < b):
        A, B = routes[a], routes[b]
        for i in range(len(A) + 1):
            for j in range(len(B) + 1):
                candidate = [r[:] for r in routes]
                candidate[a], candidate[b] = A[:i] + B[j:], B[:j] + A[i:]
                assert cost_of(problem, candidate) >= base - 1e-6


@pytest.mark.parametrize("seed", [510, 511, 512, 513])
def test_after_swap_star_alone_no_two_stop_exchange_with_best_reinsertion_improves(seed):
    problem, search = small_search(("swap_star",), seed=seed)
    base = search.cost
    routes = routes_of(search)
    for a, b in ((a, b) for a in range(len(routes)) for b in range(len(routes)) if a < b):
        for x in routes[a]:
            for y in routes[b]:
                A, B = [s for s in routes[a] if s != x], [s for s in routes[b] if s != y]
                for at_y in range(len(A) + 1):
                    for at_x in range(len(B) + 1):
                        candidate = [r[:] for r in routes]
                        candidate[a], candidate[b] = A[:at_y] + [y] + A[at_y:], B[:at_x] + [x] + B[at_x:]
                        assert cost_of(problem, candidate) >= base - 1e-6


@pytest.mark.parametrize("seed", [510, 514, 517, 518, 523])  # seeds on which a swap-only search really moves (3-78%)
def test_after_swap_alone_no_exchange_in_place_improves(seed):
    problem, search = small_search(("swap",), seed=seed)
    base = search.cost
    routes = routes_of(search)
    for a, b in ((a, b) for a in range(len(routes)) for b in range(len(routes)) if a < b):
        for i, x in enumerate(routes[a]):
            for j, y in enumerate(routes[b]):
                candidate = [r[:] for r in routes]
                candidate[a][i], candidate[b][j] = y, x
                assert cost_of(problem, candidate) >= base - 1e-6


# ---- the new operators find things the old polish could not -------------------------------------------------------------


def test_two_opt_star_and_swap_star_each_improve_solutions_the_other_operators_leave_alone():
    found = {"two_opt_star": 0, "swap_star": 0}
    for seed in range(500, 520):
        problem = make(40, seed)
        base_ops = ("relocate", "swap", "two_opt")
        settled = RouteSearch(problem, start_routes(problem), operators=base_ops, seed=seed)
        settled.local_search()
        for extra in found:
            again = RouteSearch(problem, settled.result_routes(), operators=(*base_ops, extra), seed=seed)
            again.local_search()
            found[extra] += again.cost < settled.cost - 1e-6
    assert found["two_opt_star"] > 0 and found["swap_star"] > 0, found


# ---- fleet, feasibility and edge cases ------------------------------------------------------------------------------------


def test_an_overloaded_vehicle_is_relieved_by_moving_stops_into_an_unused_vehicle():
    problem = make(15, 520, capacity=100, vehicles=4, demand_range=(8, 14))
    stops = problem.request.stops
    search = RouteSearch(problem, [stops], seed=3)  # everything in one van: badly overloaded, three vans idle
    assert search.excess(search.load[0]) > 0
    search.local_search()
    assert all(search.excess(load) == 0 for load in search.load)
    assert sum(1 for r in search.routes if r) >= 2


def test_bad_input_is_rejected():
    problem = make(10, 521)
    with pytest.raises(ValueError, match="operators"):
        RouteSearch(problem, operators=("relocate", "magic"))
    with pytest.raises(ValueError, match="every stop"):
        RouteSearch(problem, [[1, 2, 3]])
    with pytest.raises(ValueError, match="vehicles"):
        RouteSearch(problem, [[s] for s in problem.request.stops])


def test_a_single_vehicle_tour_is_improved_inside_its_route():
    graph = generate_synthetic_graph(n_nodes=60, seed=300)
    problem = RoutingProblem(graph, RouteRequest(depot=0, stops=list(range(1, 31))))
    start = [nearest_neighbor_order(problem)]
    search = RouteSearch(problem, start, seed=1)
    before = search.cost
    search.local_search()
    assert search.cost < before  # relocate (within the route) and 2-opt find improvements on a nearest-neighbour tour
    assert sorted(search.result_routes()[0][1:-1]) == list(range(1, 31))


# ---- iterated local search ---------------------------------------------------------------------------------------------------


def test_iterated_local_search_only_ever_improves_and_is_deterministic():
    problem = make(50, 504)
    a = RouteSearch(problem, start_routes(problem), seed=7)
    a.local_search()
    start_cost = a.cost
    trace = a.run_ils(40)
    assert all(later <= earlier + 1e-9 for earlier, later in zip(trace, trace[1:]))
    assert a.cost <= start_cost + 1e-9 and a.cost == pytest.approx(trace[-1])

    b = RouteSearch(problem, start_routes(problem), seed=7)
    b.local_search()
    assert b.run_ils(40) == trace and b.result_routes() == a.result_routes()


def test_iterated_local_search_beats_a_single_local_search_on_average():
    gains = []
    for seed in range(500, 505):
        problem = make(50, seed)
        search = RouteSearch(problem, start_routes(problem), seed=seed)
        search.local_search()
        settled = search.cost
        search.run_ils(60)
        gains.append(100 * (settled - search.cost) / settled)
    assert sum(gains) / len(gains) > 0.5  # measured at about 2-3% after 60 iterations; a safe margin
    assert min(gains) >= 0


def test_improve_with_search_is_routes_in_routes_out():
    problem = make(30, 505)
    start = start_routes(problem)
    out = improve_with_search(problem, start, iterations=10, seed=3)
    assert sorted(s for r in out for s in r[1:-1]) == problem.request.stops
    assert evaluate(problem, out) <= evaluate(problem, start) + 1e-9
    assert set(ALL_OPERATORS) >= {"relocate", "swap", "two_opt_star", "swap_star", "two_opt"}
