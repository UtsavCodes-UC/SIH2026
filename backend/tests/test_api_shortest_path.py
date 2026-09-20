"""POST /api/shortest-path: the cheapest way between two points, by Dijkstra and by the searches."""

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.core.graph_model import TrafficGraph
from app.main import app
from app.services.graph_store import get_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    get_store().clear()
    yield
    get_store().clear()


def make_graph(n_nodes=50, seed=3) -> dict:
    response = client.post("/api/graph/synthetic", json={"n_nodes": n_nodes, "seed": seed, "area_size_km": 6})
    assert response.status_code == 200, response.text
    return response.json()


def a_pair(view, min_hops=5):
    """Two nodes with a real journey between them, found on the graph the API returned."""
    g = nx.DiGraph()
    g.add_edges_from((u, v) for u, v, _ in view["edges"])
    g.add_edges_from((v, u) for u, v, _ in view["edges"])  # the view lists each two-way road once
    nodes = [int(n[0]) for n in view["nodes"]]
    for s in nodes:
        for t in nodes:
            if s != t and nx.has_path(g, s, t) and len(nx.shortest_path(g, s, t)) >= min_hops:
                return s, t
    raise AssertionError("no pair found")


def post(graph_id, source, target, **body):
    return client.post("/api/shortest-path", json={"graph_id": graph_id, "source": source, "target": target, **body})


def test_the_exact_route_is_returned_by_default_with_a_polyline_along_the_roads():
    view = make_graph()
    graph_id, coords = view["summary"]["graph_id"], {int(n[0]): [n[1], n[2]] for n in view["nodes"]}
    s, t = a_pair(view)

    response = post(graph_id, s, t)

    assert response.status_code == 200, response.text
    body = response.json()
    (result,) = body["results"]
    assert result["algorithm"] == "dijkstra" and result["gap_pct"] == 0
    assert result["nodes"][0] == s and result["nodes"][-1] == t and result["hops"] == len(result["nodes"]) - 1
    assert result["path"][0] == pytest.approx(coords[s]) and result["path"][-1] == pytest.approx(coords[t])
    assert body["exact_cost"] == pytest.approx(result["cost"]) == pytest.approx(result["time_min"])  # default cost: minutes
    assert 0 <= result["delay_min"] <= result["time_min"] and result["distance_km"] > 0
    assert body["cost_weights"] == {"time": 1.0, "distance": 0.0, "congestion": 0.0}


def test_all_four_can_be_compared_and_none_beats_the_exact_answer():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    s, t = a_pair(view)

    body = post(graph_id, s, t, algorithms=["ga", "dijkstra", "qpso", "pso", "qpso"], n_particles=20, n_iterations=60).json()

    assert [r["algorithm"] for r in body["results"]] == ["ga", "dijkstra", "qpso", "pso"]  # asked-for order, duplicate dropped
    for r in body["results"]:
        assert r["nodes"][0] == s and r["nodes"][-1] == t
        assert r["gap_pct"] >= -1e-9 and r["cost"] >= body["exact_cost"] - 1e-9
    exact = next(r for r in body["results"] if r["algorithm"] == "dijkstra")
    assert exact["gap_pct"] == 0 and exact["iterations"] == 1
    qpso = next(r for r in body["results"] if r["algorithm"] == "qpso")
    assert len(qpso["convergence"]) == 60 + 1 and all(b <= a + 1e-9 for a, b in zip(qpso["convergence"], qpso["convergence"][1:]))


def test_a_search_is_repeatable_for_a_seed():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    s, t = a_pair(view)
    same = dict(algorithms=["qpso"], n_particles=15, n_iterations=30, seed=9)
    a, b = (post(graph_id, s, t, **same).json()["results"][0] for _ in range(2))
    assert a["nodes"] == b["nodes"] and a["convergence"] == b["convergence"]


def test_the_cost_weights_change_the_route_and_are_what_is_minimized():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    s, t = a_pair(view, min_hops=6)
    weights = {"time": 0.2, "distance": 0.5, "congestion": 0.3}

    quickest = post(graph_id, s, t).json()["results"][0]
    shortest = post(graph_id, s, t, cost_weights={"time": 0, "distance": 1}).json()["results"][0]
    blended = post(graph_id, s, t, cost_weights=weights).json()

    assert shortest["distance_km"] <= quickest["distance_km"] + 1e-9 and quickest["time_min"] <= shortest["time_min"] + 1e-9
    (result,) = blended["results"]
    assert blended["cost_weights"] == weights
    assert result["cost"] == pytest.approx(0.2 * result["time_min"] + 0.5 * result["distance_km"] + 0.3 * result["delay_min"])


def test_bad_requests_are_refused_with_a_reason():
    view = make_graph()
    graph_id = view["summary"]["graph_id"]
    s, t = a_pair(view)

    assert post("nope", s, t).status_code == 404
    assert post(graph_id, 99999, t).status_code == 422
    assert post(graph_id, s, 99999).status_code == 422
    same = post(graph_id, s, s)
    assert same.status_code == 422 and "different" in same.json()["detail"]
    assert post(graph_id, s, t, algorithms=[]).status_code == 422
    assert post(graph_id, s, t, algorithms=["annealing"]).status_code == 422
    assert post(graph_id, s, t, n_iterations=5).status_code == 422
    assert post(graph_id, s, t, cost_weights={"time": 0, "distance": 0, "congestion": 0}).status_code == 422


def test_a_place_that_cannot_be_reached_is_reported_not_crashed():
    g = TrafficGraph()
    for i, (lat, lon) in enumerate([(28.60, 77.20), (28.61, 77.21), (28.62, 77.22), (28.63, 77.23)]):
        g.add_node(i, lat=lat, lon=lon, pos=(i * 1.0, i * 1.0))
    for u, v in [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3)]:  # node 3 can be entered but never left
        g.add_edge(u, v, 1.0, 1.0)
    stored = get_store().add(g, "synthetic", "dead end", (28.6, 77.2))

    for algorithms in (["dijkstra"], ["qpso"]):
        response = post(stored.graph_id, 3, 0, algorithms=algorithms)
        assert response.status_code == 422 and "no route" in response.json()["detail"]
    assert post(stored.graph_id, 0, 3).status_code == 200  # the other way round it is fine
