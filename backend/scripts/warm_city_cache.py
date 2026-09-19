"""
Pre-download the preset cities into backend/data/cache/ so a demo never depends on the
Overpass API being reachable. Each first-time download takes 1-2 minutes; loads after
that are instant. Skips places that are already cached.

Usage (from backend/, with the venv active, internet needed):
    python scripts/warm_city_cache.py
    python scripts/warm_city_cache.py --radius 1500 --refresh
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.osm_loader import PRESETS, CityLoadError, load_city_graph  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--radius", type=int, default=1200, help="metres around each preset's centre (the UI default is 1200)")
    parser.add_argument("--refresh", action="store_true", help="download again even if cached")
    args = parser.parse_args()

    for preset in PRESETS:
        t0 = time.perf_counter()
        try:
            graph = load_city_graph(preset["lat"], preset["lon"], radius_m=args.radius, refresh=args.refresh)
        except CityLoadError as exc:
            print(f"FAILED  {preset['name']}: {exc}")
            continue
        print(f"ok      {preset['name']}: {graph.node_count} nodes, {graph.edge_count} edges ({time.perf_counter() - t0:.0f}s)")


if __name__ == "__main__":
    main()
