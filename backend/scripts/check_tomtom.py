"""
Check that your TomTom API key works, using ONE Traffic Flow request (of the free 2,500 a day).

Reads TOMTOM_API_KEY from the environment or backend/.env, asks TomTom for the traffic on the road
nearest a point (default: MG Road, Bengaluru), and prints what came back. The key itself is never printed.

Usage (from backend/, with the venv active, internet needed):
    python scripts/check_tomtom.py
    python scripts/check_tomtom.py --point 28.6315,77.2167      # Connaught Place, New Delhi
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ENV_FILE, tomtom_api_key, tomtom_zoom  # noqa: E402
from app.data.tomtom import TomTomFlowProvider, TrafficProviderError  # noqa: E402

MG_ROAD = "12.9758,77.6068"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--point", default=MG_ROAD, help="lat,lon to query (default: MG Road, Bengaluru)")
    args = parser.parse_args()

    key = tomtom_api_key()
    if not key:
        print(f"No key found. Add a line  TOMTOM_API_KEY=your_key  to {ENV_FILE}  (copy .env.example), then run this again.")
        return 1

    try:
        lat, lon = (float(part) for part in args.point.split(","))
    except ValueError:
        print("--point must look like 12.9758,77.6068")
        return 1

    provider = TomTomFlowProvider(key, zoom=tomtom_zoom())
    try:
        sample = provider.fetch_point(lat, lon)
    except TrafficProviderError as exc:
        print(f"FAILED: {exc}")
        return 1

    if sample is None:
        print(f"The key works, but TomTom has no traffic reading for a road near {lat}, {lon}. Try another --point.")
        return 0

    print(f"OK: TomTom answered for the road nearest {lat}, {lon}")
    print(f"  current speed    {sample.current_kph:.0f} km/h")
    print(f"  free-flow speed  {sample.free_flow_kph:.0f} km/h")
    print(f"  slowdown         x{sample.slowdown:.2f}  (1.00 = no congestion)")
    print(f"  confidence       {sample.confidence:.2f}")
    print(f"  road closed      {'yes' if sample.road_closure else 'no'}")
    print(f"  segment shape    {len(sample.shape)} points")
    print("Live traffic is ready: in the app, use the Real city tab and press 'Fetch live traffic'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
