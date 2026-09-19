import networkx as nx
import pytest
from shapely.geometry import LineString

from app.core.geo import lat_lon_from_km, local_km
from app.core.traffic import apply_random_traffic, apply_rush_hour, clear_traffic
from app.data.osm_loader import parse_speed_kph, to_traffic_graph
from app.data.synthetic_graph_generator import generate_synthetic_graph


def fake_osm_graph() -> nx.MultiDiGraph:
    """Shaped like an OSMnx result: x = lon, y = lat, edge length in metres."""
    g = nx.MultiDiGraph()
    for node, (lat, lon) in {1: (28.630, 77.210), 2: (28.631, 77.211), 3: (28.632, 77.212), 9: (28.640, 77.220)}.items():
        g.add_node(node, y=lat, x=lon)
    g.add_edge(1, 2, length=500.0, highway="residential")
    g.add_edge(2, 1, length=500.0, highway="residential")
    g.add_edge(2, 3, length=1000.0, highway="primary", maxspeed="50")
    g.add_edge(3, 2, length=1000.0, highway="primary", maxspeed="50")
    g.add_edge(1, 2, length=520.0, highway="motorway")  # parallel road, longer but much faster: should win
    g.add_edge(2, 2, length=10.0, highway="service")  # self-loop: ignored
    g.add_edge(3, 9, length=800.0, highway="tertiary")  # node 9 is a one-way dead end: not strongly connected
    curve = LineString([(77.211, 28.631), (77.2115, 28.6315), (77.212, 28.632)])  # (lon, lat) like shapely/OSM
    g.add_edge(2, 3, length=1000.0, highway="primary", maxspeed="50", geometry=curve)
    return g


def test_to_traffic_graph_keeps_the_strongly_connected_core_and_quickest_parallel_edge():
    graph = to_traffic_graph(fake_osm_graph(), 28.631, 77.211)

    assert set(graph.graph.nodes) == {1, 2, 3}  # dead-end node 9 dropped
    assert not graph.graph.has_edge(2, 2)
    assert graph.graph[1][2]["distance_km"] == pytest.approx(0.52)  # the motorway wins on time
    assert graph.graph[1][2]["base_travel_time_min"] == pytest.approx(0.52 / 70.0 * 60.0)
    assert graph.graph[2][3]["base_travel_time_min"] == pytest.approx(1.0 / 50.0 * 60.0)  # maxspeed tag used


def test_to_traffic_graph_georeferences_nodes_and_keeps_road_shapes():
    graph = to_traffic_graph(fake_osm_graph(), 28.631, 77.211)
    attrs = graph.graph.nodes[2]

    assert (attrs["lat"], attrs["lon"]) == pytest.approx((28.631, 77.211))
    assert attrs["pos"] == pytest.approx((0.0, 0.0), abs=1e-9)  # node 2 sits at the chosen centre
    shape = graph.graph[2][3]["shape"]
    assert shape[0] == pytest.approx((28.631, 77.211)) and shape[-1] == pytest.approx((28.632, 77.212))  # (lat, lon)
    assert "shape" not in graph.graph[1][2]


@pytest.mark.parametrize(
    "maxspeed, highway, expected",
    [
        ("50", "residential", 50.0),
        ("30 mph", "residential", 30 * 1.609344),
        (["40", "60"], "primary", 40.0),
        (None, "residential", 22.0),
        ("walk", "primary", 40.0),  # unparseable -> road-class default
        (None, ["secondary", "tertiary"], 35.0),
        (None, "cycleway", 25.0),  # unknown class -> fallback
    ],
)
def test_parse_speed_kph(maxspeed, highway, expected):
    assert parse_speed_kph(maxspeed, highway) == pytest.approx(expected)


def test_local_km_and_its_inverse_agree():
    east, north = local_km(28.64, 77.22, 28.63, 77.21)
    assert east > 0 and north > 0
    assert lat_lon_from_km(east, north, 28.63, 77.21) == pytest.approx((28.64, 77.22))


def test_clear_random_and_rush_hour_traffic():
    graph = generate_synthetic_graph(n_nodes=60, seed=2)

    clear_traffic(graph)
    assert all(d["congestion_factor"] == 1.0 and d["weight"] == d["base_travel_time_min"] for _, _, d in graph.graph.edges(data=True))

    apply_random_traffic(graph, low=1.2, high=1.4, seed=1)
    assert all(1.2 <= d["congestion_factor"] <= 1.4 for _, _, d in graph.graph.edges(data=True))

    apply_rush_hour(graph, peak=3.0, seed=1)
    factors = [d["congestion_factor"] for _, _, d in graph.graph.edges(data=True)]
    assert max(factors) > 2.0 and min(factors) >= 0.5
    assert all(d["weight"] == pytest.approx(d["base_travel_time_min"] * d["congestion_factor"]) for _, _, d in graph.graph.edges(data=True))


def test_traffic_argument_validation():
    graph = generate_synthetic_graph(n_nodes=20, seed=2)
    with pytest.raises(ValueError):
        apply_random_traffic(graph, low=2.0, high=1.0)
    with pytest.raises(ValueError):
        apply_rush_hour(graph, peak=0.5)

    bare = nx.DiGraph()
    bare.add_edge(0, 1)
    from app.core.graph_model import TrafficGraph

    no_positions = TrafficGraph()
    no_positions.add_edge("a", "b", 1.0, 1.0)
    with pytest.raises(ValueError):
        apply_rush_hour(no_positions)
