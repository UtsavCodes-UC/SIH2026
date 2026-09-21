"""Graph endpoints: create a synthetic or real-city network, read it back, change its traffic."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.live_traffic import count_roads
from app.core.traffic import apply_random_traffic, apply_rush_hour, clear_traffic
from app.data.osm_loader import PRESETS, UnusablePlaceError, city_key, geocode, is_preset, load_city_graph, remember_place
from app.data.place_search import PhotonPlaceSearch, get_place_search, suggest
from app.data.synthetic_graph_generator import generate_synthetic_graph, georeference
from app.data.tomtom import TomTomFlowProvider
from app.deployment import HOSTED_MAX_RADIUS_M, LIMIT_MESSAGE, is_hosted_demo
from app.schemas.graph import (
    CityGraphRequest,
    ClosureRequest,
    CongestionRequest,
    GraphView,
    PlaceSearchResponse,
    Preset,
    SyntheticGraphRequest,
    TrafficInfo,
)
from app.services.closures import ClosureError, set_closures
from app.services.graph_store import GraphStore, StoredGraph, get_store
from app.services.live_traffic_service import apply_live_traffic, get_flow_provider
from app.services.snapshots import SnapshotNotFound, apply_snapshot
from app.services.views import graph_view

router = APIRouter(prefix="/graph", tags=["graph"])

MIN_CITY_NODES = 10  # fewer drivable intersections than this can't host a delivery problem


def lookup(store: GraphStore, graph_id: str) -> StoredGraph:
    try:
        return store.get(graph_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown graph_id {graph_id!r} (it may have been evicted; create it again)")


@router.get("/presets", response_model=list[Preset])
def presets() -> list[dict]:
    """Ready-made real places the UI can load with one click."""
    return PRESETS


@router.get("/places", response_model=PlaceSearchResponse)
def search_places(
    q: str = Query("", max_length=100, description="what the user has typed so far"),
    lat: float | None = Query(None, ge=-90, le=90, description="with lon: prefer results near this point"),
    lon: float | None = Query(None, ge=-180, le=180),
    online: PhotonPlaceSearch | None = Depends(get_place_search),
) -> PlaceSearchResponse:
    """Place-name suggestions for a search-as-you-type box: known places first, then Photon (OpenStreetMap data)."""
    suggestions, note = suggest(q, online, near=(lat, lon) if lat is not None and lon is not None else None)
    return PlaceSearchResponse(suggestions=[asdict(s) for s in suggestions], note=note)


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
    if is_hosted_demo() and (
        req.radius_m > HOSTED_MAX_RADIUS_M or req.lat is None or req.lon is None or not is_preset(req.lat, req.lon)
    ):
        raise UnusablePlaceError(LIMIT_MESSAGE)  # a live download cannot finish there: say so at once instead of timing out after minutes
    geocoded = req.lat is None or req.lon is None
    if geocoded:
        lat, lon = geocode(req.place)  # unknown name -> 422, lookup failure -> 503
    else:
        lat, lon = req.lat, req.lon
    graph = load_city_graph(lat, lon, radius_m=req.radius_m, refresh=req.refresh)
    if graph.node_count < MIN_CITY_NODES:
        raise UnusablePlaceError(
            f"Found the place ({lat:.4f}, {lon:.4f}) but there are only {graph.node_count} drivable intersections within "
            f"{req.radius_m} m. Try a larger radius or a more specific place."
        )
    if req.place and not geocoded and not is_preset(lat, lon):
        remember_place(req.place, lat, lon)  # a picked suggestion: suggest it again later, even offline
    # A geocoded place shows where the search put the map, so a wrong "Springfield" is easy to spot.
    name = f"{req.place} ({lat:.4f}, {lon:.4f})" if geocoded else req.place or f"({lat:.4f}, {lon:.4f})"
    stored = store.add(graph, "city", f"{name}, {req.radius_m} m radius", (lat, lon), key=city_key(lat, lon, req.radius_m))
    return graph_view(stored)


@router.get("/{graph_id}", response_model=GraphView)
def get_graph(graph_id: str, store: GraphStore = Depends(get_store)) -> GraphView:
    stored = lookup(store, graph_id)
    with stored.lock:
        return graph_view(stored)


@router.put("/{graph_id}/closures", response_model=GraphView)
def put_closures(graph_id: str, req: ClosureRequest, store: GraphStore = Depends(get_store)) -> GraphView:
    """Block roads: the listed roads are closed, every other road is open. The next solve plans around them.

    A road is named by the two intersections it joins; a two-way road is closed in both directions. `roads: []`
    reopens everything. The view says which intersections the closures cut off from the rest of the network.
    """
    stored = lookup(store, graph_id)
    with stored.lock:
        try:
            set_closures(stored, req.roads)
        except ClosureError as error:
            raise HTTPException(status_code=422, detail=str(error))
        return graph_view(stored)


@router.post("/{graph_id}/congestion", response_model=GraphView)
def set_congestion(
    graph_id: str,
    req: CongestionRequest,
    store: GraphStore = Depends(get_store),
    provider: TomTomFlowProvider | None = Depends(get_flow_provider),
) -> GraphView:
    """Change the traffic on every road (the dynamic weight update); the next solve reacts to it.

    Simulated modes (random, rush hour, clear) work on any network. `live` reads real traffic from the
    provider and `snapshot` replays a recording of it; both are for real-city networks only.
    """
    stored = lookup(store, graph_id)
    with stored.lock:
        roads = count_roads(stored.graph)
        if req.mode == "random":
            apply_random_traffic(stored.graph, req.low, req.high, req.seed)
            stored.traffic = TrafficInfo(kind="simulated", label="random", roads_total=roads)
        elif req.mode == "rush_hour":
            apply_rush_hour(stored.graph, peak=req.peak, seed=req.seed)
            stored.traffic = TrafficInfo(kind="simulated", label="rush hour", roads_total=roads)
        elif req.mode == "clear":
            clear_traffic(stored.graph)
            stored.traffic = TrafficInfo(kind="free_flow", label="free flow", roads_total=roads)
        elif req.mode == "live":
            apply_live_traffic(stored, provider)  # sets stored.traffic
        else:
            try:
                apply_snapshot(stored, req.snapshot_id)  # sets stored.traffic
            except SnapshotNotFound:
                raise HTTPException(status_code=404, detail=f"unknown snapshot {req.snapshot_id!r}")
        return graph_view(stored)
