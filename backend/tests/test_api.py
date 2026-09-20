import pytest
from fastapi.testclient import TestClient

from app.core.graph_model import TrafficGraph
from app.data.osm_loader import CityLoadError, UnusablePlaceError
from app.data.synthetic_graph_generator import generate_synthetic_graph, georeference
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


def edge_congestions(graph_id: str) -> list[float]:
    return [e[2] for e in client.get(f"/api/graph/{graph_id}").json()["edges"]]


def solve(graph_id: str, **overrides) -> dict:
    response = client.post("/api/optimize", json={"graph_id": graph_id, **FAST, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


# ---- graph ------------------------------------------------------------------


def test_health_endpoints():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}


def test_synthetic_graph_view_is_consistent():
    view = make_graph(n_nodes=40)
    summary, nodes, edges = view["summary"], view["nodes"], view["edges"]

    assert summary["source"] == "synthetic" and summary["node_count"] == 40
    ids = {int(n[0]) for n in nodes}
    assert len(ids) == 40 and all(len(n) == 3 for n in nodes)
    assert all(int(u) in ids and int(v) in ids for u, v, _ in edges)
    (south, west), (north, east) = summary["bounds"]
    assert all(south <= n[1] <= north and west <= n[2] <= east for n in nodes)
    assert summary["mean_congestion"] > 0


def test_get_graph_roundtrip_and_unknown_id():
    view = make_graph()
    assert client.get(f"/api/graph/{view['summary']['graph_id']}").json()["summary"] == view["summary"]
    assert client.get("/api/graph/nope").status_code == 404


def test_presets_lists_real_places():
    presets = client.get("/api/graph/presets").json()
    assert len(presets) >= 3 and {"name", "lat", "lon"} <= set(presets[0])


def test_congestion_clear_random_and_rush_hour():
    graph_id = make_graph(n_nodes=80)["summary"]["graph_id"]

    cleared = client.post(f"/api/graph/{graph_id}/congestion", json={"mode": "clear"}).json()
    assert cleared["summary"]["mean_congestion"] == pytest.approx(1.0)

    client.post(f"/api/graph/{graph_id}/congestion", json={"mode": "random", "low": 1.5, "high": 2.0, "seed": 3})
    assert all(1.5 <= c <= 2.0 for c in edge_congestions(graph_id))

    view = client.post(f"/api/graph/{graph_id}/congestion", json={"mode": "rush_hour", "peak": 3.0, "seed": 3}).json()
    nodes = {int(n[0]): (n[1], n[2]) for n in view["nodes"]}
    centre_lat = sum(p[0] for p in nodes.values()) / len(nodes)
    centre_lon = sum(p[1] for p in nodes.values()) / len(nodes)

    def distance(edge):
        (la, lo), (lb, lb_o) = nodes[int(edge[0])], nodes[int(edge[1])]
        return (((la + lb) / 2 - centre_lat) ** 2 + ((lo + lb_o) / 2 - centre_lon) ** 2) ** 0.5

    ranked = sorted(view["edges"], key=distance)
    third = len(ranked) // 3
    inner = sum(e[2] for e in ranked[:third]) / third
    outer = sum(e[2] for e in ranked[-third:]) / third
    assert inner > outer + 0.3  # the busy core is clearly slower than the outskirts


def test_congestion_request_validation():
    graph_id = make_graph()["summary"]["graph_id"]
    assert client.post(f"/api/graph/{graph_id}/congestion", json={"mode": "gridlock"}).status_code == 422
    bad = {"mode": "random", "low": 3.0, "high": 1.0}
    assert client.post(f"/api/graph/{graph_id}/congestion", json=bad).status_code == 422


# ---- city loading (network stubbed) ---------------------------------------------


def test_city_endpoint_uses_the_loader_and_reports_its_source(monkeypatch):
    def fake_loader(lat, lon, radius_m=1500, network_type="drive", refresh=False):
        graph = generate_synthetic_graph(n_nodes=30, area_size_km=2, seed=5)
        georeference(graph, lat, lon)
        return graph

    monkeypatch.setattr("app.api.graph.load_city_graph", fake_loader)
    response = client.post("/api/graph/city", json={"lat": 28.63, "lon": 77.21, "radius_m": 800})

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["source"] == "city" and "800 m" in summary["label"]
    assert summary["center"] == [28.63, 77.21]


def test_city_endpoint_needs_a_location_and_maps_network_failures_to_503(monkeypatch):
    assert client.post("/api/graph/city", json={"radius_m": 800}).status_code == 422

    def unreachable(*args, **kwargs):
        raise CityLoadError("Overpass is unreachable")

    monkeypatch.setattr("app.api.graph.load_city_graph", unreachable)
    response = client.post("/api/graph/city", json={"lat": 28.63, "lon": 77.21})
    assert response.status_code == 503 and "Overpass" in response.json()["detail"]


def fake_city_loader(n_nodes=30):
    def loader(lat, lon, radius_m=1500, network_type="drive", refresh=False):
        graph = generate_synthetic_graph(n_nodes=n_nodes, area_size_km=2, seed=5)
        georeference(graph, lat, lon)
        return graph

    return loader


def test_a_typed_place_is_geocoded_and_labelled_with_where_the_search_put_it(monkeypatch):
    asked = []

    def geocode(place):
        asked.append(place)
        return 12.9352, 77.6245

    monkeypatch.setattr("app.api.graph.geocode", geocode)
    monkeypatch.setattr("app.api.graph.load_city_graph", fake_city_loader())
    response = client.post("/api/graph/city", json={"place": "  Koramangala,   Bengaluru ", "radius_m": 800})

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert asked == ["Koramangala, Bengaluru"]  # whitespace tidied before the lookup
    assert summary["center"] == [12.9352, 77.6245]
    assert summary["label"] == "Koramangala, Bengaluru (12.9352, 77.6245), 800 m radius"
    assert summary["source"] == "city" and summary["traffic"]["kind"] == "free_flow"


def test_a_place_with_coordinates_is_not_geocoded_again(monkeypatch):
    def geocode(place):
        raise AssertionError("presets already carry their coordinates")

    monkeypatch.setattr("app.api.graph.geocode", geocode)
    monkeypatch.setattr("app.api.graph.load_city_graph", fake_city_loader())
    response = client.post("/api/graph/city", json={"place": "MG Road, Bengaluru", "lat": 12.9758, "lon": 77.6068})
    assert response.status_code == 200 and response.json()["summary"]["label"].startswith("MG Road, Bengaluru, ")


def test_blank_place_names_are_rejected_before_any_lookup():
    for blank in ("", "   "):
        assert client.post("/api/graph/city", json={"place": blank}).status_code == 422


def test_an_unknown_place_is_the_users_to_fix_not_a_server_outage(monkeypatch):
    def geocode(place):
        raise UnusablePlaceError("Couldn't find a place called 'Atlantis'. Try adding the city or country.")

    monkeypatch.setattr("app.api.graph.geocode", geocode)
    response = client.post("/api/graph/city", json={"place": "Atlantis"})
    assert response.status_code == 422 and "Atlantis" in response.json()["detail"]


def test_a_place_with_almost_no_roads_is_refused_with_advice(monkeypatch):
    monkeypatch.setattr("app.api.graph.geocode", lambda place: (10.0, 20.0))
    monkeypatch.setattr("app.api.graph.load_city_graph", fake_city_loader(n_nodes=10))  # the smallest network the generator makes
    monkeypatch.setattr("app.api.graph.MIN_CITY_NODES", 11)  # so 10 intersections counts as "almost no roads"
    response = client.post("/api/graph/city", json={"place": "Middle of the sea", "radius_m": 500})
    assert response.status_code == 422
    assert "10 drivable intersections" in response.json()["detail"] and "larger radius" in response.json()["detail"]


# ---- optimize -----------------------------------------------------------------


def test_optimize_single_vehicle_returns_a_consistent_route():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    coords = {int(n[0]): [n[1], n[2]] for n in view["nodes"]}

    out = solve(graph_id, n_stops=8, n_vehicles=1, algorithm="qpso")
    problem, route = out["problem"], out["routes"][0]

    assert len(out["routes"]) == 1 and problem["n_vehicles"] == 1
    assert route["nodes"][0] == route["nodes"][-1] == problem["depot"]
    assert sorted(route["nodes"][1:-1]) == sorted(problem["stops"])
    assert route["path"][0] == pytest.approx(coords[problem["depot"]]) and route["path"][-1] == pytest.approx(coords[problem["depot"]])
    assert out["total_time_min"] == pytest.approx(route["time_min"])
    assert out["total_distance_km"] == pytest.approx(route["distance_km"]) and route["distance_km"] > 0
    assert out["polished"] and out["cost"] <= out["raw_cost"] + 1e-6
    history = out["convergence"]
    assert len(history) == FAST["n_iterations"] + 1
    assert all(b <= a + 1e-9 for a, b in zip(history, history[1:]))


def test_optimize_multi_vehicle_auto_fleet_visits_every_stop_once():
    graph_id = make_graph()["summary"]["graph_id"]

    out = solve(graph_id, n_stops=14)
    problem = out["problem"]

    assert problem["n_vehicles"] >= 2  # 14 stops x ~15 demand needs several 100-capacity vehicles
    assert len(out["routes"]) <= problem["n_vehicles"]
    assert sorted(n for r in out["routes"] for n in r["nodes"] if n != problem["depot"]) == sorted(problem["stops"])
    assert sum(r["load"] for r in out["routes"]) == pytest.approx(sum(problem["demands"].values()))
    assert out["feasible"] == (out["capacity_violation"] == 0)
    assert out["total_time_min"] == pytest.approx(sum(r["time_min"] for r in out["routes"]))


def test_optimize_is_deterministic_for_a_seed_and_echoes_the_resolved_problem():
    graph_id = make_graph()["summary"]["graph_id"]
    first = solve(graph_id, n_stops=10, seed=7)
    second = solve(graph_id, n_stops=10, seed=7)
    assert first["problem"] == second["problem"] and first["cost"] == second["cost"]

    # re-running with the echoed problem reproduces it (how the UI re-solves after a traffic change)
    problem = first["problem"]
    rerun = solve(
        graph_id, depot=problem["depot"], stops=problem["stops"], demands=problem["demands"],
        n_vehicles=problem["n_vehicles"], vehicle_capacity=problem["vehicle_capacity"], seed=7,
    )
    assert rerun["cost"] == first["cost"]


@pytest.mark.parametrize("algorithm", ["qpso", "pso", "ga", "nearest_neighbor", "route_search"])
def test_every_algorithm_solves_a_problem(algorithm):
    graph_id = make_graph()["summary"]["graph_id"]
    out = solve(graph_id, n_stops=8, algorithm=algorithm, time_limit_sec=2)
    assert out["algorithm"] == algorithm and out["total_time_min"] > 0


def test_the_default_solver_is_still_qpso_with_warm_start_and_polish():
    """The route search is an option; a request that names no algorithm gets what it always got."""
    graph_id = make_graph()["summary"]["graph_id"]
    out = solve(graph_id, n_stops=8)
    assert out["algorithm"] == "qpso" and out["warm_start"] and out["polished"]


def test_route_search_returns_a_valid_plan_and_reports_itself_honestly():
    graph_id = make_graph()["summary"]["graph_id"]

    out = solve(graph_id, n_stops=14, algorithm="route_search", time_limit_sec=2)
    problem = out["problem"]

    assert problem["n_vehicles"] >= 2
    assert sorted(n for r in out["routes"] for n in r["nodes"] if n != problem["depot"]) == sorted(problem["stops"])
    assert len(out["routes"]) <= problem["n_vehicles"]
    assert out["feasible"] and out["capacity_violation"] == 0 and out["warnings"] == []
    assert out["total_time_min"] == pytest.approx(sum(r["time_min"] for r in out["routes"]))
    # it is its own polish and uses no swarm, and says so
    assert out["polished"] is False and out["warm_start"] is False and out["cost"] == out["raw_cost"]
    assert out["cost"] == pytest.approx(out["total_time_min"])  # nothing overloaded, so cost is pure travel time
    assert out["iterations"] >= 1 and out["runtime_sec"] > 0
    history = out["convergence"]
    assert history[-1] == pytest.approx(out["cost"]) and all(b <= a + 1e-9 for a, b in zip(history, history[1:]))


def test_route_search_is_never_worse_than_nearest_neighbour_on_the_same_problem():
    graph_id = make_graph()["summary"]["graph_id"]
    baseline = solve(graph_id, n_stops=20, algorithm="nearest_neighbor")
    problem = baseline["problem"]
    same = dict(depot=problem["depot"], stops=problem["stops"], demands=problem["demands"], n_vehicles=problem["n_vehicles"])

    searched = solve(graph_id, algorithm="route_search", time_limit_sec=2, **same)

    assert searched["cost"] < baseline["cost"]


def test_route_search_on_one_vehicle_works_and_says_it_is_not_built_for_that():
    graph_id = make_graph()["summary"]["graph_id"]

    out = solve(graph_id, n_stops=8, n_vehicles=1, vehicle_capacity=1000, algorithm="route_search", time_limit_sec=2)

    assert len(out["routes"]) == 1 and sorted(out["routes"][0]["nodes"][1:-1]) == sorted(out["problem"]["stops"])
    assert len(out["warnings"]) == 1 and "several vehicles" in out["warnings"][0]


def test_route_search_time_limit_is_validated():
    graph_id = make_graph()["summary"]["graph_id"]
    post = lambda **body: client.post("/api/optimize", json={"graph_id": graph_id, "algorithm": "route_search", "n_stops": 6, **body})  # noqa: E731
    assert post(time_limit_sec=0).status_code == 422
    assert post(time_limit_sec=61).status_code == 422
    assert post(time_limit_sec=1).status_code == 200


def test_polish_can_be_switched_off():
    graph_id = make_graph()["summary"]["graph_id"]
    out = solve(graph_id, n_stops=8, polish=False)
    assert not out["polished"] and out["cost"] == out["raw_cost"]


def test_solving_reacts_to_traffic():
    graph_id = make_graph()["summary"]["graph_id"]
    client.post(f"/api/graph/{graph_id}/congestion", json={"mode": "clear"})
    free_flow = solve(graph_id, n_stops=8, algorithm="nearest_neighbor")

    client.post(f"/api/graph/{graph_id}/congestion", json={"mode": "random", "low": 2.0, "high": 3.0, "seed": 1})
    problem = free_flow["problem"]
    jammed = solve(
        graph_id, depot=problem["depot"], stops=problem["stops"], demands=problem["demands"],
        n_vehicles=problem["n_vehicles"], algorithm="nearest_neighbor",
    )
    assert jammed["total_time_min"] > free_flow["total_time_min"]


def test_bad_problems_are_rejected_with_a_reason():
    view = make_graph()
    graph_id, nodes = view["summary"]["graph_id"], [int(n[0]) for n in view["nodes"]]
    post = lambda **body: client.post("/api/optimize", json={"graph_id": graph_id, **FAST, **body})  # noqa: E731

    assert client.post("/api/optimize", json={"graph_id": "nope", **FAST}).status_code == 404
    assert post(depot=99999).status_code == 422
    assert post(depot=nodes[0], stops=[nodes[0], nodes[1]]).status_code == 422  # depot as a stop
    assert post(stops=[nodes[1], nodes[1]]).status_code == 422  # duplicate
    assert post(stops=[99999]).status_code == 422  # unknown node
    assert post(depot=nodes[0], stops=[nodes[1], nodes[2]], demands={nodes[1]: 5}).status_code == 422
    assert post(n_stops=0).status_code == 422
    assert post(n_iterations=10_000).status_code == 422


def test_unreachable_stop_is_reported_not_crashed():
    g = TrafficGraph()
    for i, (lat, lon) in enumerate([(28.60, 77.20), (28.61, 77.21), (28.62, 77.22), (28.63, 77.23)]):
        g.add_node(i, lat=lat, lon=lon, pos=(i * 1.0, i * 1.0))
    for u, v in [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3)]:  # node 3 can be entered but never left
        g.add_edge(u, v, 1.0, 1.0)
    stored = get_store().add(g, "synthetic", "dead end", (28.6, 77.2))

    response = client.post("/api/optimize", json={"graph_id": stored.graph_id, "depot": 0, "stops": [1, 3], **FAST})

    assert response.status_code == 422 and "not reachable" in response.json()["detail"]


