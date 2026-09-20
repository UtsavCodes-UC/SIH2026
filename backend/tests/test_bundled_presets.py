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
        load_city_graph(PRESETS[0]["lat"], PRESETS[0]["lon"], radius_m=2500)  # bigger than any bundled map


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


def test_the_warm_up_loads_every_bundled_map_offline_default_radius_first(no_internet):
    osm_loader.warm_presets()

    cached = {p.name for p in osm_loader.CACHE_DIR.glob("*.graphml")}
    assert len(cached) == 2 * len(PRESETS)  # each preset at 1200 m and at the bigger size other radii are cut from
    assert all(any(f"_{p['lat']:.4f}_{p['lon']:.4f}_{r}_" in name for name in cached) for p in PRESETS for r in (1200, 2000))


# ---- changing the radius of a preset place needs no internet -----------------------------------------------------------------


@pytest.mark.parametrize("radius", [500, 900, 1300, 1700])
@pytest.mark.parametrize("preset", PRESETS, ids=[p["name"] for p in PRESETS])
def test_a_smaller_radius_is_cut_from_the_bundled_map_offline(preset, radius, no_internet):
    import networkx as nx

    graph = load_city_graph(preset["lat"], preset["lon"], radius_m=radius)
    bigger = load_city_graph(preset["lat"], preset["lon"], radius_m=2000)

    half = radius / 1000.0
    assert 50 < graph.node_count < bigger.node_count
    assert all(abs(a["pos"][0]) <= half and abs(a["pos"][1]) <= half for _, a in graph.graph.nodes(data=True))
    assert nx.is_strongly_connected(graph.graph)  # every stop can reach every other
    u, v, data = next(iter(graph.graph.edges(data=True)))
    assert {"distance_km", "base_travel_time_min", "congestion_factor"} <= set(data)


def test_bigger_radii_are_nested(no_internet):
    small, medium, large = (load_city_graph(PRESETS[2]["lat"], PRESETS[2]["lon"], radius_m=r) for r in (600, 1300, 1900))

    assert small.node_count < medium.node_count < large.node_count
    assert set(small.graph.nodes) <= set(medium.graph.nodes) <= set(large.graph.nodes)


def test_the_cut_matches_a_real_download_of_that_radius(no_internet):
    # A real osmnx download of MG Road at 1300 m (2026-09-21) gave 1045 intersections and 2389 roads (arcs).
    cut = load_city_graph(PRESETS[2]["lat"], PRESETS[2]["lon"], radius_m=1300)

    assert cut.node_count == pytest.approx(1045, rel=0.08)
    assert cut.edge_count == pytest.approx(2389, rel=0.08)


def test_a_radius_beyond_the_bundled_maps_still_downloads(no_internet):
    with pytest.raises(osm_loader.CityLoadError, match="could not fetch"):
        load_city_graph(PRESETS[0]["lat"], PRESETS[0]["lon"], radius_m=2600)


def test_a_place_that_is_not_a_preset_is_never_cut_from_a_preset(no_internet):
    with pytest.raises(osm_loader.CityLoadError):
        load_city_graph(28.7041, 77.1025, radius_m=800)  # Delhi, but not the preset's centre


# ---- when the download fails, say why, and try the other servers ---------------------------------------------------------------


def test_every_server_is_tried_and_named_and_osmnx_s_confusing_error_is_translated(monkeypatch):
    import osmnx

    seen = []

    def fail(*args, **kwargs):
        endpoint = osmnx.settings.overpass_endpoint
        seen.append(endpoint)
        raise UnboundLocalError("cannot access local variable 'response' where it is not associated with a value")

    monkeypatch.setattr(osmnx, "graph_from_point", fail)

    with pytest.raises(osm_loader.CityLoadError) as info:
        load_city_graph(28.7041, 77.1025, radius_m=800)

    assert seen == list(osm_loader.OVERPASS_ENDPOINTS)
    message = str(info.value)
    assert "cannot access local variable" not in message
    assert message.count("could not connect") == len(osm_loader.OVERPASS_ENDPOINTS)
    assert all(endpoint.split("/")[2] in message for endpoint in osm_loader.OVERPASS_ENDPOINTS)


def test_a_later_server_is_used_when_the_first_ones_fail(monkeypatch, tmp_path):
    import networkx as nx
    import osmnx

    calls = []

    def flaky(*args, **kwargs):
        calls.append(osmnx.settings.overpass_endpoint)
        if len(calls) < 3:
            raise ConnectionError("refused")
        g = nx.MultiDiGraph()
        g.add_node(1, x=77.10, y=28.70)
        g.add_node(2, x=77.11, y=28.70)
        g.add_edge(1, 2, length=100.0, highway="residential")
        g.add_edge(2, 1, length=100.0, highway="residential")
        return g

    def fake_save(graph, path):
        path.write_text("saved", encoding="utf-8")

    monkeypatch.setattr(osmnx, "graph_from_point", flaky)
    monkeypatch.setattr(osmnx, "save_graphml", fake_save)

    graph = load_city_graph(28.7041, 77.1025, radius_m=800)

    assert len(calls) == 3 and calls[2] == osm_loader.OVERPASS_ENDPOINTS[2]
    assert graph.node_count == 2
