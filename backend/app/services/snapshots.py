"""
Recorded traffic: save a live reading to disk and replay it later.

A snapshot stores only what the routing needs (a congestion factor per road, plus where and when
it was taken), so a demo can show real recorded traffic without the network or an API key, always
labelled "recorded" and never as live. Snapshots are tied to the exact downloaded map (`graph_key`)
they were taken on. They are git-ignored by default: check the provider's terms before sharing them.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core.live_traffic import export_factors, import_factors
from app.schemas.graph import SnapshotInfo, TrafficInfo
from app.services.graph_store import StoredGraph
from app.services.live_traffic_service import TrafficRequestError

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "traffic_snapshots"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class SnapshotNotFound(KeyError):
    """No such snapshot."""


def _path_for(snapshot_id: str) -> Path:
    if not _SAFE_ID.match(snapshot_id):
        raise SnapshotNotFound(snapshot_id)
    path = (SNAPSHOT_DIR / f"{snapshot_id}.json").resolve()
    if path.parent != SNAPSHOT_DIR.resolve():
        raise SnapshotNotFound(snapshot_id)
    return path


def _info(snapshot_id: str, payload: dict) -> SnapshotInfo:
    return SnapshotInfo(
        id=snapshot_id,
        provider=payload.get("provider"),
        captured_at=payload.get("captured_at"),
        roads_measured=payload.get("roads_measured"),
        roads_total=payload.get("roads_total", 0),
    )


def save_snapshot(stored: StoredGraph) -> SnapshotInfo:
    traffic = stored.traffic
    if stored.key is None or traffic is None or traffic.kind not in ("live", "recorded") or traffic.captured_at is None:
        raise TrafficRequestError(
            "Only real traffic can be saved as a snapshot. Fetch live traffic first "
            "(simulated traffic is never presented as recorded)."
        )
    stamp = datetime.fromisoformat(traffic.captured_at).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_id = f"{stored.key}__{stamp}"
    payload = {
        "version": 1,
        "graph_key": stored.key,
        "provider": traffic.provider,
        "captured_at": traffic.captured_at,
        "roads_measured": traffic.roads_measured,
        "roads_total": traffic.roads_total,
        "factors": export_factors(stored.graph),
    }
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    _path_for(snapshot_id).write_text(json.dumps(payload), encoding="utf-8")
    return _info(snapshot_id, payload)


def list_snapshots(stored: StoredGraph) -> list[SnapshotInfo]:
    if stored.key is None or not SNAPSHOT_DIR.is_dir():
        return []
    found = []
    for path in SNAPSHOT_DIR.glob(f"{stored.key}__*.json"):
        try:
            found.append(_info(path.stem, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue  # unreadable or corrupt file: skip it rather than fail the listing
    return sorted(found, key=lambda s: s.captured_at or "", reverse=True)


def apply_snapshot(stored: StoredGraph, snapshot_id: str) -> TrafficInfo:
    path = _path_for(snapshot_id)
    if not path.is_file():
        raise SnapshotNotFound(snapshot_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("graph_key") != stored.key:
        raise TrafficRequestError("This snapshot was recorded on a different map, so it can't be replayed here.")
    import_factors(stored.graph, payload["factors"])
    stored.traffic = TrafficInfo(
        kind="recorded",
        label=payload.get("provider") or "recorded",
        provider=payload.get("provider"),
        captured_at=payload.get("captured_at"),
        roads_measured=payload.get("roads_measured"),
        roads_total=payload.get("roads_total", 0),
    )
    return stored.traffic
