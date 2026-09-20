"""
"Block a road" what-ifs: close roads, plan again, compare.

Closing a road takes its arcs (both directions of a two-way road) out of the graph and remembers them on the
StoredGraph, so every solver, shortest-path query and route drawing sees the closure without any change of its own,
and reopening puts the arcs back exactly as they were. Roads are named by the two intersections they join.

Traffic changes (random, rush hour, live, replay) rewrite the roads that are open. A road that is reopened later comes
back with the congestion it had when it was closed.
"""

from __future__ import annotations

import networkx as nx

from app.services.graph_store import StoredGraph


class ClosureError(ValueError):
    """A road to close does not exist."""


def _key(u, v) -> frozenset:
    return frozenset((u, v))


def closed_roads(stored: StoredGraph) -> list[list[int]]:
    """[u, v] for each closed road, in the order they were closed."""
    return [[entry[0][0], entry[0][1]] for entry in stored.closed.values()]


def set_closures(stored: StoredGraph, roads: list[tuple]) -> None:
    """Make exactly `roads` closed: reopen the ones no longer listed, close the new ones."""
    g = stored.graph.graph
    wanted: dict[frozenset, tuple] = {}
    for u, v in roads:
        if u == v:
            raise ClosureError(f"a road joins two different intersections, not {u} to itself")
        key = _key(u, v)
        if not (g.has_edge(u, v) or g.has_edge(v, u) or key in stored.closed):
            raise ClosureError(f"there is no road between intersections {u} and {v}")
        wanted.setdefault(key, (u, v))

    for key in [k for k in stored.closed if k not in wanted]:
        for a, b, data in stored.closed.pop(key):
            g.add_edge(a, b, **data)

    for key, (u, v) in wanted.items():
        if key in stored.closed:
            continue
        removed = []
        for a, b in ((u, v), (v, u)):
            if g.has_edge(a, b):
                removed.append((a, b, dict(g[a][b])))
                g.remove_edge(a, b)
        stored.closed[key] = removed


def cut_off_nodes(stored: StoredGraph) -> list[int]:
    """Intersections outside the biggest part of the network that vehicles can drive to and from."""
    g = stored.graph.graph
    if g.number_of_nodes() == 0:
        return []
    parts = nx.strongly_connected_components(g) if g.is_directed() else nx.connected_components(g)
    biggest = max(parts, key=len)
    return sorted(n for n in g.nodes if n not in biggest)
