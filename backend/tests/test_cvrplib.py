"""The CVRPLIB adapter: parsing, the benchmark's rounded distances, and that our solvers score exactly as it does."""

from pathlib import Path

import pytest

from app.core.route_search import RouteSearch
from app.data.cvrplib import (
    CvrpInstance,
    MatrixGraph,
    build_problem,
    check_solution,
    default_fleet,
    load_instance,
    load_solution,
    nint,
    parse_instance,
    parse_solution,
    solution_cost,
)

# Five customers around a depot. Distances: depot-1 = 5 (a 3-4-5 triangle), 1-2 = nint(1.5) = 2, and so on.
SMALL = """NAME : \tX-n006-k2\t
COMMENT : \t"a small hand-made instance"\t
TYPE : \tCVRP\t
DIMENSION : \t6\t
EDGE_WEIGHT_TYPE : \tEUC_2D\t
CAPACITY : \t10\t
NODE_COORD_SECTION\t\t
1\t0\t0
2\t3\t4
3\t4.5\t4
4\t-3\t-4
5\t-3\t-6
6\t0\t10
DEMAND_SECTION\t\t
1\t0
2\t4
3\t4
4\t5
5\t5
6\t2
DEPOT_SECTION\t\t
\t1
\t-1
EOF
"""


def small() -> CvrpInstance:
    return parse_instance(SMALL)


class TestParsing:
    def test_reads_the_fields_and_renumbers_the_depot_to_zero(self):
        inst = small()
        assert inst.name == "X-n006-k2"
        assert inst.capacity == 10
        assert inst.min_vehicles == 2
        assert inst.n_customers == 5
        assert inst.coords[0] == (0.0, 0.0)
        assert inst.coords[1] == (3.0, 4.0)  # customer 1 is the file's node 2
        assert inst.coords[2] == (4.5, 4.0)
        assert inst.demands == (0, 4, 4, 5, 5, 2)

    def test_name_without_a_k_has_no_minimum(self):
        assert parse_instance(SMALL.replace("X-n006-k2", "custom")).min_vehicles is None

    @pytest.mark.parametrize(
        "edit, error",
        [
            (lambda t: t.replace("EUC_2D", "EXPLICIT"), NotImplementedError),
            (lambda t: t.replace("DIMENSION : \t6", "DIMENSION : \t7"), ValueError),
            (lambda t: t.replace("CAPACITY : \t10", "CAPACITY : \t3"), ValueError),  # a customer needs more than a van holds
            (lambda t: t.replace("TYPE : \tCVRP", "TYPE : \tTSP"), ValueError),
            (lambda t: t.replace("DEMAND_SECTION", "SOMETHING_SECTION"), ValueError),
            (lambda t: t.replace("\t1\n\t-1", "\t2\n\t-1"), ValueError),  # the depot is not node 1
            (lambda t: t.replace("1\t0\n2\t4\n", "1\t3\n2\t4\n"), ValueError),  # the depot has demand
        ],
    )
    def test_refuses_what_it_does_not_understand(self, edit, error):
        with pytest.raises(error):
            parse_instance(edit(SMALL))

    def test_solution_file(self):
        routes, cost = parse_solution("Route #1: 2 1\nRoute #2: 5 4 3\nCost 34\n")
        assert routes == [[2, 1], [5, 4, 3]]
        assert cost == 34
        with pytest.raises(ValueError):
            parse_solution("no routes here")


