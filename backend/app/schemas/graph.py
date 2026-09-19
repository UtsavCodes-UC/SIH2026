from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SyntheticGraphRequest(BaseModel):
    n_nodes: int = Field(60, ge=10, le=600, description="number of intersections")
    area_size_km: float = Field(8.0, ge=1.0, le=100.0)
    k_nearest: int = Field(4, ge=2, le=8, description="roads per intersection (nearest neighbours)")
    seed: int | None = 1
    center_lat: float = Field(28.6139, ge=-90, le=90, description="where the synthetic network is placed on the map")
    center_lon: float = Field(77.2090, ge=-180, le=180)


class CityGraphRequest(BaseModel):
    place: str | None = Field(None, max_length=200, description="geocoded with Nominatim; or give lat/lon instead")
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    radius_m: int = Field(1500, ge=300, le=4000)
    refresh: bool = Field(False, description="ignore the on-disk cache and fetch again")

    @field_validator("place", mode="before")
    @classmethod
    def _blank_place_is_no_place(cls, value):
        if isinstance(value, str):
            value = " ".join(value.split())
            return value or None
        return value

    @model_validator(mode="after")
    def _needs_a_location(self) -> "CityGraphRequest":
        if self.place is None and (self.lat is None or self.lon is None):
            raise ValueError("give either `place` or both `lat` and `lon`")
        return self


class CongestionRequest(BaseModel):
    """`live` reads real traffic from the provider (real-city networks only); `snapshot` replays a
    recording made earlier from live data; the others are simulated."""

    mode: Literal["random", "rush_hour", "clear", "live", "snapshot"]
    seed: int | None = None
    low: float = Field(0.8, gt=0, le=10)  # random mode
    high: float = Field(2.5, gt=0, le=10)
    peak: float = Field(2.5, ge=1, le=10)  # rush-hour mode
    snapshot_id: str | None = None  # snapshot mode

    @model_validator(mode="after")
    def _check_mode_arguments(self) -> "CongestionRequest":
        if self.low > self.high:
            raise ValueError("`low` must not exceed `high`")
        if self.mode == "snapshot" and not self.snapshot_id:
            raise ValueError("`snapshot_id` is required for mode 'snapshot'")
        return self


class TrafficInfo(BaseModel):
    """Where the congestion currently on the graph came from. The UI must show this next to the map:
    simulated or recorded traffic is never to be presented as live."""

    kind: Literal["free_flow", "simulated", "live", "recorded"]
    label: str  # e.g. "random", "rush hour", "TomTom"
    provider: str | None = None
    captured_at: str | None = None  # ISO 8601, UTC; when a live/recorded reading was taken
    roads_measured: int | None = None  # roads with a real reading (the rest are estimated from neighbours)
    roads_total: int = 0
    cached: bool = False  # a recent live reading was reused instead of asking the provider again


class TrafficStatus(BaseModel):
    provider: str
    live_available: bool  # an API key is configured
    min_interval_sec: float


class SnapshotInfo(BaseModel):
    id: str
    provider: str | None
    captured_at: str | None
    roads_measured: int | None
    roads_total: int


class Preset(BaseModel):
    name: str
    lat: float
    lon: float


class GraphSummary(BaseModel):
    graph_id: str
    source: Literal["synthetic", "city"]
    label: str
    node_count: int
    edge_count: int
    center: tuple[float, float]
    bounds: tuple[tuple[float, float], tuple[float, float]]  # (south, west), (north, east)
    mean_congestion: float
    traffic: TrafficInfo


class GraphView(BaseModel):
    summary: GraphSummary
    # nodes: [id, lat, lon]; edges: [u, v, congestion] with one entry per road (the worse direction's congestion)
    nodes: list[list[float]]
    edges: list[list[float]]
