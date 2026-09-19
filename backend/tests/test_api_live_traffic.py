import pytest
from fastapi.testclient import TestClient

from app import config
from app.core.live_traffic import FlowSample
from app.data.synthetic_graph_generator import generate_synthetic_graph, georeference
from app.data.tomtom import TrafficProviderError
from app.main import app
from app.services import snapshots
from app.services.graph_store import get_store
from app.services.live_traffic_service import get_flow_provider

client = TestClient(app)
FAST = {"n_particles": 10, "n_iterations": 30}


class FakeProvider:
    name = "TomTom"

    def __init__(self, current_kph=20.0, free_flow_kph=40.0, error=None):
        self.calls, self._current, self._free, self._error = 0, current_kph, free_flow_kph, error

    def fetch(self, points):
        self.calls += 1
        if self._error:
            raise self._error
        return [FlowSample(lat, lon, self._current, self._free) for lat, lon in points]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    get_store().clear()
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")  # never read a real backend/.env in tests
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)

    def fake_loader(lat, lon, radius_m=1500, network_type="drive", refresh=False):
        graph = generate_synthetic_graph(n_nodes=40, area_size_km=2, seed=5)
        georeference(graph, lat, lon)
        for u, v, data in graph.graph.edges(data=True):
            data["highway"] = "primary" if (u + v) % 2 == 0 else "residential"
        return graph

    monkeypatch.setattr("app.api.graph.load_city_graph", fake_loader)
    yield
    app.dependency_overrides.clear()
    get_store().clear()


def use_provider(provider):
    app.dependency_overrides[get_flow_provider] = lambda: provider
    return provider


def make_city() -> dict:
    response = client.post("/api/graph/city", json={"lat": 12.9758, "lon": 77.6068, "radius_m": 1200, "place": "MG Road"})
    assert response.status_code == 200, response.text
    return response.json()["summary"]


def set_traffic(graph_id: str, mode: str, **extra):
    return client.post(f"/api/graph/{graph_id}/congestion", json={"mode": mode, **extra})


# ---- status and labelling -------------------------------------------------------------------


