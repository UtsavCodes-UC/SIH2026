"""Graph endpoints: create a synthetic or real-city network, read it back, change its traffic."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.traffic import apply_random_traffic, apply_rush_hour, clear_traffic
from app.data.osm_loader import PRESETS, geocode, load_city_graph
from app.data.synthetic_graph_generator import generate_synthetic_graph, georeference
from app.schemas.graph import (
    CityGraphRequest,
    CongestionRequest,
    GraphView,
    Preset,
    SyntheticGraphRequest,
)
from app.services.graph_store import GraphStore, StoredGraph, get_store
from app.services.views import graph_view

router = APIRouter(prefix="/graph", tags=["graph"])


def lookup(store: GraphStore, graph_id: str) -> StoredGraph:
    try:
        return store.get(graph_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown graph_id {graph_id!r} (it may have been evicted; create it again)")


@router.get("/presets", response_model=list[Preset])
def presets() -> list[dict]:
    """Ready-made real places the UI can load with one click."""
    return PRESETS


@router.post("/synthetic", response_model=GraphView)
def create_synthetic(req: SyntheticGraphRequest, store: GraphStore = Depends(get_store)) -> GraphView:
    graph = generate_synthetic_graph(
        n_nodes=req.n_nodes, k_nearest=req.k_nearest, area_size_km=req.area_size_km, seed=req.seed
    )
    georeference(graph, req.center_lat, req.center_lon)
    label = f"Synthetic network: {req.n_nodes} nodes over {req.area_size_km:g} km (seed {req.seed})"
    return graph_view(store.add(graph, "synthetic", label, (req.center_lat, req.center_lon)))


@router.post("/city", response_model=GraphView)
def create_city(req: CityGraphRequest, store: GraphStore = Depends(get_store)) -> GraphView:
    """Real road network from OpenStreetMap (first load needs internet; later loads use the disk cache)."""
    if req.lat is not None and req.lon is not None:
        lat, lon = req.lat, req.lon
    else:
        lat, lon = geocode(req.place)  # CityLoadError -> 503
    graph = load_city_graph(lat, lon, radius_m=req.radius_m, refresh=req.refresh)
    name = req.place or f"({lat:.4f}, {lon:.4f})"
    return graph_view(store.add(graph, "city", f"{name}, {req.radius_m} m radius", (lat, lon)))


@router.get("/{graph_id}", response_model=GraphView)
def get_graph(graph_id: str, store: GraphStore = Depends(get_store)) -> GraphView:
    stored = lookup(store, graph_id)
    with stored.lock:
        return graph_view(stored)


@router.post("/{graph_id}/congestion", response_model=GraphView)
def set_congestion(graph_id: str, req: CongestionRequest, store: GraphStore = Depends(get_store)) -> GraphView:
    """Change the traffic on every road (the dynamic weight update); the next solve reacts to it."""
    stored = lookup(store, graph_id)
    with stored.lock:
        if req.mode == "random":
            apply_random_traffic(stored.graph, req.low, req.high, req.seed)
        elif req.mode == "rush_hour":
            apply_rush_hour(stored.graph, peak=req.peak, seed=req.seed)
        else:
            clear_traffic(stored.graph)
        return graph_view(stored)