# ---- benchmark ------------------------------------------------------------------


def test_benchmark_single_vehicle_includes_the_exact_baseline():
    graph_id = make_graph()["summary"]["graph_id"]

    response = client.post("/api/benchmark", json={"graph_id": graph_id, "n_stops": 6, "n_vehicles": 1, **FAST})

    assert response.status_code == 200
    body = response.json()
    names = {a["name"] for a in body["algorithms"]}
    assert names == {"nearest_neighbor", "classical_pso", "genetic_algorithm", "qpso", "held_karp_exact"}
    assert body["exact_cost"] is not None
    for algo in body["algorithms"]:
        assert algo["raw_gap_pct"] >= -1e-6
    exact = next(a for a in body["algorithms"] if a["name"] == "held_karp_exact")
    assert exact["raw_gap_pct"] == 0 and exact["polished_cost"] is None


def test_benchmark_splits_cost_into_time_and_overload():
    graph_id = make_graph()["summary"]["graph_id"]

    body = client.post("/api/benchmark", json={"graph_id": graph_id, "n_stops": 8, **FAST}).json()

    assert body["warnings"] == []
    for algo in body["algorithms"]:
        assert algo["raw_cost"] == pytest.approx(algo["time_min"] + 1000.0 * algo["capacity_violation"])


