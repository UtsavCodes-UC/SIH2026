"""On a free demo host only the ready-made places load, up to a capped radius, and the API says why; anywhere else nothing changes."""

import pytest
from fastapi.testclient import TestClient

from app.deployment import HOSTED_MAX_RADIUS_M, is_hosted_demo
from app.main import app

client = TestClient(app)
MG_ROAD = {"place": "MG Road", "lat": 12.9758, "lon": 77.6068}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("HOSTED_DEMO", raising=False)


def test_local_by_default():
    assert not is_hosted_demo()
    assert client.get("/api/config").json() == {"hosted": False, "max_radius_m": None, "presets_only": False, "limit_note": None}


def test_render_sets_the_flag_by_itself(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    info = client.get("/api/config").json()
    assert info["hosted"] is True and info["presets_only"] is True and info["max_radius_m"] == HOSTED_MAX_RADIUS_M
    assert "not of the project" in info["limit_note"]


@pytest.mark.parametrize("value, expected", [("1", True), ("true", True), ("0", False), ("no", False)])
def test_hosted_demo_variable_overrides_render(monkeypatch, value, expected):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("HOSTED_DEMO", value)
    assert is_hosted_demo() is expected


@pytest.mark.parametrize(
    "body",
    [
        {**MG_ROAD, "radius_m": HOSTED_MAX_RADIUS_M + 100},  # a preset, but bigger than the bundled maps
        {"place": "Pune", "lat": 18.5204, "lon": 73.8567, "radius_m": 600},  # not a ready-made place
        {"place": "Pune", "radius_m": 600},  # a typed name would need a live lookup and download
    ],
)
def test_hosted_refuses_what_needs_a_live_download_at_once(monkeypatch, body):
    monkeypatch.setenv("HOSTED_DEMO", "1")
    monkeypatch.setattr("app.api.graph.load_city_graph", lambda *a, **k: pytest.fail("must not try to download"))
    monkeypatch.setattr("app.api.graph.geocode", lambda *a, **k: pytest.fail("must not look the place up"))
    response = client.post("/api/graph/city", json=body)
    assert response.status_code == 422
    assert "hosting, not of the project" in response.json()["detail"]


def test_hosted_still_loads_a_preset_within_the_limit(monkeypatch):
    monkeypatch.setenv("HOSTED_DEMO", "1")
    response = client.post("/api/graph/city", json={**MG_ROAD, "radius_m": 1300})
    assert response.status_code == 200
    assert response.json()["summary"]["node_count"] > 500


def test_local_is_not_capped(monkeypatch):
    # not hosted: a big radius or another place goes on to the loader (which would download it)
    monkeypatch.setattr("app.api.graph.load_city_graph", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("would download")))
    for body in ({**MG_ROAD, "radius_m": 3000}, {"place": "Pune", "lat": 18.5204, "lon": 73.8567, "radius_m": 600}):
        with pytest.raises(RuntimeError, match="would download"):
            client.post("/api/graph/city", json=body)
