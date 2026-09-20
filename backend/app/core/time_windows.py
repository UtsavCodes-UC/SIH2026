"""
Soft time windows: a stop may only be served between an earliest and a latest time.

The model, in minutes from the moment every van leaves the depot (time 0):

    arrival     a_j  = departure from the previous stop + the quickest driving time between the two
    service     starts at  b_j = max(a_j, earliest_j)    a van that arrives early WAITS until the window opens
    lateness    late_j = max(0, a_j - latest_j)          a van that arrives after the window closes still serves the
                                                         stop, and the minutes it is late are penalized
    departure   d_j  = b_j + service time (the same for every stop; 0 by default)

Waiting costs nothing directly (it is not driving) but pushes every later stop back, which is how it shows up in the
cost. A stop with no window is always on time. The objective is the driving cost (core/cost_model.py) plus
`time_window_penalty` x (total lateness in minutes), on top of the capacity penalty:

    C = sum of route costs  +  P_capacity * overload  +  P_window * total lateness

The times are REAL minutes even when the cost weights blend in distance or congestion: the clock runs on the roads
actually driven (`RoutingProblem.minutes`). The return leg to the depot is not subject to a window.

What supports windows and what does not (see BENCHMARKS.md, Finding 17): QPSO, PSO, GA and nearest neighbour evaluate them
through `RoutingProblem.cost`. The linear-time optimal Split decoder, the exact Held-Karp solver and the route search
assume that a route's cost does not depend on when it starts, which windows break, so they refuse or step aside.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class TimeWindow:
    earliest: float
    latest: float

    def __post_init__(self):
        if not (math.isfinite(self.earliest) and math.isfinite(self.latest)):
            raise ValueError("a time window needs finite times")
        if self.earliest < 0 or self.latest < self.earliest:
            raise ValueError(f"a time window needs 0 <= earliest <= latest, got [{self.earliest}, {self.latest}]")


@dataclass(frozen=True)
class StopTiming:
    stop: object
    arrival_min: float
    start_min: float  # when service begins: arrival, or the opening of the window if the van arrived early
    wait_min: float
    late_min: float
    earliest: float | None
    latest: float | None


@dataclass(frozen=True)
class RouteSchedule:
    stops: list[StopTiming]
    end_min: float  # back at the depot, waiting and service time included

    @property
    def late_min(self) -> float:
        return sum(s.late_min for s in self.stops)

    @property
    def wait_min(self) -> float:
        return sum(s.wait_min for s in self.stops)


def schedule_route(
    route: Sequence,
    minutes: Mapping,
    windows: Mapping | None,
    service_time_min: float = 0.0,
) -> RouteSchedule:
    """Arrival, waiting and lateness at every stop of a depot-delimited route [depot, s_1, ..., s_k, depot], driving with
    the `minutes` table (minutes[u][v] = real driving minutes)."""
    clock = 0.0
    timings: list[StopTiming] = []
    for u, v in zip(route[:-2], route[1:-1]):
        arrival = clock + minutes[u][v]
        window = windows.get(v) if windows else None
        start = arrival if window is None else max(arrival, window.earliest)
        timings.append(
            StopTiming(
                stop=v,
                arrival_min=arrival,
                start_min=start,
                wait_min=start - arrival,
                late_min=0.0 if window is None else max(0.0, arrival - window.latest),
                earliest=None if window is None else window.earliest,
                latest=None if window is None else window.latest,
            )
        )
        clock = start + service_time_min
    end = clock + minutes[route[-2]][route[-1]] if len(route) > 2 else 0.0
    return RouteSchedule(timings, end)


def random_time_windows(
    stops: Sequence,
    quickest_from_depot: Mapping,
    rng: random.Random,
    horizon_min: float = 80.0,
    width_range: tuple[float, float] = (30.0, 60.0),
) -> dict:
    """Demo windows: each stop's window is centred a random 0..horizon minutes after the quickest a van could reach it
    from the depot, and is 30-60 minutes wide. Windows like these are usually satisfiable but bind, so ordering matters."""
    windows = {}
    for stop in stops:
        centre = quickest_from_depot[stop] + rng.uniform(0.0, horizon_min)
        width = rng.uniform(*width_range)
        windows[stop] = TimeWindow(round(max(0.0, centre - width / 2), 1), round(centre + width / 2, 1))
    return windows
