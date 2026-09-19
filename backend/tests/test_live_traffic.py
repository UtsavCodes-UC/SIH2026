import json
import ssl
import urllib.error

import pytest

from app import config
from app.data import http as http_module
from app.core.graph_model import TrafficGraph
from app.core.live_traffic import (
    FlowSample,
    apply_samples,
    build_road_index,
    choose_sample_roads,
    export_factors,
    import_factors,
)
from app.data.tomtom import TomTomFlowProvider, TrafficProviderError
from app.schemas.graph import TrafficInfo
from app.services import live_traffic_service as live_service
from app.services import snapshots
from app.services.graph_store import GraphStore
from app.services.live_traffic_service import TrafficRequestError, TrafficUnavailableError, apply_live_traffic

CENTRE = (12.9700, 77.6000)


def line_graph(n_nodes: int = 10, highways: list[str] | None = None) -> TrafficGraph:
    """A straight street of n_nodes intersections about 108 m apart (0.001 degrees of longitude)."""
    g = TrafficGraph()
    for i in range(n_nodes):
        g.add_node(i, lat=CENTRE[0], lon=CENTRE[1] + 0.001 * i, pos=(0.0, 0.0))
    for i in range(n_nodes - 1):
        for a, b in ((i, i + 1), (i + 1, i)):
            g.add_edge(a, b, 0.108, 0.5)
            g.graph[a][b]["highway"] = (highways[i] if highways else "primary")
    return g


def factor(g: TrafficGraph, road: int) -> float:
    return g.graph[road][road + 1]["congestion_factor"]


# ---- settings -----------------------------------------------------------------


def test_env_file_is_read_and_the_environment_takes_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# a comment\nTOMTOM_API_KEY="abc123"\nLIVE_TRAFFIC_SAMPLES=42\nEMPTY=\n', encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env)
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    monkeypatch.delenv("LIVE_TRAFFIC_SAMPLES", raising=False)

    assert config.tomtom_api_key() == "abc123"
    assert config.live_sample_count() == 42
    assert config.get_setting("EMPTY") is None  # empty counts as unset

    monkeypatch.setenv("TOMTOM_API_KEY", "from-environment")
    assert config.tomtom_api_key() == "from-environment"

    monkeypatch.delenv("TOMTOM_API_KEY")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    assert config.tomtom_api_key() is None
    assert config.live_sample_count() == 80  # default


# ---- readings -> slowdown --------------------------------------------------------


def test_slowdown_is_a_ratio_of_free_flow_to_current_speed_and_is_clamped():
    assert FlowSample(0, 0, current_kph=20, free_flow_kph=40).slowdown == pytest.approx(2.0)
    assert FlowSample(0, 0, current_kph=50, free_flow_kph=40).slowdown == 1.0  # never faster than free flow
    assert FlowSample(0, 0, current_kph=2, free_flow_kph=40).slowdown == 6.0  # capped
    assert FlowSample(0, 0, current_kph=0, free_flow_kph=40).slowdown == 6.0
    assert FlowSample(0, 0, current_kph=30, free_flow_kph=40, road_closure=True).slowdown == 6.0


# ---- choosing where to measure ---------------------------------------------------


def test_sampling_is_spread_out_deterministic_and_relaxes_when_the_area_is_small():
    index = build_road_index(line_graph(10), CENTRE)  # 9 roads, 108 m apart

    assert choose_sample_roads(index, 3, min_spacing_km=0.2) == [0, 2, 4]
    assert choose_sample_roads(index, 3, min_spacing_km=0.2) == [0, 2, 4]
    everything = choose_sample_roads(index, 9, min_spacing_km=0.2)  # only 5 fit at 200 m; the rest need relaxing
    assert sorted(everything) == list(range(9))


def test_sampling_prefers_major_roads():
    highways = ["primary" if i % 2 == 0 else "residential" for i in range(9)]
    index = build_road_index(line_graph(10, highways), CENTRE)

    assert all(i % 2 == 0 for i in choose_sample_roads(index, 3, min_spacing_km=0.05))


# ---- writing readings onto the graph -----------------------------------------------


def test_a_reading_covers_every_road_along_its_segment_and_spreads_to_neighbours():
    g = line_graph(10)
    long_segment = FlowSample(
        lat=CENTRE[0], lon=CENTRE[1] + 0.0025, current_kph=10, free_flow_kph=40,
        shape=[(CENTRE[0], CENTRE[1] + 0.001), (CENTRE[0], CENTRE[1] + 0.004)],  # runs from node 1 to node 4
    )
    free_road = FlowSample(lat=CENTRE[0], lon=CENTRE[1] + 0.0085, current_kph=40, free_flow_kph=40)  # road 8

    update = apply_samples(g, CENTRE, [long_segment, free_road])

    assert (update.roads_measured, update.roads_total) == (4, 9)  # roads 1, 2, 3 (along the segment) and 8
    assert [factor(g, r) for r in (1, 2, 3)] == pytest.approx([4.0, 4.0, 4.0])
    assert factor(g, 8) == pytest.approx(1.0)
    # unmeasured roads lean toward whichever measured roads are nearest: 4.0 near the jam, 1.0 near the free road
    assert 4.0 > factor(g, 5) > factor(g, 6) > factor(g, 7) > 1.0
    assert factor(g, 0) > 1.0 and factor(g, 4) > 1.0
    for road in range(9):  # both directions of a road carry the same factor
        assert g.graph[road][road + 1]["congestion_factor"] == g.graph[road + 1][road]["congestion_factor"]
    assert g.graph[1][2]["weight"] == pytest.approx(0.5 * 4.0)  # travel time follows the congestion factor


