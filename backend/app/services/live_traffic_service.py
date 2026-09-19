"""Live traffic for a stored graph: fetch readings, write them onto the roads, remember where they came from."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from app.config import live_min_interval_sec, live_sample_count, tomtom_api_key, tomtom_max_qps, tomtom_zoom
from app.core.live_traffic import apply_samples, build_road_index, choose_sample_roads, export_factors, import_factors
from app.data.tomtom import TomTomFlowProvider, TrafficProviderError
from app.schemas.graph import TrafficInfo
from app.services.graph_store import LiveReading, StoredGraph


class TrafficUnavailableError(RuntimeError):
    """No live-traffic provider is configured (no API key)."""


class TrafficRequestError(ValueError):
    """The request makes no sense for this graph or snapshot."""


def get_flow_provider() -> TomTomFlowProvider | None:
    """The configured provider, or None when there is no API key. A FastAPI dependency, so tests swap it out."""
    key = tomtom_api_key()
    return TomTomFlowProvider(key, zoom=tomtom_zoom(), max_qps=tomtom_max_qps()) if key else None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def apply_live_traffic(stored: StoredGraph, provider: TomTomFlowProvider | None) -> TrafficInfo:
    if stored.source != "city":
        raise TrafficRequestError(
            "Live traffic is only available for real-city networks: the synthetic map's roads are not real streets."
        )

    cached = stored.live_cache
    if cached is not None and time.monotonic() - cached.taken_at < live_min_interval_sec():
        import_factors(stored.graph, cached.factors)  # a recent reading: don't spend more of the free quota
        stored.traffic = cached.info.model_copy(update={"cached": True})
        return stored.traffic

    if provider is None:
        raise TrafficUnavailableError(
            "Live traffic needs a TomTom API key. Add TOMTOM_API_KEY=... to backend/.env (see .env.example) "
            "and try again; no restart is needed."
        )

    index = build_road_index(stored.graph, stored.center)
    roads = choose_sample_roads(index, live_sample_count())
    points = [(float(index.mid_latlon[i][0]), float(index.mid_latlon[i][1])) for i in roads]
    samples = [s for s in provider.fetch(points) if s is not None]
    if not samples:
        raise TrafficProviderError(
            f"{provider.name} returned no traffic readings for this area (no roads near the {len(points)} sampled points)."
        )

    update = apply_samples(stored.graph, stored.center, samples, index)
    info = TrafficInfo(
        kind="live",
        label=provider.name,
        provider=provider.name,
        captured_at=utc_now_iso(),
        roads_measured=update.roads_measured,
        roads_total=update.roads_total,
    )
    stored.traffic = info
    stored.live_cache = LiveReading(time.monotonic(), export_factors(stored.graph), info)
    return info
