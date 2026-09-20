"""The recorded MG Road traffic ships with the repo, so a fresh container or cloud instance can replay real traffic offline."""

import shutil
from pathlib import Path

import pytest

from app.data.osm_loader import city_key, load_city_graph
from app.services import snapshots
from app.services.graph_store import GraphStore

REAL_DIR = Path(__file__).resolve().parents[1] / "data" / "recorded_traffic"
MG_ROAD = (12.9758, 77.6068, 1200)


@pytest.fixture
def mg_road(monkeypatch, tmp_path):
    monkeypatch.setattr(snapshots, "BUNDLED_DIR", REAL_DIR)  # conftest points it at an empty folder; use the real one here
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "my_recordings")
    lat, lon, radius = MG_ROAD
    graph = load_city_graph(lat, lon, radius_m=radius)  # from the bundled preset, no internet
    return GraphStore().add(graph, "city", "MG Road", (lat, lon), key=city_key(lat, lon, radius, "drive"))


def test_the_bundled_recording_is_listed_for_its_map_and_only_that_map(mg_road):
    listed = snapshots.list_snapshots(mg_road)

    assert len(listed) == 1 and listed[0].provider == "TomTom" and listed[0].roads_measured == 541
    assert listed[0].captured_at.startswith("2026-09-19")
    other = GraphStore().add(mg_road.graph, "city", "another map", (0.0, 0.0), key="osm_1.0000_1.0000_1200_drive")
    assert snapshots.list_snapshots(other) == []


def test_replaying_it_is_labelled_recorded_and_changes_the_congestion(mg_road):
    before = sum(d["congestion_factor"] for _, _, d in mg_road.graph.graph.edges(data=True)) / mg_road.graph.edge_count

    info = snapshots.apply_snapshot(mg_road, snapshots.list_snapshots(mg_road)[0].id)

    after = sum(d["congestion_factor"] for _, _, d in mg_road.graph.graph.edges(data=True)) / mg_road.graph.edge_count
    assert info.kind == "recorded" and info.provider == "TomTom" and info.captured_at.startswith("2026-09-19")
    assert after > before * 1.2  # the evening traffic is far heavier than free flow


def test_a_copy_in_the_users_own_folder_is_listed_once(mg_road, tmp_path):
    mine = tmp_path / "my_recordings"
    mine.mkdir()
    for path in REAL_DIR.glob("*.json"):
        shutil.copy(path, mine / path.name)

    assert len(snapshots.list_snapshots(mg_road)) == 1


def test_the_users_own_recordings_are_listed_beside_the_bundled_one(mg_road, tmp_path):
    mine = tmp_path / "my_recordings"
    mine.mkdir()
    (mine / f"{mg_road.key}__20300101T000000Z.json").write_text(
        '{"version": 1, "graph_key": "%s", "provider": "TomTom", "captured_at": "2030-01-01T00:00:00+00:00", "roads_measured": 1, "roads_total": 2, "factors": []}' % mg_road.key,
        encoding="utf-8",
    )

    ids = [s.id for s in snapshots.list_snapshots(mg_road)]

    assert len(ids) == 2 and ids[0].endswith("20300101T000000Z")  # newest first
    with pytest.raises(snapshots.SnapshotNotFound):
        snapshots.apply_snapshot(mg_road, "../../etc/passwd")
