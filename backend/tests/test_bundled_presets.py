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


# ---- loading the same city again is cheap, and never shares state ------------------------------------------------------------


def test_a_second_load_does_not_parse_the_map_again(no_internet, monkeypatch):
    import osmnx

    lat, lon = PRESETS[2]["lat"], PRESETS[2]["lon"]
    first = load_city_graph(lat, lon, radius_m=RADIUS)

    def refuse(*args, **kwargs):
        raise AssertionError("parsed the map file again")

    monkeypatch.setattr(osmnx, "load_graphml", refuse)
    second = load_city_graph(lat, lon, radius_m=RADIUS)

    assert second.node_count == first.node_count and second.edge_count == first.edge_count
    u, v = next(iter(first.graph.edges()))
    assert second.graph[u][v]["distance_km"] == first.graph[u][v]["distance_km"]
    assert "shape" in second.graph[u][v] or "shape" not in first.graph[u][v]


def test_each_load_is_its_own_copy(no_internet):
    lat, lon = PRESETS[0]["lat"], PRESETS[0]["lon"]
    a = load_city_graph(lat, lon, radius_m=RADIUS)
    u, v = next(iter(a.graph.edges()))
    a.update_congestion(u, v, 4.0)

    b = load_city_graph(lat, lon, radius_m=RADIUS)

    assert b.graph[u][v]["congestion_factor"] != 4.0 and b is not a


def test_the_warm_up_loads_all_four_presets_offline(no_internet):
    osm_loader.warm_presets()

    cached = {p.name for p in osm_loader.CACHE_DIR.glob("*.graphml")}
    assert len(cached) == len(PRESETS)
