"""Blocking roads: what closing a road does to the graph view, to plans and to shortest paths; and the capacity warning."""

import pytest
from fastapi.testclient import TestClient

from app.core.graph_model import TrafficGraph
from app.main import app
from app.services.graph_store import get_store

client = TestClient(app)
FAST = {"n_particles": 10, "n_iterations": 30}


@pytest.fixture(autouse=True)
def clean_store():
    get_store().clear()
    yield
    get_store().clear()


def make_graph(n_nodes=40, seed=1) -> dict:
    response = client.post("/api/graph/synthetic", json={"n_nodes": n_nodes, "seed": seed, "area_size_km": 6})
    assert response.status_code == 200, response.text
    return response.json()


def close(graph_id, roads):
    return client.put(f"/api/graph/{graph_id}/closures", json={"roads": roads})


def view_of(graph_id):
    return client.get(f"/api/graph/{graph_id}").json()


def roads_of(view):
    return {frozenset((int(u), int(v))) for u, v, _ in view["edges"]}


def solve(graph_id, **overrides):
    response = client.post("/api/optimize", json={"graph_id": graph_id, **FAST, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def roads_driven(body, view):
    """The roads (as node pairs) that a plan's polylines run along."""
    ids = {(round(lat, 7), round(lon, 7)): int(n) for n, lat, lon in view["nodes"]}
    driven = set()
    for route in body["routes"]:
        points = [ids[(round(lat, 7), round(lon, 7))] for lat, lon in route["path"]]
        driven |= {frozenset(pair) for pair in zip(points, points[1:])}
    return driven


# ---- the graph ----------------------------------------------------------------


def test_closing_a_road_removes_it_from_the_map_and_reopening_restores_it_exactly():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    u, v, _ = view["edges"][0]

    closed = close(graph_id, [[u, v]])

    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["closed"] == [[u, v]] and body["summary"]["closed_roads"] == 1
    assert frozenset((int(u), int(v))) not in roads_of(body)
    assert len(body["edges"]) == len(view["edges"]) - 1
    assert body["summary"]["edge_count"] < view["summary"]["edge_count"]

    reopened = close(graph_id, []).json()

    assert reopened["closed"] == [] and reopened["summary"]["closed_roads"] == 0
    assert sorted(map(tuple, reopened["edges"])) == sorted(map(tuple, view["edges"]))  # same roads, same congestion
    assert reopened["summary"]["edge_count"] == view["summary"]["edge_count"]


def test_both_directions_of_a_two_way_road_close_whichever_way_it_is_named():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    u, v, _ = view["edges"][0]

    body = close(graph_id, [[v, u]]).json()  # named the other way round

    g = get_store().get(graph_id).graph.graph
    assert not g.has_edge(int(u), int(v)) and not g.has_edge(int(v), int(u))
    assert body["summary"]["closed_roads"] == 1


def test_the_request_is_the_whole_set_so_a_road_left_out_reopens():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    (a, b, _), (c, d, _) = view["edges"][0], view["edges"][1]

    close(graph_id, [[a, b]])
    body = close(graph_id, [[c, d]]).json()

    assert body["closed"] == [[c, d]]
    assert frozenset((int(a), int(b))) in roads_of(body) and frozenset((int(c), int(d))) not in roads_of(body)
    assert close(graph_id, [[c, d], [c, d], [d, c]]).json()["summary"]["closed_roads"] == 1  # the same road named thrice


def test_a_road_that_does_not_exist_is_rejected_and_changes_nothing():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    u, v, _ = view["edges"][0]
    known = {frozenset((int(a), int(b))) for a, b, _ in view["edges"]}
    nodes = [int(n[0]) for n in view["nodes"]]
    missing = next([a, b] for a in nodes for b in nodes if a != b and frozenset((a, b)) not in known)

    assert close(graph_id, [[u, v], missing]).status_code == 422
    assert close(graph_id, [[u, u]]).status_code == 422
    assert close("nope", []).status_code == 404
    assert view_of(graph_id)["closed"] == []


def test_traffic_changes_leave_closed_roads_closed():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    u, v, _ = view["edges"][0]
    close(graph_id, [[u, v]])

    after = client.post(f"/api/graph/{graph_id}/congestion", json={"mode": "rush_hour", "seed": 3}).json()

    assert after["closed"] == [[u, v]]
    assert frozenset((int(u), int(v))) not in roads_of(after)
    assert frozenset((int(u), int(v))) in roads_of(close(graph_id, []).json())


def test_closing_every_road_at_an_intersection_cuts_it_off():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    victim = int(view["nodes"][5][0])
    around = [[u, v] for u, v, _ in view["edges"] if victim in (int(u), int(v))]
    assert view["cut_off"] == [] and around

    body = close(graph_id, around).json()

    assert body["cut_off"] == [victim]
    assert close(graph_id, []).json()["cut_off"] == []


# ---- plans and shortest paths ---------------------------------------------------


def test_a_plan_drives_around_a_closed_road():
    view = make_graph(n_nodes=50, seed=2)
    graph_id = view["summary"]["graph_id"]
    before = solve(graph_id, n_stops=10, algorithm="nearest_neighbor")
    used = roads_driven(before, view)
    # close a road the plan was using, provided the network stays connected (checked by the solve succeeding)
    for road in sorted(used, key=sorted):
        u, v = sorted(road)
        if close(graph_id, [[u, v]]).json()["cut_off"]:
            close(graph_id, [])
            continue
        after = solve(graph_id, n_stops=10, algorithm="nearest_neighbor", stops=before["problem"]["stops"], depot=before["problem"]["depot"],
                      demands=before["problem"]["demands"])
        assert road not in roads_driven(after, view_of(graph_id))
        assert set(after["problem"]["stops"]) == set(before["problem"]["stops"])
        return
    pytest.fail("no road of the plan could be closed without cutting something off")


def test_the_quickest_route_goes_around_a_closed_road_and_comes_back_when_it_reopens():
    view = make_graph(n_nodes=50, seed=3)
    graph_id = view["summary"]["graph_id"]
    nodes = [int(n[0]) for n in view["nodes"]]
    source, target = nodes[0], nodes[-1]

    def quickest():
        response = client.post("/api/shortest-path", json={"graph_id": graph_id, "source": source, "target": target})
        return response

    first = quickest().json()["results"][0]
    for a, b in zip(first["nodes"], first["nodes"][1:]):
        if close(graph_id, [[a, b]]).json()["cut_off"]:
            continue
        response = quickest()
        if response.status_code != 200:
            close(graph_id, [])
            continue
        rerouted = response.json()["results"][0]
        assert frozenset((a, b)) not in {frozenset(p) for p in zip(rerouted["nodes"], rerouted["nodes"][1:])}
        assert rerouted["cost"] >= first["cost"] - 1e-9  # closing a road can only make the best route slower
        break
    else:
        pytest.fail("no road of the route could be closed")

    close(graph_id, [])
    again = quickest().json()["results"][0]
    assert again["nodes"] == first["nodes"] and again["cost"] == pytest.approx(first["cost"])


def test_stops_that_the_closures_cut_off_are_named_in_a_clear_error():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    victim = int(view["nodes"][5][0])
    depot = int(view["nodes"][0][0])
    other = int(view["nodes"][7][0])
    close(graph_id, [[u, v] for u, v, _ in view["edges"] if victim in (int(u), int(v))])

    response = client.post("/api/optimize", json={"graph_id": graph_id, "depot": depot, "stops": [victim, other], **FAST})

    assert response.status_code == 422
    assert str(victim) in response.json()["detail"] and "closed road" in response.json()["detail"]
    reached = client.post("/api/shortest-path", json={"graph_id": graph_id, "source": depot, "target": victim})
    assert reached.status_code == 422 and "closed road" in reached.json()["detail"]


def test_random_stops_are_never_drawn_from_cut_off_places():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    victim = int(view["nodes"][5][0])
    close(graph_id, [[u, v] for u, v, _ in view["edges"] if victim in (int(u), int(v))])

    for seed in range(6):
        body = solve(graph_id, n_stops=30, seed=seed, depot=int(view["nodes"][0][0]))
        assert victim not in body["problem"]["stops"] and len(body["problem"]["stops"]) == 30


def test_mutually_reachable_respects_one_way_streets():
    g = TrafficGraph()
    for u, v in [(1, 2), (2, 3), (3, 1), (3, 4)]:  # 4 can be entered but never left
        g.add_edge(u, v, 1.0, 1.0)
    g.add_edge(5, 1, 1.0, 1.0)  # 5 can leave but never be entered
    assert g.mutually_reachable(1) == {1, 2, 3}

    undirected = TrafficGraph(directed=False)
    undirected.add_edge(1, 2, 1.0, 1.0)
    undirected.add_edge(3, 4, 1.0, 1.0)
    assert undirected.mutually_reachable(1) == {1, 2}


# ---- a single stop that does not fit in one vehicle ----------------------------------


def test_a_stop_bigger_than_one_vehicle_is_flagged_by_name():
    graph_id = make_graph()["summary"]["graph_id"]
    stops = [3, 7, 11]
    demands = {"3": 10, "7": 30, "11": 12}

    body = solve(graph_id, stops=stops, demands=demands, vehicle_capacity=20, n_vehicles=3, algorithm="nearest_neighbor")

    warnings = [w for w in body["warnings"] if "more than one vehicle can carry" in w]
    assert len(warnings) == 1 and "stop 7 (30)" in warnings[0] and "1 stop(s)" in warnings[0]
    assert "stop 3" not in warnings[0] and "stop 11" not in warnings[0]
    assert body["capacity_violation"] > 0 and body["feasible"] is False  # the overload it warned about is real
    assert "exceeds the fleet" not in " ".join(body["warnings"])  # the fleet as a whole has room; that is a different warning


def test_no_single_stop_warning_when_every_stop_fits_and_the_benchmark_gets_it_too():
    graph_id = make_graph()["summary"]["graph_id"]
    fits = solve(graph_id, stops=[3, 7], demands={"3": 20, "7": 5}, vehicle_capacity=20, n_vehicles=2, algorithm="nearest_neighbor")
    assert not any("more than one vehicle" in w for w in fits["warnings"])  # exactly the capacity is fine

    bench = client.post(
        "/api/benchmark",
        json={"graph_id": graph_id, "stops": [3, 7], "demands": {"3": 25, "7": 5}, "vehicle_capacity": 20, "n_vehicles": 2, **FAST},
    ).json()
    assert any("more than one vehicle can carry" in w and "stop 3 (25)" in w for w in bench["warnings"])


def test_many_oversized_stops_are_summarized():
    graph_id = make_graph()["summary"]["graph_id"]
    stops = [3, 7, 11, 13, 17, 19, 23]

    body = solve(graph_id, stops=stops, demands={str(s): 50 for s in stops}, vehicle_capacity=20, n_vehicles=7, algorithm="nearest_neighbor")

    (warning,) = [w for w in body["warnings"] if "more than one vehicle can carry" in w]
    assert "7 stop(s)" in warning and "and 2 more" in warning
