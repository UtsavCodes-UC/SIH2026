from app.core.graph_model import TrafficGraph


def test_travel_time_and_congestion_update():
    g = TrafficGraph()
    g.add_edge("A", "B", distance_km=10, base_travel_time_min=15, congestion_factor=1.0)

    assert g.travel_time("A", "B") == 15
    assert g.graph["A"]["B"]["weight"] == 15

    g.update_congestion("A", "B", 2.0)

    assert g.travel_time("A", "B") == 30
    assert g.graph["A"]["B"]["weight"] == 30


def test_shortest_path_prefers_lower_weight_route():
    g = TrafficGraph()
    g.add_edge("A", "B", 5, 5)
    g.add_edge("B", "C", 5, 5)
    g.add_edge("A", "C", 5, 20)

    assert g.shortest_path("A", "C") == ["A", "B", "C"]
    assert g.shortest_path_time("A", "C") == 10


def test_all_pairs_shortest_time():
    g = TrafficGraph()
    g.add_edge("A", "B", 5, 5)
    g.add_edge("B", "C", 5, 5)

    result = g.all_pairs_shortest_time(["A", "C"])
    assert result["A"]["C"] == 10
    assert "A" not in result["C"]  # directed graph: no path back from C to A


def test_to_dict_from_dict_roundtrip():
    g = TrafficGraph()
    g.add_edge("A", "B", 5, 5, 1.5)
    payload = g.to_dict()

    restored = TrafficGraph.from_dict(payload)
    assert restored.travel_time("A", "B") == 7.5
    assert restored.node_count == 2
    assert restored.edge_count == 1
