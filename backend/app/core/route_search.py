"""
Route-set local search and iterated local search for the capacitated multi-vehicle problem.

`local_search.improve_routes` (relocate + swap + 2-opt, scanning everything every pass) was the polish through
Finding 12, where our pipelines ended 6-9% above an OR-Tools capacitated reference. This is the stronger search
that finding pointed at: the neighbourhoods a modern CVRP solver uses, restricted to a stop's nearest neighbours
and re-examined only where something changed. Results: docs/BENCHMARKS.md, Finding 13.

Operators (each move is scored exactly for our directed, per-direction congested costs; none reverses a stretch
of road, so only the edges at its ends change):

    relocate   move a run of 1-3 consecutive stops next to a nearby stop, in another route or the same one (Or-opt)
    swap       exchange two stops of different routes, each taking the other's place
    2-opt*     exchange the tails of two routes: A[:i] + B[j:] and B[:j] + A[i:]
    SWAP*      exchange two stops of different routes, each re-inserted at ITS best position in the other route
               (not necessarily the other's old place); contains `swap` as a special case
    2-opt      reorder inside a route (`local_search.two_opt`, exact for asymmetric costs)

A move is taken when it lowers  travel time + penalty * capacity overload, the same fitness the metaheuristics use,
so an overloaded van is relieved as readily as a long trip is shortened.

Granularity: a stop is only paired with its `neighbours` nearest stops (by leg time in both directions), and after a
change only the stops of the routes it touched are re-examined (a queue), so repairing a small change costs a few
milliseconds instead of a full scan.

`ruin_and_recreate` and `run_ils` add the diversification: remove a cluster of nearby stops, reinsert each at its
cheapest position, repair locally, keep the result if it is better (iterated local search).

Vehicles: the search holds exactly `n_vehicles` route slots, some possibly empty, so a stop can be moved into an
unused vehicle and the fleet limit can never be exceeded; empty routes are dropped from the result.
"""

from __future__ import annotations

import random
import time
from collections import deque
from typing import Sequence

from app.core.baselines.dijkstra_baseline import nearest_neighbor_order
from app.core.local_search import two_opt
from app.core.types import OptimizationResult
from app.core.vrp_formulation import RoutingProblem

EPS = 1e-9
ALL_OPERATORS = ("relocate", "swap", "two_opt_star", "swap_star", "two_opt")


