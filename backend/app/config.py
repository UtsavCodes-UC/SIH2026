"""Settings from environment variables, with a tiny reader for backend/.env (no extra dependency).

The .env file is read on every lookup, so adding an API key to it takes effect without
restarting the backend. It is git-ignored; copy `.env.example` to `.env` and fill it in.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def get_setting(name: str, default: str | None = None) -> str | None:
    """Environment variable first, then backend/.env; empty values count as unset."""
    return os.environ.get(name) or _read_env_file(ENV_FILE).get(name) or default


def _number(name: str, default: float) -> float:
    try:
        return float(get_setting(name) or default)
    except ValueError:
        return default


def tomtom_api_key() -> str | None:
    return get_setting("TOMTOM_API_KEY")


def tomtom_zoom() -> int:
    return int(_number("TOMTOM_FLOW_ZOOM", 15))


def tomtom_max_qps() -> float:
    return _number("TOMTOM_MAX_QPS", 5.0)


def live_sample_count() -> int:
    return int(_number("LIVE_TRAFFIC_SAMPLES", 80))


def live_min_interval_sec() -> float:
    """Re-use the last live reading for this long instead of spending more of the free daily quota."""
    return _number("LIVE_TRAFFIC_MIN_INTERVAL_SEC", 300.0)
