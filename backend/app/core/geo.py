"""Small-area conversions between lat/lon degrees and local kilometres."""

from __future__ import annotations

import math

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON_AT_EQUATOR = 111.320


def local_km(lat: float, lon: float, centre_lat: float, centre_lon: float) -> tuple[float, float]:
    """Tangent-plane offset (east km, north km) of a point from the centre."""
    east = (lon - centre_lon) * KM_PER_DEG_LON_AT_EQUATOR * math.cos(math.radians(centre_lat))
    north = (lat - centre_lat) * KM_PER_DEG_LAT
    return east, north


def lat_lon_from_km(east_km: float, north_km: float, centre_lat: float, centre_lon: float) -> tuple[float, float]:
    """Inverse of `local_km`."""
    lat = centre_lat + north_km / KM_PER_DEG_LAT
    lon = centre_lon + east_km / (KM_PER_DEG_LON_AT_EQUATOR * math.cos(math.radians(centre_lat)))
    return lat, lon
