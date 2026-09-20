"""
What "cheap" means for a route: a weighted blend of travel time, distance and congestion.

Every road segment (arc) a has a free-flow time tau (minutes), a length (km) and a congestion factor gamma. Its
current travel time is tau * gamma. The blend the optimizer minimizes is

    cost(a) = w_time * tau * gamma  +  w_distance * length  +  w_congestion * tau * max(0, gamma - 1)

- time        minutes spent driving the arc, congestion included
- distance    kilometres driven
- congestion  the minutes LOST to congestion on the arc: how much longer it takes than in free flow (0 on a free road)

Legs between stops are shortest paths under this cost, so a plan can prefer a slightly longer road that avoids a jam
when the congestion weight is high. The default, w_time = 1 and nothing else, is plain travel time and reproduces every
earlier result exactly. All three terms are non-negative, so Dijkstra applies and leg costs still obey the triangle
inequality.

`path_metrics` reports the three quantities separately for any path, so a plan can be described in real minutes,
kilometres and minutes of delay whatever weights it was optimized for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CostWeights:
    time: float = 1.0
    distance: float = 0.0
    congestion: float = 0.0

    def __post_init__(self):
        for name in ("time", "distance", "congestion"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"the {name} weight must be a non-negative number")
        if self.time + self.distance + self.congestion <= 0:
            raise ValueError("at least one weight must be positive")

    @property
    def is_default(self) -> bool:
        """Plain travel time with unit weight: the cost the graph already keeps as each arc's `weight`."""
        return self.time == 1.0 and self.distance == 0.0 and self.congestion == 0.0

    def arc_cost(self, edge: Mapping) -> float:
        """The blended cost of one arc, from its attribute dictionary."""
        tau, gamma = edge["base_travel_time_min"], edge["congestion_factor"]
        return self.time * tau * gamma + self.distance * edge["distance_km"] + self.congestion * tau * max(0.0, gamma - 1.0)


@dataclass(frozen=True)
class PathMetrics:
    time_min: float  # driving time, congestion included
    distance_km: float
    delay_min: float  # minutes lost to congestion compared with free flow


def path_metrics(graph, path: Sequence) -> PathMetrics:
    """Real minutes, kilometres and congestion delay along a node path of a TrafficGraph."""
    g = graph.graph
    time = distance = delay = 0.0
    for a, b in zip(path, path[1:]):
        edge = g[a][b]
        tau, gamma = edge["base_travel_time_min"], edge["congestion_factor"]
        time += tau * gamma
        distance += edge["distance_km"]
        delay += tau * max(0.0, gamma - 1.0)
    return PathMetrics(time, distance, delay)