def test_status_reports_whether_a_key_is_configured_without_revealing_it(tmp_path, monkeypatch):
    status = client.get("/api/traffic/status").json()
    assert status["live_available"] is False and status["provider"] == "TomTom"

    (tmp_path / "with.env").write_text("TOMTOM_API_KEY=very-secret-key\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "with.env")
    response = client.get("/api/traffic/status")
    assert response.json()["live_available"] is True
    assert "very-secret-key" not in response.text


def test_every_graph_reports_where_its_traffic_came_from():
    synthetic = client.post("/api/graph/synthetic", json={"n_nodes": 30, "seed": 1}).json()["summary"]
    assert synthetic["traffic"]["kind"] == "simulated" and synthetic["traffic"]["label"] == "random"

    city = make_city()
    assert city["traffic"]["kind"] == "free_flow" and city["traffic"]["roads_total"] > 0

    assert set_traffic(city["graph_id"], "rush_hour").json()["summary"]["traffic"]["label"] == "rush hour"
    assert set_traffic(city["graph_id"], "random").json()["summary"]["traffic"]["kind"] == "simulated"
    assert set_traffic(city["graph_id"], "clear").json()["summary"]["traffic"]["kind"] == "free_flow"


# ---- live ---------------------------------------------------------------------------------------


def test_live_traffic_updates_the_map_and_is_labelled_live():
    city = make_city()
    provider = use_provider(FakeProvider(current_kph=10, free_flow_kph=40))
    set_traffic(city["graph_id"], "clear")

    view = set_traffic(city["graph_id"], "live").json()

    traffic = view["summary"]["traffic"]
    assert traffic["kind"] == "live" and traffic["provider"] == "TomTom" and traffic["captured_at"]
    assert 0 < traffic["roads_measured"] <= traffic["roads_total"] and provider.calls == 1
    assert view["summary"]["mean_congestion"] == pytest.approx(4.0)  # every reading was a 4x slowdown
    assert min(e[2] for e in view["edges"]) == pytest.approx(4.0)


def test_repeat_live_requests_reuse_the_last_reading():
    city = make_city()
    provider = use_provider(FakeProvider())

    first = set_traffic(city["graph_id"], "live").json()["summary"]["traffic"]
    second = set_traffic(city["graph_id"], "live").json()["summary"]["traffic"]

    assert provider.calls == 1 and first["cached"] is False and second["cached"] is True


def test_plans_report_the_traffic_they_were_computed_under():
    city = make_city()
    use_provider(FakeProvider())
    set_traffic(city["graph_id"], "live")

    plan = client.post("/api/optimize", json={"graph_id": city["graph_id"], "n_stops": 6, **FAST}).json()
    bench = client.post("/api/benchmark", json={"graph_id": city["graph_id"], "n_stops": 5, "n_vehicles": 1, **FAST}).json()

    assert plan["traffic"]["kind"] == "live" and bench["traffic"]["kind"] == "live"


def test_live_traffic_changes_the_route_times():
    city = make_city()
    set_traffic(city["graph_id"], "clear")
    free = client.post("/api/optimize", json={"graph_id": city["graph_id"], "n_stops": 8, "algorithm": "nearest_neighbor"}).json()
    problem = free["problem"]

    use_provider(FakeProvider(current_kph=10, free_flow_kph=40))
    set_traffic(city["graph_id"], "live")
    live = client.post(
        "/api/optimize",
        json={"graph_id": city["graph_id"], "algorithm": "nearest_neighbor", "depot": problem["depot"], "stops": problem["stops"],
              "demands": problem["demands"], "n_vehicles": problem["n_vehicles"]},
    ).json()

    assert live["total_time_min"] == pytest.approx(4.0 * free["total_time_min"], rel=1e-6)  # uniform 4x slowdown


def test_live_traffic_is_refused_without_a_key_on_synthetic_maps_and_when_the_provider_fails():
    synthetic = client.post("/api/graph/synthetic", json={"n_nodes": 30, "seed": 1}).json()["summary"]
    use_provider(FakeProvider())
    response = set_traffic(synthetic["graph_id"], "live")
    assert response.status_code == 422 and "real-city" in response.json()["detail"]

    city = make_city()
    app.dependency_overrides.clear()  # no key configured
    response = set_traffic(city["graph_id"], "live")
    assert response.status_code == 503 and "TOMTOM_API_KEY" in response.json()["detail"]

    use_provider(FakeProvider(error=TrafficProviderError("TomTom rejected the API key (HTTP 403).")))
    response = set_traffic(city["graph_id"], "live")
    assert response.status_code == 502 and "403" in response.json()["detail"]


# ---- snapshots --------------------------------------------------------------------------------------


def test_a_live_reading_can_be_recorded_and_replayed_without_the_provider():
    city = make_city()
    use_provider(FakeProvider(current_kph=10, free_flow_kph=40))
    set_traffic(city["graph_id"], "live")

    saved = client.post(f"/api/graph/{city['graph_id']}/traffic/snapshots")
    assert saved.status_code == 200, saved.text
    snapshot_id = saved.json()["id"]
    assert [s["id"] for s in client.get(f"/api/graph/{city['graph_id']}/traffic/snapshots").json()] == [snapshot_id]

    app.dependency_overrides.clear()  # offline demo: no key, no provider
    set_traffic(city["graph_id"], "clear")
    replay = set_traffic(city["graph_id"], "snapshot", snapshot_id=snapshot_id).json()

    assert replay["summary"]["traffic"]["kind"] == "recorded"
    assert replay["summary"]["traffic"]["captured_at"] == saved.json()["captured_at"]
    assert replay["summary"]["mean_congestion"] == pytest.approx(4.0)


def test_simulated_traffic_cannot_be_saved_as_a_snapshot_and_bad_snapshots_are_rejected():
    city = make_city()
    set_traffic(city["graph_id"], "rush_hour")
    response = client.post(f"/api/graph/{city['graph_id']}/traffic/snapshots")
    assert response.status_code == 422 and "Only real traffic" in response.json()["detail"]

    assert set_traffic(city["graph_id"], "snapshot", snapshot_id="nope").status_code == 404
    assert set_traffic(city["graph_id"], "snapshot", snapshot_id="../../etc/passwd").status_code == 404
    assert set_traffic(city["graph_id"], "snapshot").status_code == 422  # snapshot_id is required
