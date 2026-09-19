"""Traffic-provider status and recorded snapshots."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.graph import lookup
from app.config import live_min_interval_sec, tomtom_api_key
from app.schemas.graph import SnapshotInfo, TrafficStatus
from app.services.graph_store import GraphStore, get_store
from app.services.snapshots import list_snapshots, save_snapshot

router = APIRouter(tags=["traffic"])


@router.get("/traffic/status", response_model=TrafficStatus)
def traffic_status() -> TrafficStatus:
    """Whether live traffic can be fetched (a key is configured). Never reveals the key itself."""
    return TrafficStatus(provider="TomTom", live_available=bool(tomtom_api_key()), min_interval_sec=live_min_interval_sec())


@router.get("/graph/{graph_id}/traffic/snapshots", response_model=list[SnapshotInfo])
def snapshots(graph_id: str, store: GraphStore = Depends(get_store)) -> list[SnapshotInfo]:
    """Recorded traffic available for this map, newest first."""
    return list_snapshots(lookup(store, graph_id))


@router.post("/graph/{graph_id}/traffic/snapshots", response_model=SnapshotInfo)
def record_snapshot(graph_id: str, store: GraphStore = Depends(get_store)) -> SnapshotInfo:
    """Save the current real (live or recorded) traffic so it can be replayed later, e.g. offline."""
    stored = lookup(store, graph_id)
    with stored.lock:
        return save_snapshot(stored)