def test_a_road_closure_and_unmatched_readings():
    g = line_graph(6)
    closure = FlowSample(lat=CENTRE[0], lon=CENTRE[1] + 0.0025, current_kph=30, free_flow_kph=30, road_closure=True)
    nowhere = FlowSample(lat=13.5, lon=78.5, current_kph=5, free_flow_kph=40)  # far from every road: no match

    update = apply_samples(g, CENTRE, [closure, nowhere])

    assert update.roads_measured == 1
    assert factor(g, 2) == 6.0


def test_no_readings_leaves_every_road_at_free_flow():
    g = line_graph(6)
    update = apply_samples(g, CENTRE, [])
    assert update.roads_measured == 0 and all(factor(g, r) == 1.0 for r in range(5))


def test_factors_export_and_import_roundtrip_and_ignore_unknown_edges():
    g = line_graph(5)
    apply_samples(g, CENTRE, [FlowSample(CENTRE[0], CENTRE[1] + 0.0015, current_kph=20, free_flow_kph=40)])
    saved = export_factors(g)

    fresh = line_graph(5)
    matched = import_factors(fresh, saved + [[99, 100, 3.0]])

    assert matched == len(saved)
    assert [factor(fresh, r) for r in range(4)] == [factor(g, r) for r in range(4)]


# ---- the TomTom adapter (network faked) --------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.tomtom.com/x?key=SECRET", code, "error", {}, None)


FLOW_PAYLOAD = {
    "flowSegmentData": {
        "frc": "FRC3", "currentSpeed": 18, "freeFlowSpeed": 40, "currentTravelTime": 80, "freeFlowTravelTime": 36,
        "confidence": 0.9, "roadClosure": False,
        "coordinates": {"coordinate": [{"latitude": 12.97, "longitude": 77.60}, {"latitude": 12.971, "longitude": 77.601}]},
    }
}


def make_provider(responses, **kwargs):
    """A provider whose 'network' pops from `responses` (a payload dict, or an exception to raise)."""
    calls, sleeps = [], []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        item = responses.pop(0) if isinstance(responses, list) else responses
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    provider = TomTomFlowProvider("SECRET", urlopen=fake_urlopen, sleep=sleeps.append, clock=lambda: 0.0, **kwargs)
    return provider, calls, sleeps


def test_tomtom_reading_is_parsed_and_the_request_matches_the_documented_api():
    provider, calls, _ = make_provider([FLOW_PAYLOAD], zoom=14)

    sample = provider.fetch_point(12.97, 77.60)

    assert (sample.current_kph, sample.free_flow_kph, sample.confidence, sample.road_closure) == (18.0, 40.0, 0.9, False)
    assert sample.shape == [(12.97, 77.60), (12.971, 77.601)]
    url = calls[0]
    assert url.startswith("https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/14/json?")
    assert "point=12.970000%2C77.600000" in url and "unit=kmph" in url and "key=SECRET" in url


def test_the_real_connection_always_verifies_certificates():
    # A certificate error must never be "fixed" by switching verification off: the API key travels over this connection.
    context = http_module.tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_no_road_near_the_point_is_a_missing_reading_not_an_error():
    provider, _, _ = make_provider([http_error(400)])
    assert provider.fetch_point(12.97, 77.60) is None
    provider, _, _ = make_provider([{"unexpected": "shape"}])
    assert provider.fetch_point(12.97, 77.60) is None


def test_a_rejected_key_stops_everything_and_never_leaks_the_key():
    provider, calls, _ = make_provider(http_error(403))

    with pytest.raises(TrafficProviderError) as caught:
        provider.fetch([(12.97, 77.60)] * 8)

    message = str(caught.value)
    assert "403" in message and "Traffic API" in message and "whitelisting" in message
    assert "SECRET" not in message
    assert len(calls) <= 4  # fail fast: remaining requests are skipped once the key is known to be bad


def test_rate_limiting_backs_off_and_then_recovers_or_gives_up():
    provider, _, sleeps = make_provider([http_error(429), http_error(429), FLOW_PAYLOAD])
    assert provider.fetch_point(12.97, 77.60) is not None
    assert 1.0 in sleeps and 2.0 in sleeps  # backed off between attempts

    provider, _, _ = make_provider(http_error(429))
    with pytest.raises(TrafficProviderError, match="rate limit"):
        provider.fetch_point(12.97, 77.60)


