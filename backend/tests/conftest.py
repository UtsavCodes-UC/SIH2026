import pytest

from app.data import osm_loader


@pytest.fixture(autouse=True)
def isolated_map_cache(tmp_path, monkeypatch):
    """No test may read or write the real downloaded maps and remembered places in backend/data/cache."""
    monkeypatch.setattr(osm_loader, "CACHE_DIR", tmp_path / "map_cache")
