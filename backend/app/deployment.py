"""Where this server runs. A free demo host (Render) has about a tenth of a CPU and its live map downloads from OpenStreetMap do not finish
in time (a test download of a small area there had not answered after 290 seconds), so only the maps that ship with the app can be
loaded. This module says whether we are on such a host, so the API can refuse at once instead of timing out after minutes, and the
interface can explain that it is the hosting that limits the map, not the project."""

from __future__ import annotations

import os

HOSTED_MAX_RADIUS_M = 2000  # the bundled preset maps ship up to this radius; anything bigger needs a live download

LIMIT_MESSAGE = (
    f"This free demo server can only load the four ready-made places, up to {HOSTED_MAX_RADIUS_M} m radius. Any other place, or a bigger map, "
    "has to be downloaded live from OpenStreetMap, which takes longer than the free host allows, so the request times out. This is a limit "
    "of the hosting, not of the project: on a normal computer (localhost or Docker) any place in the world works, up to 4000 m."
)


def is_hosted_demo() -> bool:
    """True on a free demo host. Render sets RENDER=true by itself; HOSTED_DEMO=1/0 forces the answer on any other host."""
    forced = os.environ.get("HOSTED_DEMO")
    if forced is not None:
        return forced.strip().lower() in ("1", "true", "yes")
    return bool(os.environ.get("RENDER"))


def deployment_info() -> dict:
    hosted = is_hosted_demo()
    return {
        "hosted": hosted,
        "max_radius_m": HOSTED_MAX_RADIUS_M if hosted else None,
        "presets_only": hosted,
        "limit_note": LIMIT_MESSAGE if hosted else None,
    }