def test_network_failures_are_reported_without_the_key():
    provider, calls, _ = make_provider(urllib.error.URLError("connection refused for key SECRET"))

    with pytest.raises(TrafficProviderError) as caught:
        provider.fetch_point(12.97, 77.60)

    assert "SECRET" not in str(caught.value) and "could not get a reading" in str(caught.value)
    assert len(calls) == 3  # retried twice before giving up


def test_requests_are_paced_to_the_configured_rate():
    provider, _, sleeps = make_provider(FLOW_PAYLOAD, max_qps=5.0)  # one request per 0.2 s
    for _ in range(3):
        provider.fetch_point(12.97, 77.60)
    assert sleeps == pytest.approx([0.2, 0.4])  # the clock is frozen, so each call waits for its own slot


# ---- fetching live traffic for a stored graph -------------------------------------------


class FakeProvider:
    name = "TomTom"

    def __init__(self, current_kph=20.0, free_flow_kph=40.0, answer=True):
        self.calls, self._current, self._free, self._answer = 0, current_kph, free_flow_kph, answer

    def fetch(self, points):
        self.calls += 1
        return [FlowSample(la, lo, self._current, self._free) if self._answer else None for la, lo in points]


def city_stored(store: GraphStore | None = None):
    store = store or GraphStore()
    return store.add(line_graph(30), "city", "test street", CENTRE, key="osm_test_1200_drive")


def test_live_traffic_is_written_onto_the_roads_and_labelled_live():
    stored = city_stored()
    provider = FakeProvider(current_kph=20, free_flow_kph=40)

    info = apply_live_traffic(stored, provider)

    assert info.kind == "live" and info.provider == "TomTom" and info.captured_at
    assert 0 < info.roads_measured <= info.roads_total == 29
    assert provider.calls == 1
    assert factor(stored.graph, 5) == pytest.approx(2.0)  # every reading was a 2x slowdown, so every road is 2.0
    assert stored.traffic == info


def test_a_recent_reading_is_reused_to_save_the_free_quota(monkeypatch):
    stored = city_stored()
    provider = FakeProvider()
    apply_live_traffic(stored, provider)
    stored.graph.update_congestion(5, 6, 1.0)  # something changed the traffic since (e.g. a simulated mode)

    again = apply_live_traffic(stored, provider)

    assert provider.calls == 1 and again.cached and factor(stored.graph, 5) == pytest.approx(2.0)

    monkeypatch.setattr(live_service, "live_min_interval_sec", lambda: 0.0)  # the interval has passed
    assert not apply_live_traffic(stored, provider).cached and provider.calls == 2


def test_live_traffic_refuses_synthetic_maps_and_a_missing_key_and_empty_answers():
    synthetic = GraphStore().add(line_graph(5), "synthetic", "fake", CENTRE)
    with pytest.raises(TrafficRequestError, match="real-city"):
        apply_live_traffic(synthetic, FakeProvider())

    with pytest.raises(TrafficUnavailableError, match="TOMTOM_API_KEY"):
        apply_live_traffic(city_stored(), None)

    with pytest.raises(TrafficProviderError, match="no traffic readings"):
        apply_live_traffic(city_stored(), FakeProvider(answer=False))


# ---- recorded snapshots ---------------------------------------------------------------------


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snaps")
    return tmp_path / "snaps"


def test_only_real_traffic_can_be_saved(snapshot_dir):
    stored = city_stored()  # a fresh city is at free flow, not a real reading
    with pytest.raises(TrafficRequestError, match="Only real traffic"):
        snapshots.save_snapshot(stored)


def test_a_snapshot_records_and_replays_real_traffic_labelled_recorded(snapshot_dir):
    stored = city_stored()
    apply_live_traffic(stored, FakeProvider(current_kph=10, free_flow_kph=40))  # 4x slowdown everywhere
    saved = snapshots.save_snapshot(stored)

    assert (snapshot_dir / f"{saved.id}.json").is_file() and saved.roads_total == 29
    assert [s.id for s in snapshots.list_snapshots(stored)] == [saved.id]

    stored.graph.update_congestion(5, 6, 1.0)
    info = snapshots.apply_snapshot(stored, saved.id)

    assert factor(stored.graph, 5) == pytest.approx(4.0)
    assert info.kind == "recorded" and info.captured_at == saved.captured_at and info.provider == "TomTom"
    assert stored.traffic == info


def test_snapshots_are_tied_to_their_map_and_ids_cannot_escape_the_folder(snapshot_dir):
    stored = city_stored()
    apply_live_traffic(stored, FakeProvider())
    saved = snapshots.save_snapshot(stored)

    other_map = GraphStore().add(line_graph(30), "city", "elsewhere", CENTRE, key="osm_other_1200_drive")
    with pytest.raises(TrafficRequestError, match="different map"):
        snapshots.apply_snapshot(other_map, saved.id)
    assert snapshots.list_snapshots(other_map) == []

    for bad in ("missing", "../../etc/passwd", "..\\secret", "a/b", ""):
        with pytest.raises(snapshots.SnapshotNotFound):
            snapshots.apply_snapshot(stored, bad)
