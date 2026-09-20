"""In-memory registry of loaded graphs, keyed by id. Small and process-local by design
(the prototype runs as a single API process); the oldest graphs are evicted first."""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from app.core.graph_model import TrafficGraph
from app.core.live_traffic import count_roads
from app.schemas.graph import TrafficInfo


@dataclass
class LiveReading:
    """The last real reading taken for a graph, kept so repeat clicks don't burn the provider's free quota."""

    taken_at: float  # time.monotonic()
    factors: list[list]  # [u, v, congestion factor] for every edge
    info: TrafficInfo


@dataclass
class StoredGraph:
    graph_id: str
    graph: TrafficGraph
    source: str  # "synthetic" | "city"
    label: str
    center: tuple[float, float]  # (lat, lon)
    key: str | None = None  # identifies the downloaded map (city graphs); ties snapshots to it
    traffic: TrafficInfo | None = None  # where the current congestion came from
    live_cache: LiveReading | None = None
    # Closed roads: the arcs taken out of the graph, so that reopening restores them exactly (see services/closures.py).
    # Keyed by the road's two intersections; each entry lists (u, v, edge data) for every direction that was removed.
    closed: dict[frozenset, list[tuple]] = field(default_factory=dict)
    # Requests run in a worker-thread pool; solving reads edge weights and the traffic
    # endpoints rewrite them, so per-graph access is serialized.
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


class GraphStore:
    def __init__(self, capacity: int = 24):
        self._capacity = capacity
        self._items: OrderedDict[str, StoredGraph] = OrderedDict()
        self._lock = threading.Lock()

    def add(
        self,
        graph: TrafficGraph,
        source: str,
        label: str,
        center: tuple[float, float],
        key: str | None = None,
    ) -> StoredGraph:
        stored = StoredGraph(uuid.uuid4().hex[:12], graph, source, label, center, key=key)
        roads = count_roads(graph)
        # a new synthetic network starts with random traffic; a freshly loaded city starts at free flow
        stored.traffic = (
            TrafficInfo(kind="simulated", label="random", roads_total=roads)
            if source == "synthetic"
            else TrafficInfo(kind="free_flow", label="free flow", roads_total=roads)
        )
        with self._lock:
            self._items[stored.graph_id] = stored
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
        return stored

    def get(self, graph_id: str) -> StoredGraph:
        with self._lock:
            stored = self._items[graph_id]  # KeyError if unknown or evicted
            self._items.move_to_end(graph_id)
            return stored

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


_store = GraphStore()


def get_store() -> GraphStore:
    return _store
