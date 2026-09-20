"""Turns an API problem description into a validated RouteRequest, filling in whatever
the caller left out (depot, stops, demands, fleet size) deterministically from the seed."""

from __future__ import annotations

import math
import random

import numpy as np

from app.core.cost_model import CostWeights
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

    if spec.stops:
        stops = list(spec.stops)
        if len(set(stops)) != len(stops):
            raise InvalidProblemError("stops contains duplicates")
        unknown = [s for s in stops if s not in known]
        if unknown:
            raise InvalidProblemError(f"stops not in this graph: {unknown[:5]}")
        if depot in stops:
            raise InvalidProblemError("the depot cannot also be a stop")
    else:
        candidates = [n for n in node_ids if n != depot]
        if not candidates:
            raise InvalidProblemError("the graph has no nodes besides the depot")
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

    return RouteRequest(
        depot=depot,
        stops=stops,
        demands=demands,
        vehicle_capacity=spec.vehicle_capacity,
        n_vehicles=n_vehicles,
        cost_weights=CostWeights(spec.cost_weights.time, spec.cost_weights.distance, spec.cost_weights.congestion),
    )
