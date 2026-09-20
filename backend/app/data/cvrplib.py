"""
Standard CVRP benchmark instances (CVRPLIB, TSPLIB text format) as problems the rest of the code can solve.

Our own benchmarks run on synthetic road graphs, so their only references are other heuristics. CVRPLIB's "X" set
(Uchoa et al., 2017) publishes an optimal or best-known cost for every instance, which is what lets us say how far
from optimal a solver is.

Conventions of the X set that this module follows exactly (a solver is only comparable if it scores the same way):

- Node 1 of the file is the depot and customers are 2..n. We renumber to depot 0 and customers 1..n-1, which is also
  how the published solution files number the customers.
- EDGE_WEIGHT_TYPE EUC_2D: the distance between two points is their Euclidean distance rounded to the nearest
  integer, and a solution costs the sum of these integers over the legs it drives. The rounded direct distance is used
  as is, with NO shortest-path closure: rounding can break the triangle inequality by a unit, and the published costs
  are defined on the direct legs. (`MatrixGraph` below is why our road-graph code can be reused without shortcuts.)
- The fleet is free: the "k" in an instance name is the smallest number of vehicles that can carry the demand, not a
  limit. Whoever calls `build_problem` chooses how many vehicles to allow.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from app.core.vrp_formulation import RouteRequest, RoutingProblem


def nint(x: float) -> int:
    """Round to the nearest integer, halves upward (the TSPLIB `nint` for the non-negative distances used here)."""
    return int(math.floor(x + 0.5))


@dataclass(frozen=True)
class CvrpInstance:
    name: str
    capacity: int
    coords: tuple[tuple[float, float], ...]  # index 0 is the depot
    demands: tuple[int, ...]  # index 0 is the depot (demand 0)
    min_vehicles: int | None  # the k of a name like X-n101-k25, when there is one

    @property
    def n_customers(self) -> int:
        return len(self.coords) - 1

    def distance(self, a: int, b: int) -> int:
        (ax, ay), (bx, by) = self.coords[a], self.coords[b]
        return nint(math.hypot(ax - bx, ay - by))

    def matrix(self) -> list[list[float]]:
        n = len(self.coords)
        return [[float(self.distance(a, b)) for b in range(n)] for a in range(n)]


def _sections(text: str):
    """Split a TSPLIB file into its `KEY : value` header and its data sections (a list of token lists each)."""
    header: dict[str, str] = {}
    sections: dict[str, list[list[str]]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "EOF":
            continue
        if ":" not in line and line.split()[0].endswith("_SECTION"):
            current = line.split()[0]
            sections[current] = []
        elif ":" in line and not line[0].isdigit() and not line.startswith("-"):
            key, _, value = line.partition(":")
            header[key.strip().upper()] = value.strip()
            current = None
        elif current is not None:
            sections[current].append(line.split())
        else:
            raise ValueError(f"unexpected line outside any section: {line!r}")
    return header, sections


def parse_instance(text: str) -> CvrpInstance:
    """Read a CVRPLIB `.vrp` file. Only what the X set uses is supported; anything else is refused, not guessed."""
    header, sections = _sections(text)
    if header.get("TYPE", "CVRP") != "CVRP":
        raise ValueError(f"TYPE {header['TYPE']!r} is not CVRP")
    if header.get("EDGE_WEIGHT_TYPE") != "EUC_2D":
        raise NotImplementedError(f"EDGE_WEIGHT_TYPE {header.get('EDGE_WEIGHT_TYPE')!r}: only EUC_2D is supported")
    for needed in ("NAME", "DIMENSION", "CAPACITY"):
        if needed not in header:
            raise ValueError(f"missing {needed}")
    for needed in ("NODE_COORD_SECTION", "DEMAND_SECTION", "DEPOT_SECTION"):
        if needed not in sections:
            raise ValueError(f"missing {needed}")

    n = int(header["DIMENSION"])
    capacity = int(float(header["CAPACITY"]))
    if capacity <= 0:
        raise ValueError("CAPACITY must be positive")

    coords = {int(row[0]): (float(row[1]), float(row[2])) for row in sections["NODE_COORD_SECTION"]}
    demands = {int(row[0]): int(float(row[1])) for row in sections["DEMAND_SECTION"]}
    if sorted(coords) != list(range(1, n + 1)) or sorted(demands) != list(range(1, n + 1)):
        raise ValueError(f"DIMENSION is {n} but the coordinate/demand sections do not list nodes 1..{n}")
    depots = [int(tok) for row in sections["DEPOT_SECTION"] for tok in row if int(tok) != -1]
    if depots != [1]:
        raise ValueError(f"expected a single depot at node 1, found {depots}")
    if demands[1] != 0:
        raise ValueError("the depot must have demand 0")
    too_big = [i for i in range(2, n + 1) if demands[i] > capacity]
    if too_big:
        raise ValueError(f"customers {too_big[:5]} demand more than the vehicle capacity")

    name = header["NAME"]
    k = re.search(r"-k(\d+)$", name)
    return CvrpInstance(
        name=name,
        capacity=capacity,
        coords=tuple(coords[i] for i in range(1, n + 1)),
        demands=tuple(demands[i] for i in range(1, n + 1)),
        min_vehicles=int(k.group(1)) if k else None,
    )


def parse_solution(text: str) -> tuple[list[list[int]], float]:
    """Read a CVRPLIB `.sol` file: (routes as lists of customers 1..n-1 without the depot, the stated cost)."""
    routes: list[list[int]] = []
    cost = None
    for raw in text.splitlines():
        line = raw.strip()
        route = re.match(r"Route\s*#\s*\d+\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if route:
            routes.append([int(tok) for tok in route.group(1).split()])
        elif line.lower().startswith("cost"):
            cost = float(line.split()[1])
    if cost is None or not routes:
        raise ValueError("not a solution file: no routes or no Cost line")
    return routes, cost


def default_fleet(instance: CvrpInstance) -> int:
    """How many vans the benchmarks allow: 25% more than the minimum k, plus two. The fleet is free in the benchmark, so
    this only has to be roomy enough never to be the reason a solution is worse (the scripts also check that the
    published optimal solution fits)."""
    if instance.min_vehicles is None:
        raise ValueError(f"{instance.name} has no k in its name; pass an explicit fleet size")
    return math.ceil(1.25 * instance.min_vehicles) + 2


def load_instance(path: Path) -> CvrpInstance:
    return parse_instance(path.read_text(encoding="utf-8"))


def load_solution(path: Path) -> tuple[list[list[int]], float]:
    return parse_solution(path.read_text(encoding="utf-8"))


def solution_cost(instance: CvrpInstance, routes: Iterable[Sequence[int]]) -> int:
    """Cost of routes given as customer lists (depot left out), straight from the coordinates. Deliberately does not
    go through `RoutingProblem`, so it can check what the solvers report."""
    total = 0
    for route in routes:
        path = [0, *route, 0]
        total += sum(instance.distance(a, b) for a, b in zip(path, path[1:]))
    return total


def check_solution(instance: CvrpInstance, routes: Sequence[Sequence[int]], max_vehicles: int | None = None) -> None:
    """Raise unless every customer is visited exactly once, no route exceeds the capacity and (if given) the fleet
    limit holds. Independent of any solver's own bookkeeping."""
    visited = sorted(c for r in routes for c in r)
    if visited != list(range(1, instance.n_customers + 1)):
        raise AssertionError("every customer must be visited exactly once")
    for r in routes:
        load = sum(instance.demands[c] for c in r)
        if load > instance.capacity:
            raise AssertionError(f"a route carries {load} > capacity {instance.capacity}")
    if max_vehicles is not None and len([r for r in routes if r]) > max_vehicles:
        raise AssertionError(f"{len([r for r in routes if r])} routes but only {max_vehicles} vehicles allowed")


class MatrixGraph:
    """Stands in for `TrafficGraph` where travel times are given directly and there is no road network to route over.
    `RoutingProblem` only asks its graph for `all_pairs_shortest_time`; answering with the given matrix keeps every
    solver in the project usable on a benchmark instance without changing a distance."""

    def __init__(self, matrix: Sequence[Sequence[float]]):
        self._matrix = matrix

    def all_pairs_shortest_time(self, nodes: Iterable) -> dict:
        nodes = list(nodes)
        return {u: {v: (0.0 if u == v else float(self._matrix[u][v])) for v in nodes} for u in nodes}


def build_problem(instance: CvrpInstance, n_vehicles: int, decoder: str = "greedy") -> tuple[MatrixGraph, RouteRequest, RoutingProblem]:
    graph = MatrixGraph(instance.matrix())
    request = RouteRequest(
        depot=0,
        stops=list(range(1, instance.n_customers + 1)),
        demands={c: instance.demands[c] for c in range(1, instance.n_customers + 1)},
        vehicle_capacity=instance.capacity,
        n_vehicles=n_vehicles,
        decoder=decoder,
    )
    return graph, request, RoutingProblem(graph, request)
