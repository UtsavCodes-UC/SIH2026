"""The four preset places ship with the repo, so they load without the internet and without a warmed cache."""

import pytest

from app.data import osm_loader
from app.data.osm_loader import PRESET_DIR, PRESETS, _cache_path, load_city_graph

RADIUS = 1200  # the UI's default


@pytest.fixture
def no_internet(monkeypatch):
    import osmnx

    def refuse(*args, **kwargs):
        raise AssertionError("tried to download from OpenStreetMap")

    monkeypatch.setattr(osmnx, "graph_from_point", refuse)


@pytest.mark.parametrize("preset", PRESETS, ids=[p["name"] for p in PRESETS])
def test_each_preset_is_bundled_and_loads_offline(preset, no_internet):
    bundled = PRESET_DIR / _cache_path(preset["lat"], preset["lon"], RADIUS, "drive").name
    assert bundled.is_file(), f"{bundled.name} is missing from backend/data/presets"
    assert not (osmnx_cache := _cache_path(preset["lat"], preset["lon"], RADIUS, "drive")).exists()  # the test cache starts empty

    graph = load_city_graph(preset["lat"], preset["lon"], radius_m=RADIUS)

    assert graph.node_count > 200 and graph.edge_count > graph.node_count
    assert osmnx_cache.is_file()  # copied into the cache, so later loads and recorded traffic use the ordinary path


def test_other_places_still_go_to_the_internet(no_internet):
    with pytest.raises(osm_loader.CityLoadError, match="could not fetch"):
        load_city_graph(PRESETS[0]["lat"], PRESETS[0]["lon"], radius_m=1500)  # not a bundled radius


def test_a_refresh_bypasses_the_bundled_copy(no_internet):
    with pytest.raises(osm_loader.CityLoadError, match="could not fetch"):
        load_city_graph(PRESETS[0]["lat"], PRESETS[0]["lon"], radius_m=RADIUS, refresh=True)