class RouteSearch:
    def __init__(
        self,
        problem: RoutingProblem,
        routes: Sequence[Sequence] | None = None,
        neighbours: int = 12,
        penalty_weight: float = 1000.0,
        operators: Sequence[str] = ALL_OPERATORS,
        seed: int | None = None,
    ):
        unknown = set(operators) - set(ALL_OPERATORS)
        if unknown:
            raise ValueError(f"unknown operators {sorted(unknown)}; choose from {ALL_OPERATORS}")
        request = problem.request
        if problem.has_time_windows:
            raise ValueError("the route search does not model time windows yet: its move evaluation assumes a route's cost does not depend on when it starts")
        self.problem = problem
        self.depot = request.depot
        self.stops = list(dict.fromkeys(request.stops))
        self.demand = {s: (request.demands or {}).get(s, 0) for s in self.stops}
        self.capacity = request.vehicle_capacity if request.demands is not None else None
        self.fleet = request.n_vehicles
        self.penalty = penalty_weight
        self.operators = frozenset(operators)
        self.rng = random.Random(seed)

        nodes = [self.depot, *self.stops]
        legs = problem.legs
        self.leg = {u: {v: (0.0 if u == v else legs[u][v]) for v in nodes} for u in nodes}
        ranked = {x: sorted((z for z in self.stops if z != x), key=lambda z: self.leg[x][z] + self.leg[z][x]) for x in self.stops}
        self.ranked = ranked  # every other stop, nearest first (ruin picks its cluster from here)
        self.near = {x: ranked[x][:neighbours] for x in self.stops}

        self.routes: list[list] = []
        self.load: list[float] = []
        self.route_of: dict = {}
        self.cost = 0.0
        if routes is not None:
            self.set_routes(routes)

    # ---- state -----------------------------------------------------------------------------------------------

    def set_routes(self, routes: Sequence[Sequence]) -> None:
        depot = self.depot
        lists = [list(r[1:-1]) if r and r[0] == depot else list(r) for r in routes]
        lists = [r for r in lists if r]
        if len(lists) > self.fleet:
            raise ValueError(f"{len(lists)} routes but only {self.fleet} vehicles")
        if sorted(s for r in lists for s in r) != sorted(self.stops):
            raise ValueError("the routes must visit every stop exactly once")
        lists += [[] for _ in range(self.fleet - len(lists))]
        self.routes = lists
        self.load = [sum(self.demand[s] for s in r) for r in lists]
        self.route_of = {s: i for i, r in enumerate(lists) for s in r}
        self.cost = self.recompute_cost()

    def result_routes(self) -> list[list]:
        return [[self.depot, *r, self.depot] for r in self.routes if r]

    def snapshot(self):
        return [r[:] for r in self.routes], self.load[:], self.cost

    def restore(self, snapshot) -> None:
        routes, load, cost = snapshot
        self.routes = [r[:] for r in routes]
        self.load = load[:]
        self.cost = cost
        self.route_of = {s: i for i, r in enumerate(self.routes) for s in r}

    def excess(self, load: float) -> float:
        return max(0.0, load - self.capacity) if self.capacity is not None else 0.0

    def route_time(self, route: Sequence) -> float:
        if not route:
            return 0.0
        leg, depot = self.leg, self.depot
        total = leg[depot][route[0]] + leg[route[-1]][depot]
        for a, b in zip(route, route[1:]):
            total += leg[a][b]
        return total

    def contribution(self, index: int) -> float:
        return self.route_time(self.routes[index]) + self.penalty * self.excess(self.load[index])

    def recompute_cost(self) -> float:
        return sum(self.contribution(i) for i in range(len(self.routes)))

    def travel_time(self) -> float:
        return sum(self.route_time(r) for r in self.routes)

    def set_route(self, index: int, new: list) -> None:
        """Replace one route, keeping the loads, the stop-to-route map and the running cost exact."""
        self.cost -= self.contribution(index)
        self.routes[index] = new
        self.load[index] = sum(self.demand[s] for s in new)
        for s in new:
            self.route_of[s] = index
        self.cost += self.contribution(index)

    # ---- moves -----------------------------------------------------------------------------------------------

    def _relocate(self, x) -> list[int] | None:
        leg, depot, demand, near, route_of, routes, load = self.leg, self.depot, self.demand, self.near, self.route_of, self.routes, self.load
        excess, penalty = self.excess, self.penalty
        ra = route_of[x]
        A = routes[ra]
        p = A.index(x)
        empty = next((i for i, r in enumerate(routes) if not r), None)
        best_delta, best_move = -EPS, None

        for length in (1, 2, 3):
            if p + length > len(A):
                break
            segment = A[p : p + length]
            head, tail = segment[0], segment[-1]
            seg_load = sum(demand[s] for s in segment)
            u0 = A[p - 1] if p else depot
            v0 = A[p + length] if p + length < len(A) else depot
            saved = leg[u0][head] + leg[tail][v0] - leg[u0][v0]
            leave = excess(load[ra] - seg_load) - excess(load[ra])
            inside = set(segment)
            reduced = None  # the source route without the segment, for same-route moves

            for z in near[head] if length == 1 else [*near[head], *(t for t in near[tail] if t not in near[head])]:
                if z in inside:
                    continue
                rb = route_of[z]
                B = routes[rb]
                q = B.index(z)
                if rb != ra:
                    over = leave + excess(load[rb] + seg_load) - excess(load[rb])
                    v = B[q + 1] if q + 1 < len(B) else depot
                    delta = leg[z][head] + leg[tail][v] - leg[z][v] - saved + penalty * over  # after z
                    if delta < best_delta:
                        best_delta, best_move = delta, ("move", ra, p, length, rb, q + 1)
                    u = B[q - 1] if q else depot
                    delta = leg[u][head] + leg[tail][z] - leg[u][z] - saved + penalty * over  # before z
                    if delta < best_delta:
                        best_delta, best_move = delta, ("move", ra, p, length, rb, q)
                else:
                    if reduced is None:
                        reduced = A[:p] + A[p + length :]
                    qz = reduced.index(z)
                    for at in (qz + 1, qz):
                        candidate = reduced[:at] + segment + reduced[at:]
                        if candidate == A:
                            continue
                        delta = self.route_time(candidate) - self.route_time(A)
                        if delta < best_delta:
                            best_delta, best_move = delta, ("intra", ra, candidate)

            if empty is not None and empty != ra:  # a vehicle that is not in use yet
                over = leave + excess(seg_load) - excess(0.0)
                delta = leg[depot][head] + leg[tail][depot] - saved + penalty * over
                if delta < best_delta:
                    best_delta, best_move = delta, ("move", ra, p, length, empty, 0)

        if best_move is None:
            return None
        if best_move[0] == "intra":
            self.set_route(best_move[1], best_move[2])
            return [best_move[1]]
        _, ra, p, length, rb, at = best_move
        segment = routes[ra][p : p + length]
        self.set_route(ra, routes[ra][:p] + routes[ra][p + length :])
        self.set_route(rb, routes[rb][:at] + segment + routes[rb][at:])
        return [ra, rb]

    def _swap(self, x) -> list[int] | None:
        leg, depot, demand, near, route_of, routes, load = self.leg, self.depot, self.demand, self.near, self.route_of, self.routes, self.load
        excess, penalty = self.excess, self.penalty
        ra = route_of[x]
        A = routes[ra]
        p = A.index(x)
        u1 = A[p - 1] if p else depot
        v1 = A[p + 1] if p + 1 < len(A) else depot
        dx = demand[x]
        best_delta, best_move = -EPS, None
        for y in near[x]:
            rb = route_of[y]
            if rb == ra:
                continue
            B = routes[rb]
            q = B.index(y)
            u2 = B[q - 1] if q else depot
            v2 = B[q + 1] if q + 1 < len(B) else depot
            dy = demand[y]
            delta = (
                leg[u1][y] + leg[y][v1] - leg[u1][x] - leg[x][v1]
                + leg[u2][x] + leg[x][v2] - leg[u2][y] - leg[y][v2]
                + penalty * (excess(load[ra] - dx + dy) + excess(load[rb] - dy + dx) - excess(load[ra]) - excess(load[rb]))
            )
            if delta < best_delta:
                best_delta, best_move = delta, (rb, q)
        if best_move is None:
            return None
        rb, q = best_move
        y = routes[rb][q]
        new_a, new_b = A[:], routes[rb][:]
        new_a[p], new_b[q] = y, x
        self.set_route(ra, new_a)
        self.set_route(rb, new_b)
        return [ra, rb]

    def _two_opt_star(self, x) -> list[int] | None:
        leg, depot, demand, near, route_of, routes, load = self.leg, self.depot, self.demand, self.near, self.route_of, self.routes, self.load
        excess, penalty = self.excess, self.penalty
        ra = route_of[x]
        A = routes[ra]
        p = A.index(x)
        succ_a = A[p + 1] if p + 1 < len(A) else depot
        prefix_a = sum(demand[s] for s in A[: p + 1])
        suffix_a = load[ra] - prefix_a
        best_delta, best_move = -EPS, None
        for z in near[x]:
            rb = route_of[z]
            if rb == ra:
                continue
            B = routes[rb]
            q = B.index(z)
            pred_b = B[q - 1] if q else depot
            prefix_b = sum(demand[s] for s in B[:q])
            suffix_b = load[rb] - prefix_b
            delta = (
                leg[x][z] + leg[pred_b][succ_a] - leg[x][succ_a] - leg[pred_b][z]  # x -> z, pred_b -> succ_a
                + penalty * (excess(prefix_a + suffix_b) + excess(prefix_b + suffix_a) - excess(load[ra]) - excess(load[rb]))
            )
            if delta < best_delta:
                best_delta, best_move = delta, (rb, q)
        if best_move is None:
            return None
        rb, q = best_move
        B = routes[rb]
        self.set_route(ra, A[: p + 1] + B[q:])
        self.set_route(rb, B[:q] + A[p + 1 :])
        return [ra, rb]

    def _best_insertion(self, stop, route: list) -> tuple[float, int]:
        """The cheapest place to insert `stop` into `route`: (extra travel time, index)."""
        leg, depot = self.leg, self.depot
        best, at = float("inf"), 0
        previous = depot
        for i in range(len(route) + 1):
            following = route[i] if i < len(route) else depot
            extra = leg[previous][stop] + leg[stop][following] - leg[previous][following]
            if extra < best:
                best, at = extra, i
            previous = following
        return best, at

    def _swap_star(self, x) -> list[int] | None:
        leg, depot, demand, near, route_of, routes, load = self.leg, self.depot, self.demand, self.near, self.route_of, self.routes, self.load
        excess, penalty = self.excess, self.penalty
        ra = route_of[x]
        A = routes[ra]
        p = A.index(x)
        u1 = A[p - 1] if p else depot
        v1 = A[p + 1] if p + 1 < len(A) else depot
        gain_x = leg[u1][x] + leg[x][v1] - leg[u1][v1]
        reduced_a = A[:p] + A[p + 1 :]
        dx = demand[x]
        best_delta, best_move = -EPS, None
        for y in near[x]:
            rb = route_of[y]
            if rb == ra:
                continue
            B = routes[rb]
            q = B.index(y)
            u2 = B[q - 1] if q else depot
            v2 = B[q + 1] if q + 1 < len(B) else depot
            gain_y = leg[u2][y] + leg[y][v2] - leg[u2][v2]
            reduced_b = B[:q] + B[q + 1 :]
            dy = demand[y]
            put_x, at_x = self._best_insertion(x, reduced_b)
            put_y, at_y = self._best_insertion(y, reduced_a)
            delta = (
                put_x + put_y - gain_x - gain_y
                + penalty * (excess(load[ra] - dx + dy) + excess(load[rb] - dy + dx) - excess(load[ra]) - excess(load[rb]))
            )
            if delta < best_delta:
                best_delta, best_move = delta, (rb, reduced_b, at_x, reduced_a, at_y, y)
        if best_move is None:
            return None
        rb, reduced_b, at_x, reduced_a, at_y, y = best_move
        self.set_route(ra, reduced_a[:at_y] + [y] + reduced_a[at_y:])
        self.set_route(rb, reduced_b[:at_x] + [x] + reduced_b[at_x:])
        return [ra, rb]

    def _tidy(self, index: int) -> bool:
        """2-opt inside one route; True if it changed."""
        route = self.routes[index]
        if len(route) < 3:
            return False
        better = two_opt(route, self.problem.leg_time, self.depot)
        if better == route:
            return False
        self.set_route(index, list(better))
        return True

    def _try(self, x) -> list[int] | None:
        ops = self.operators
        for name, move in (
            ("relocate", self._relocate),
            ("swap", self._swap),
            ("two_opt_star", self._two_opt_star),
            ("swap_star", self._swap_star),
        ):
            if name in ops:
                touched = move(x)
                if touched is not None:
                    return touched
        return None

    # ---- local search ----------------------------------------------------------------------------------------

    def local_search(self, stops: Sequence | None = None) -> None:
        """Improve until no operator finds anything, examining `stops` first (default: all of them) and, after
        every change, the stops of the routes it touched."""
        queue = deque(stops if stops is not None else self.rng.sample(self.stops, len(self.stops)))
        queued = set(queue)
        tidy = "two_opt" in self.operators
        if tidy:
            for i in range(len(self.routes)):
                self._tidy(i)
        while queue:
            x = queue.popleft()
            queued.discard(x)
            touched = self._try(x)
            while touched is not None:
                if tidy:
                    for i in touched:
                        self._tidy(i)
                for i in touched:
                    for s in self.routes[i]:
                        if s not in queued:
                            queued.add(s)
                            queue.append(s)
                touched = self._try(x)

    # ---- diversification -------------------------------------------------------------------------------------

    def _place(self, stop, route_indices) -> tuple[float, int, int, float]:
        """The cheapest place for `stop` among the given routes: (cost, route, index, overload it would cause)."""
        demand = self.demand[stop]
        best = (float("inf"), -1, 0, 0.0)
        for r in route_indices:
            extra, at = self._best_insertion(stop, self.routes[r])
            over = self.excess(self.load[r] + demand) - self.excess(self.load[r])
            cost = extra + self.penalty * over
            if cost < best[0]:
                best = (cost, r, at, over)
        return best

    def ruin_and_recreate(self, n_remove: int) -> list:
        """Remove a cluster of nearby stops and put each back at its cheapest position. Returns the stops of
        the routes that changed (what the repair search should look at first)."""
        rng = self.rng
        centre = rng.choice(self.stops)
        pool = self.ranked[centre][: n_remove * 2]
        removed = [centre, *rng.sample(pool, min(n_remove - 1, len(pool)))]

        touched = set()
        for s in removed:
            r = self.route_of[s]
            touched.add(r)
            self.set_route(r, [t for t in self.routes[r] if t != s])
        pending = set(removed)  # their entry in route_of is stale until they are back in a route
        rng.shuffle(removed)

        unused = [i for i, route in enumerate(self.routes) if not route][:1]
        for s in removed:
            pending.discard(s)
            nearby = {self.route_of[z] for z in self.near[s] if z not in pending}
            cost, r, at, over = self._place(s, [*nearby, *unused])
            if r < 0 or over > 0:  # nothing nearby has room: look at every route
                cost, r, at, over = min(((cost, r, at, over), self._place(s, range(len(self.routes)))), key=lambda t: t[0])
            self.set_route(r, self.routes[r][:at] + [s] + self.routes[r][at:])
            touched.add(r)
            unused = [i for i in unused if not self.routes[i]] or [i for i, route in enumerate(self.routes) if not route][:1]
        return [s for r in touched for s in self.routes[r]]

    def run_ils(
        self,
        iterations: int,
        remove: tuple[int, int] = (4, 12),
        max_seconds: float | None = None,
        accept_worse: float = 0.0,
        patience: int | None = None,
    ) -> list[float]:
        """Iterated local search from the current routes. Each iteration ruins and recreates a cluster, repairs
        locally and keeps the result if it is better than the current solution (or within `accept_worse` of its
        cost, as a fraction). The best solution seen is restored at the end. Stops early after `iterations`, after
        `max_seconds`, or (if given) after `patience` iterations in a row without a new best. Returns the best cost
        after each iteration."""
        best = self.snapshot()
        best_cost = self.cost
        current_cost = self.cost
        trace = []
        since_best = 0
        started = time.perf_counter()
        for _ in range(iterations):
            if max_seconds is not None and time.perf_counter() - started > max_seconds:
                break
            before = self.snapshot()
            dirty = self.ruin_and_recreate(self.rng.randint(*remove))
            self.local_search(dirty)
            since_best += 1
            if self.cost < current_cost - EPS or self.cost < current_cost * (1 + accept_worse) - EPS:
                current_cost = self.cost
                if self.cost < best_cost - EPS:
                    best, best_cost = self.snapshot(), self.cost
                    since_best = 0
            else:
                self.restore(before)
            trace.append(best_cost)
            if patience is not None and since_best >= patience:
                break
        self.restore(best)
        return trace


