"""In-memory registry of loaded graphs, keyed by id. Small and process-local by design
(the prototype runs as a single API process); the oldest graphs are evicted first."""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from app.core.graph_model import TrafficGraph


@dataclass
class StoredGraph:
    graph_id: str
    graph: TrafficGraph
    source: str  # "synthetic" | "city"
    label: str
    center: tuple[float, float]  # (lat, lon)
    # Requests run in a worker-thread pool; solving reads edge weights and the traffic
    # endpoints rewrite them, so per-graph access is serialized.
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


class GraphStore:
    def __init__(self, capacity: int = 24):
        self._capacity = capacity
        self._items: OrderedDict[str, StoredGraph] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, graph: TrafficGraph, source: str, label: str, center: tuple[float, float]) -> StoredGraph:
        stored = StoredGraph(uuid.uuid4().hex[:12], graph, source, label, center)
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