class TestDistances:
    def test_rounding_is_to_the_nearest_integer_halves_up(self):
        assert nint(1.4) == 1 and nint(1.5) == 2 and nint(2.5) == 3 and nint(0.0) == 0

    def test_distances_are_rounded_euclidean(self):
        inst = small()
        assert inst.distance(0, 1) == 5  # 3-4-5
        assert inst.distance(1, 2) == 2  # 1.5 rounds up
        assert inst.distance(0, 5) == 10
        assert inst.distance(1, 0) == inst.distance(0, 1)

    def test_rounding_can_break_the_triangle_inequality_and_the_matrix_keeps_it(self):
        """A(0,0), B(1,1), C(2,2): rounded, A-B = 1 and B-C = 1 but A-C = 3. The benchmark scores the direct leg (3), so
        a shortest-path table (which would say 2) would score routes differently from the published costs."""
        inst = CvrpInstance("tri", 10, ((0, 0), (1, 1), (2, 2)), (0, 1, 1), None)
        problem = build_problem(inst, n_vehicles=2)[2]
        assert problem.leg_time(0, 2) == 3.0
        assert problem.leg_time(0, 1) + problem.leg_time(1, 2) == 2.0

    def test_matrix_graph_answers_only_for_the_nodes_asked_and_zero_on_the_diagonal(self):
        table = MatrixGraph([[0, 4, 9], [4, 0, 5], [9, 5, 0]]).all_pairs_shortest_time([0, 2])
        assert table == {0: {0: 0.0, 2: 9.0}, 2: {0: 9.0, 2: 0.0}}


class TestFleet:
    def test_default_fleet_is_a_quarter_over_k_plus_two(self):
        assert default_fleet(small()) == 5  # ceil(1.25 * 2) + 2

    def test_an_instance_without_a_k_needs_an_explicit_fleet(self):
        with pytest.raises(ValueError):
            default_fleet(parse_instance(SMALL.replace("X-n006-k2", "custom")))


class TestSolverAgreesWithTheBenchmarkScoring:
    def test_routes_cost_the_same_through_the_problem_and_from_the_coordinates(self):
        inst = small()
        _, _, problem = build_problem(inst, n_vehicles=3)
        routes = [[1, 2], [4, 3], [5]]  # customers 1..5: 1-2 | 4-3 | 5 (loads 8, 9, 2)
        full = [[0, *r, 0] for r in routes]
        assert problem.evaluate_routes(full).total_time_min == solution_cost(inst, routes)

    def test_check_solution_catches_each_kind_of_mistake(self):
        inst = small()
        check_solution(inst, [[1, 2], [4, 3], [5]])
        with pytest.raises(AssertionError):
            check_solution(inst, [[1, 2], [4, 3]])  # customer 5 is missing
        with pytest.raises(AssertionError):
            check_solution(inst, [[1, 2, 3], [4, 5]])  # 13 > 10 on the first route
        with pytest.raises(AssertionError):
            check_solution(inst, [[1, 2], [4, 3], [5]], max_vehicles=2)

    def test_the_route_search_solves_it_and_the_reported_cost_is_the_true_one(self):
        inst = small()
        _, request, problem = build_problem(inst, n_vehicles=4)
        from app.core.baselines.dijkstra_baseline import nearest_neighbor_order

        search = RouteSearch(problem, problem.split(nearest_neighbor_order(problem)), seed=1)
        search.local_search()
        search.run_ils(50)
        routes = [r[1:-1] for r in search.result_routes()]
        check_solution(inst, routes, max_vehicles=4)
        assert search.cost == solution_cost(inst, routes)  # nothing overloaded, so cost is pure distance


# The published X-n101-k25 files, if they have been fetched (scripts/fetch_cvrplib.py). They are third-party data and
# git-ignored, so this only runs where they exist.
DATA = Path(__file__).resolve().parent.parent / "data" / "cvrplib"


@pytest.mark.skipif(not (DATA / "X-n101-k25.vrp").exists() or not (DATA / "X-n101-k25.sol").exists(), reason="CVRPLIB files not fetched")
def test_published_optimal_solution_costs_what_the_file_says():
    inst = load_instance(DATA / "X-n101-k25.vrp")
    routes, stated = load_solution(DATA / "X-n101-k25.sol")
    check_solution(inst, routes)
    assert solution_cost(inst, routes) == stated == 27591
    _, _, problem = build_problem(inst, n_vehicles=len(routes))
    assert problem.evaluate_routes([[0, *r, 0] for r in routes]).total_time_min == 27591
