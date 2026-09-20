"""Builds the JSON-facing views: a graph for the map, and routes drawn along real roads."""

from __future__ import annotations

from app.core.cost_model import CostWeights, path_metrics
from app.core.graph_model import TrafficGraph
from app.core.vrp_formulation import RoutingProblem
from app.schemas.graph import GraphSummary, GraphView
from app.schemas.solve import CostWeightsSpec, ResolvedProblem, RouteOut, StopTimingOut, TimeWindowSpec
from app.services.closures import closed_roads, cut_off_nodes
from app.services.graph_store import StoredGraph


def _mean_congestion(graph: TrafficGraph) -> float:
    factors = [d["congestion_factor"] for _, _, d in graph.graph.edges(data=True)]
    return sum(factors) / len(factors) if factors else 1.0


def graph_summary(stored: StoredGraph) -> GraphSummary:
    graph = stored.graph
    lats = [a["lat"] for _, a in graph.graph.nodes(data=True)]
    lons = [a["lon"] for _, a in graph.graph.nodes(data=True)]
    return GraphSummary(
        graph_id=stored.graph_id,
        source=stored.source,
        label=stored.label,
        node_count=graph.node_count,
        edge_count=graph.edge_count,
        center=stored.center,
        bounds=((min(lats), min(lons)), (max(lats), max(lons))),
        mean_congestion=_mean_congestion(graph),
        traffic=stored.traffic,
        closed_roads=len(stored.closed),
    )


def graph_view(stored: StoredGraph) -> GraphView:
    g = stored.graph.graph
    nodes = [[node, attrs["lat"], attrs["lon"]] for node, attrs in g.nodes(data=True)]

    # one entry per road: two-way roads collapse to a single line coloured by the worse direction
    roads: dict[tuple, float] = {}
    for u, v, data in g.edges(data=True):
        key = (u, v) if (v, u) not in roads else (v, u)
        roads[key] = max(roads.get(key, 0.0), data["congestion_factor"])
    edges = [[u, v, congestion] for (u, v), congestion in roads.items()]
    return GraphView(
        summary=graph_summary(stored), nodes=nodes, edges=edges, closed=closed_roads(stored), cut_off=cut_off_nodes(stored)
    )


def path_points(graph: TrafficGraph, path) -> list[list[float]]:
    """The [lat, lon] points along a node path, following each road's shape when it has one."""
    g = graph.graph
    points: list[list[float]] = []
    for a, b in zip(path, path[1:]):
        edge = g[a][b]
        shape = edge.get("shape")
        segment = [list(p) for p in shape] if shape else [
            [g.nodes[a]["lat"], g.nodes[a]["lon"]],
            [g.nodes[b]["lat"], g.nodes[b]["lon"]],
        ]
        points.extend(segment if not points else segment[1:])
    if not points and path:  # a path of a single node
        points = [[g.nodes[path[0]]["lat"], g.nodes[path[0]]["lon"]]]
    return points


def _leg_polyline(graph: TrafficGraph, u, v, weights: CostWeights | None = None):
    """Follow the cheapest path from u to v (the quickest, unless other weights were asked for). Returns the
    [lat, lon] points and the path's real metrics: minutes, kilometres and congestion delay."""
    path = graph.shortest_path(u, v, weights)
    return path_points(graph, path), path_metrics(graph, path)


def route_outputs(stored: StoredGraph, problem: RoutingProblem, routes: list[list]) -> list[RouteOut]:
    loads = problem.route_loads(routes)
    weights = problem.request.cost_weights
    outputs = []
    for vehicle, (route, load) in enumerate(zip(routes, loads), start=1):
        polyline: list[list[float]] = []
        time_min = distance = delay = 0.0
        for u, v in zip(route, route[1:]):
            points, metrics = _leg_polyline(stored.graph, u, v, weights)
            polyline.extend(points if not polyline else points[1:])
            time_min += metrics.time_min
            distance += metrics.distance_km
            delay += metrics.delay_min
        timing = {}
        if problem.has_time_windows and len(route) > 2:
            plan = problem.schedule(route)
            timing = dict(
                late_min=plan.late_min, wait_min=plan.wait_min, end_min=plan.end_min,
                schedule=[
                    StopTimingOut(stop=t.stop, arrival_min=t.arrival_min, start_min=t.start_min, wait_min=t.wait_min,
                                  late_min=t.late_min, earliest=t.earliest, latest=t.latest)
                    for t in plan.stops
                ],
            )
        outputs.append(
            RouteOut(vehicle=vehicle, nodes=list(route), path=polyline, load=load, time_min=time_min, distance_km=distance,
                     delay_min=delay, **timing)
        )
    return outputs


def problem_warnings(problem: RoutingProblem) -> list[str]:
    """Things the caller should know before trusting the costs."""
    request = problem.request
    total_demand = sum(request.demands.values())
    fleet_capacity = request.n_vehicles * request.vehicle_capacity
    warnings = []
    if total_demand > fleet_capacity:
        warnings.append(
            f"Total demand ({total_demand:g}) exceeds the fleet's capacity ({request.n_vehicles} x "
            f"{request.vehicle_capacity:g} = {fleet_capacity:g}): at least {total_demand - fleet_capacity:g} units of "
            "overload are unavoidable, so every cost includes a constant penalty and comparisons between "
            "algorithms are dominated by it. Add vehicles or raise the capacity."
        )
    too_big = [(stop, demand) for stop, demand in request.demands.items() if demand > request.vehicle_capacity]
    if too_big:
        shown = ", ".join(f"stop {stop} ({demand:g})" for stop, demand in too_big[:5])
        more = f" and {len(too_big) - 5} more" if len(too_big) > 5 else ""
        warnings.append(
            f"{len(too_big)} stop(s) ask for more than one vehicle can carry ({request.vehicle_capacity:g}): {shown}{more}. "
            "Whichever van serves them is overloaded, and the overload is penalized in every plan, so the cost includes "
            "a constant that no algorithm can remove. Raise the capacity or lower those demands."
        )
    if problem.has_time_windows:
        depot = request.depot
        closed_before_reachable = [
            stop for stop, window in request.time_windows.items() if problem.minutes[depot][stop] > window.latest + 1e-9
        ]
        if closed_before_reachable:
            warnings.append(
                f"{len(closed_before_reachable)} stop(s) have a window that closes before a van driving straight from the depot "
                "could arrive, so they will be late whatever the plan."
            )
    return warnings


def resolved_problem(problem: RoutingProblem) -> ResolvedProblem:
    request = problem.request
    return ResolvedProblem(
        depot=request.depot,
        stops=list(request.stops),
        demands={s: float(request.demands[s]) for s in request.stops},
        n_vehicles=request.n_vehicles,
        vehicle_capacity=float(request.vehicle_capacity),
        cost_weights=CostWeightsSpec(
            time=request.cost_weights.time, distance=request.cost_weights.distance, congestion=request.cost_weights.congestion
        ) if request.cost_weights is not None else CostWeightsSpec(),
        time_windows={s: TimeWindowSpec(earliest=w.earliest, latest=w.latest) for s, w in request.time_windows.items()} if request.time_windows else None,
        service_time_min=request.service_time_min,
        time_window_penalty=request.time_window_penalty,
    )
