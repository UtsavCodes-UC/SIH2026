import pytest

from app.data import osm_loader


@pytest.fixture(autouse=True)
def no_bundled_recordings(tmp_path, monkeypatch):
    """Tests decide which recorded traffic exists: the recordings that ship with the repo stay out of them."""
    from app.services import snapshots

    monkeypatch.setattr(snapshots, "BUNDLED_DIR", tmp_path / "bundled_recordings")


@pytest.fixture(autouse=True)
def isolated_map_cache(tmp_path, monkeypatch):
    """No test may read or write the real downloaded maps and remembered places in backend/data/cache."""
    monkeypatch.setattr(osm_loader, "CACHE_DIR", tmp_path / "map_cache")