def improve_with_search(
    problem: RoutingProblem,
    routes: Sequence[Sequence],
    iterations: int = 0,
    neighbours: int = 12,
    penalty_weight: float = 1000.0,
    seed: int | None = 0,
    operators: Sequence[str] = ALL_OPERATORS,
) -> list[list]:
    """Local search on a route set, then (optionally) iterated local search; routes in, routes out."""
    search = RouteSearch(problem, routes, neighbours=neighbours, penalty_weight=penalty_weight, operators=operators, seed=seed)
    search.local_search()
    if iterations:
        search.run_ils(iterations)
    return search.result_routes()


MAX_HISTORY = 1000  # points kept of the search's progress curve, so a long run does not bloat an API response


def solve_with_search(
    problem: RoutingProblem,
    penalty_weight: float = 1000.0,
    time_limit_sec: float = 10.0,
    max_iterations: int | None = None,
    seed: int | None = None,
) -> OptimizationResult:
    """Nearest neighbour, then this module's local search, then iterated local search, as one algorithm that returns
    the same result type as QPSO, PSO and GA so the API, the benchmark and the UI can treat it like any of them.

    The iterated search stops at the time limit, at `max_iterations` if given, or when it has gone
    `patience = 300 + 10 x stops` iterations without a new best (a small problem converges long before the time
    limit; on 100 stops that is 1,300 iterations, about the length of a default run). `convergence_history` is the cost
    of the nearest-neighbour start, the cost after the local search, then the best cost after each iteration, thinned to
    at most MAX_HISTORY points with the last one kept. `iterations` counts the iterated-search iterations run.
    """
    started = time.perf_counter()
    search = RouteSearch(problem, problem.split(nearest_neighbor_order(problem)), penalty_weight=penalty_weight, seed=seed)
    history = [search.cost]
    search.local_search()
    history.append(search.cost)

    patience = 300 + 10 * len(search.stops)
    remaining = max(0.0, time_limit_sec - (time.perf_counter() - started))
    trace = search.run_ils(max_iterations if max_iterations is not None else 10**9, max_seconds=remaining, patience=patience)
    history.extend(trace)
    if len(history) > MAX_HISTORY:
        stride = (len(history) - 1) / (MAX_HISTORY - 1)
        history = [history[round(i * stride)] for i in range(MAX_HISTORY)]

    evaluation = problem.evaluate_routes(search.result_routes())
    return OptimizationResult(
        best_route=evaluation.route,
        best_cost=evaluation.total_time_min + penalty_weight * evaluation.capacity_violation,
        convergence_history=history,
        runtime_sec=time.perf_counter() - started,
        iterations=len(trace),
        n_particles=1,
    )