def test_infeasible_by_construction_problems_are_flagged():
    graph_id = make_graph()["summary"]["graph_id"]
    # one vehicle of capacity 20 cannot carry ~8 stops of 5-25 units each
    tight = {"n_stops": 8, "n_vehicles": 1, "vehicle_capacity": 20}

    optimized = solve(graph_id, **tight)
    benchmark = client.post("/api/benchmark", json={"graph_id": graph_id, **tight, **FAST}).json()

    for warnings in (optimized["warnings"], benchmark["warnings"]):
        assert len(warnings) == 1 and "exceeds the fleet's capacity" in warnings[0]
    assert optimized["feasible"] is False and optimized["capacity_violation"] > 0
    assert all(a["capacity_violation"] > 0 for a in benchmark["algorithms"])
    assert solve(graph_id, n_stops=8)["warnings"] == []  # the auto-sized fleet is never flagged


def test_benchmark_leaves_the_route_search_out_unless_asked():
    graph_id = make_graph()["summary"]["graph_id"]
    body = client.post("/api/benchmark", json={"graph_id": graph_id, "n_stops": 10, **FAST}).json()
    assert "route_search" not in {a["name"] for a in body["algorithms"]}


def test_benchmark_can_include_the_route_search():
    graph_id = make_graph()["summary"]["graph_id"]

    body = client.post("/api/benchmark", json={"graph_id": graph_id, "n_stops": 10, "include_route_search": True, "time_limit_sec": 2, **FAST}).json()

    assert {a["name"] for a in body["algorithms"]} == {"nearest_neighbor", "classical_pso", "genetic_algorithm", "qpso", "route_search"}
    row = next(a for a in body["algorithms"] if a["name"] == "route_search")
    assert row["polished_cost"] is None and row["polished_gap_pct"] is None and row["iterations"] >= 1
    assert row["raw_cost"] == pytest.approx(row["time_min"] + 1000.0 * row["capacity_violation"])
    assert row["convergence"][-1] == pytest.approx(row["raw_cost"])


def test_benchmark_route_search_gap_to_the_exact_optimum_on_one_vehicle():
    graph_id = make_graph()["summary"]["graph_id"]

    body = client.post(
        "/api/benchmark", json={"graph_id": graph_id, "n_stops": 6, "n_vehicles": 1, "include_route_search": True, "time_limit_sec": 2, **FAST}
    ).json()

    row = next(a for a in body["algorithms"] if a["name"] == "route_search")
    assert row["raw_gap_pct"] >= -1e-6  # nothing beats the exact optimum
    assert row["raw_gap_pct"] == pytest.approx(100 * (row["raw_cost"] - body["exact_cost"]) / body["exact_cost"])


def test_benchmark_multi_vehicle_has_no_exact_baseline():
    graph_id = make_graph()["summary"]["graph_id"]

    body = client.post("/api/benchmark", json={"graph_id": graph_id, "n_stops": 10, **FAST}).json()

    assert body["problem"]["n_vehicles"] >= 2
    assert body["exact_cost"] is None
    assert "held_karp_exact" not in {a["name"] for a in body["algorithms"]}
    assert all(a["raw_gap_pct"] is None for a in body["algorithms"])
