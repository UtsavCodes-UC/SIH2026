"""Turns an API problem description into a validated RouteRequest, filling in whatever
the caller left out (depot, stops, demands, fleet size) deterministically from the seed."""

from __future__ import annotations

import math
import random

import numpy as np

from app.core.cost_model import CostWeights
from app.core.time_windows import TimeWindow, random_time_windows
from app.core.vrp_formulation import RouteRequest
from app.schemas.solve import ProblemSpec
from app.services.graph_store import StoredGraph

DEMAND_RANGE = (5, 25)
TARGET_FLEET_UTILIZATION = 0.85


class InvalidProblemError(ValueError):
    """The requested depot/stops/demands don't make sense on this graph."""


def central_node(stored: StoredGraph):
    """The node nearest the centroid of all node positions: a natural default depot."""
    nodes = list(stored.graph.graph.nodes(data=True))
    coords = np.array([attrs["pos"] for _, attrs in nodes], dtype=float)
    nearest = int(np.argmin(np.linalg.norm(coords - coords.mean(axis=0), axis=1)))
    return nodes[nearest][0]


def resolve_problem(stored: StoredGraph, spec: ProblemSpec) -> RouteRequest:
    node_ids = list(stored.graph.graph.nodes)
    known = set(node_ids)
    rng = random.Random(spec.seed)

    depot = spec.depot if spec.depot is not None else central_node(stored)
    if depot not in known:
        raise InvalidProblemError(f"depot {depot} is not a node of this graph")

    reachable = stored.graph.mutually_reachable(depot)  # closed roads can cut places off

    if spec.stops:
        stops = list(spec.stops)
        if len(set(stops)) != len(stops):
            raise InvalidProblemError("stops contains duplicates")
        unknown = [s for s in stops if s not in known]
        if unknown:
            raise InvalidProblemError(f"stops not in this graph: {unknown[:5]}")
        if depot in stops:
            raise InvalidProblemError("the depot cannot also be a stop")
        cut_off = [s for s in stops if s not in reachable]
        if cut_off:
            cause = f"the {len(stored.closed)} closed road(s)" if stored.closed else "the road network's one-way streets"
            raise InvalidProblemError(
                f"{len(cut_off)} stop(s) are not reachable from the depot and back because of {cause}: {cut_off[:8]}. "
                "Reopen a road, move the depot, or pick other stops."
            )
    else:
        candidates = [n for n in node_ids if n != depot and n in reachable]
        if not candidates:
            raise InvalidProblemError("the graph has no nodes the depot can reach besides itself")
        stops = rng.sample(candidates, min(spec.n_stops, len(candidates)))

    if spec.demands is not None:
        missing = [s for s in stops if s not in spec.demands]
        if missing:
            raise InvalidProblemError(f"demands missing for stops: {missing[:5]}")
        if any(spec.demands[s] < 0 for s in stops):
            raise InvalidProblemError("demands must be non-negative")
        demands = {s: spec.demands[s] for s in stops}
    else:
        demands = {s: rng.randint(*DEMAND_RANGE) for s in stops}

    n_vehicles = spec.n_vehicles
    if n_vehicles is None:
        n_vehicles = max(1, math.ceil(sum(demands.values()) / (TARGET_FLEET_UTILIZATION * spec.vehicle_capacity)))

    windows = None
    if spec.time_windows:
        outside = [s for s in spec.time_windows if s not in set(stops)]
        if outside:
            raise InvalidProblemError(f"time windows given for nodes that are not stops: {outside[:5]}")
        windows = {s: TimeWindow(w.earliest, w.latest) for s, w in spec.time_windows.items()}
    if spec.random_windows:
        missing = [s for s in stops if not windows or s not in windows]
        if missing:
            quickest = stored.graph.all_pairs_shortest_time([depot])[depot]
            unreachable = [s for s in missing if s not in quickest]
            if unreachable:
                raise InvalidProblemError(f"stops that the depot cannot reach cannot be given a window: {unreachable[:5]}")
            # its own random stream: turning windows on never changes which stops or demands a seed produces
            windows = {**random_time_windows(missing, quickest, random.Random(f"{spec.seed}-windows")), **(windows or {})}

    return RouteRequest(
        depot=depot,
        stops=stops,
        demands=demands,
        vehicle_capacity=spec.vehicle_capacity,
        n_vehicles=n_vehicles,
        cost_weights=CostWeights(spec.cost_weights.time, spec.cost_weights.distance, spec.cost_weights.congestion),
        time_windows=windows,
        service_time_min=spec.service_time_min,
        time_window_penalty=spec.time_window_penalty,
    )
