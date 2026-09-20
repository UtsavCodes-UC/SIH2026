"""
Rehearse the demo (docs/DEMO_SCRIPT.md) through the API, and check that everything it needs is there.

Run it before every demo, against the server you will present from (local uvicorn or the Docker container). It walks the
same scenes as the script, with fixed seeds, prints what each scene should show (so you know what "normal" looks like),
and exits with 1 if a check fails. Nothing here spends the live-traffic quota unless you pass --live.

    python scripts/demo_rehearsal.py                                 # against http://127.0.0.1:8000
    python scripts/demo_rehearsal.py --base http://127.0.0.1:8020    # e.g. the Docker container on another port
    python scripts/demo_rehearsal.py --live                          # also fetch real TomTom traffic once (about 80 requests)

The numbers differ from the screen in the UI, which draws random stops each time; what should match is the pattern (the
direction and rough size of each change). Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

MG_ROAD = {"place": "MG Road, Bengaluru", "lat": 12.9758, "lon": 77.6068, "radius_m": 1200}  # the UI's default radius: cached, with a recorded snapshot
FASTEST = {"time": 1.0, "distance": 0.0, "congestion": 0.0}
SHORTEST = {"time": 0.0, "distance": 1.0, "congestion": 0.0}  # the UI's "Shortest" preset: the clearest trade-off to show
AVOID_JAMS = {"time": 0.5, "distance": 0.0, "congestion": 0.5}  # the UI's "Avoid jams" preset, normalized (a mild, noisy effect at 15 stops)

failures: list[str] = []
warnings: list[str] = []


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body=None, timeout=300):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{method} {path} -> {error.code}: {error.read().decode()[:300]}") from None
        return json.loads(raw) if raw[:1] in (b"{", b"[") else raw.decode()

    get = lambda self, path, **kw: self.call("GET", path, **kw)  # noqa: E731
    post = lambda self, path, body=None, **kw: self.call("POST", path, body, **kw)  # noqa: E731
    put = lambda self, path, body=None, **kw: self.call("PUT", path, body, **kw)  # noqa: E731


def scene(title: str) -> None:
    print(f"\n=== {title}")


def check(ok: bool, what: str, detail: str = "", warn_only: bool = False) -> None:
    mark = "ok  " if ok else ("WARN" if warn_only else "FAIL")
    print(f"  [{mark}] {what}" + (f"  ({detail})" if detail else ""))
    if not ok:
        (warnings if warn_only else failures).append(what)


def timed(label: str, fn):
    started = time.perf_counter()
    result = fn()
    print(f"      {label}: {time.perf_counter() - started:.1f} s")
    return result


def summary_line(plan: dict) -> str:
    return (
        f"{plan['total_time_min']:.1f} min, {plan['total_distance_km']:.1f} km, {plan['total_delay_min']:.1f} min lost to congestion, "
        f"{len(plan['routes'])} vans, feasible={plan['feasible']}"
    )


def problem_of(plan: dict, **extra) -> dict:
    """The same problem again (stops, demands, depot, fleet), so a change in the result is the world's doing, not a new draw."""
    p = plan["problem"]
    return {"depot": p["depot"], "stops": p["stops"], "demands": p["demands"], "n_vehicles": p["n_vehicles"], "vehicle_capacity": p["vehicle_capacity"], **extra}


def stop_van(plan: dict) -> dict:
    return {stop: route["vehicle"] for route in plan["routes"] for stop in route["nodes"][1:-1]}


def used_roads(plan: dict, view: dict) -> list[tuple[int, int]]:
    """Roads a plan drives on, recovered from its polylines: consecutive intersections that appear on the line and are joined by a road."""
    at = {(round(lat, 6), round(lon, 6)): int(n) for n, lat, lon in view["nodes"]}
    roads = {frozenset((int(u), int(v))) for u, v, _ in view["edges"]}
    found: dict[frozenset, int] = {}
    for route in plan["routes"]:
        on_line = [at[(round(a, 6), round(b, 6))] for a, b in route["path"] if (round(a, 6), round(b, 6)) in at]
        for u, v in zip(on_line, on_line[1:]):
            if u != v and frozenset((u, v)) in roads:
                found[frozenset((u, v))] = found.get(frozenset((u, v)), 0) + 1
    return [tuple(sorted(k)) for k, _ in sorted(found.items(), key=lambda kv: -kv[1])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--live", action="store_true", help="also fetch real TomTom traffic once (spends about 80 of the 2,500 daily requests)")
    args = parser.parse_args()
    api = Api(args.base)
    began = time.perf_counter()

    # ------------------------------------------------------------------------------------------------ 0
    scene("0. Is everything there?")
    try:
        check(api.get("/health").get("status") == "ok", "API answers on /health", args.base)
    except Exception as error:  # noqa: BLE001
        check(False, "API answers on /health", str(error)[:120])
        print("\nNothing is listening there. Start the app (README, 'Run it') and try again.")
        return 1
    check("id=\"root\"" in api.get("/"), "the UI is served from the same address (npm run build done / Docker image built)")
    check(len(api.get("/api/graph/presets")) == 4, "the four preset cities are listed")
    status = api.get("/api/traffic/status")
    check(status["live_available"], "a TomTom key is configured (live traffic)", "recorded traffic still works without it", warn_only=True)

    # ------------------------------------------------------------------------------------------------ 1
    scene("1. Synthetic network, delivery plan (the UI starts on this: 80 intersections, 8 km, random traffic)")
    synthetic = api.post("/api/graph/synthetic", {"n_nodes": 80, "area_size_km": 8, "seed": 1})
    sid = synthetic["summary"]["graph_id"]
    base_plan = timed("QPSO plan, 15 stops", lambda: api.post("/api/optimize", {"graph_id": sid, "n_stops": 15, "seed": 1}))
    print("      " + summary_line(base_plan))
    check(base_plan["feasible"], "the QPSO plan respects every van's capacity")
    check(base_plan["polished"] and base_plan["warm_start"], "defaults are QPSO + warm start + polish")

    # ------------------------------------------------------------------------------------------------ 2
    scene("2. Algorithm benchmark on that same problem (say what it shows, not what we hope it shows)")
    bench = timed("benchmark of every algorithm", lambda: api.post("/api/benchmark", {"graph_id": sid, **problem_of(base_plan), "seed": 1}))
    rows = sorted(bench["algorithms"], key=lambda a: a["polished_cost"] if a["polished_cost"] is not None else a["raw_cost"])
    print(f"      {'algorithm':<22}{'raw (min)':>10}{'+polish':>10}{'time (s)':>10}")
    for a in rows:
        polished = f"{a['polished_cost']:.1f}" if a["polished_cost"] is not None else "-"
        print(f"      {a['name']:<22}{a['raw_cost']:>10.1f}{polished:>10}{a['runtime_sec']:>10.2f}")
    print("      -> honest reading: after the polish the swarms end close together; QPSO's edge is on the RAW numbers (docs/BENCHMARKS.md)")
    check(len(rows) >= 4, "QPSO, PSO, GA and nearest neighbour are all in the table", ", ".join(a["name"] for a in rows))

    # ------------------------------------------------------------------------------------------------ 3
    scene("3. Traffic changes -> the plan changes (free flow -> rush hour), same stops")
    results = {}
    for mode in ("clear", "rush_hour"):
        api.post(f"/api/graph/{sid}/congestion", {"mode": mode, "seed": 1})
        results[mode] = api.post("/api/optimize", {"graph_id": sid, **problem_of(base_plan), "seed": 1})
        print(f"      {mode:<10} {summary_line(results[mode])}")
    moved = sum(1 for s, v in stop_van(results["clear"]).items() if stop_van(results["rush_hour"])[s] != v)
    slower = results["rush_hour"]["total_time_min"] / results["clear"]["total_time_min"] - 1
    print(f"      -> rush hour: {slower:+.0%} driving time; {moved} of {len(base_plan['problem']['stops'])} stops now ride in a different van")
    check(slower > 0.05, "rush hour makes the same job slower", f"{slower:+.0%}")
    check(results["rush_hour"]["traffic"]["label"] == "rush hour", "the plan says which traffic it was computed under")

    # ------------------------------------------------------------------------------------------------ 4
    scene("4. Real city with recorded real traffic: MG Road, Bengaluru (works offline)")
    city = timed("load the city (from the disk cache)", lambda: api.post("/api/graph/city", MG_ROAD))
    cid = city["summary"]["graph_id"]
    print(f"      {city['summary']['node_count']} intersections, {city['summary']['edge_count']} arcs; traffic starts as: {city['summary']['traffic']['label']}")
    check(city["summary"]["node_count"] > 300, "the real map loaded", f"{city['summary']['node_count']} intersections")
    snaps = api.get(f"/api/graph/{cid}/traffic/snapshots")
    check(len(snaps) >= 1, "a recorded TomTom snapshot exists for this map", f"{len(snaps)} found")
    free = api.post("/api/optimize", {"graph_id": cid, "n_stops": 12, "seed": 3})
    print("      free flow : " + summary_line(free))
    if snaps:
        replay = api.post(f"/api/graph/{cid}/congestion", {"mode": "snapshot", "snapshot_id": snaps[0]["id"]})
        tr = replay["summary"]["traffic"]
        print(f"      replaying : {snaps[0]['id']}  ->  badge says {tr['kind'].upper()} ({tr['provider']}, {tr['roads_measured']} of {tr['roads_total']} roads measured, captured {tr['captured_at']})")
        check(tr["kind"] == "recorded", "a replay is labelled RECORDED, never LIVE")
        recorded = api.post("/api/optimize", {"graph_id": cid, **problem_of(free), "seed": 3})
        print("      recorded  : " + summary_line(recorded))
        check(recorded["total_time_min"] >= free["total_time_min"] * 0.99, "real traffic is never quicker than free flow", f"{recorded['total_time_min'] / free['total_time_min'] - 1:+.0%}")

        # ------------------------------------------------------------------------------------------ 5
        scene("5. What to minimize: Fastest vs Shortest (distance only), on the recorded traffic")
        fast = recorded
        short = api.post("/api/optimize", {"graph_id": cid, **problem_of(free), "cost_weights": SHORTEST, "seed": 3})
        calm = api.post("/api/optimize", {"graph_id": cid, **problem_of(free), "cost_weights": AVOID_JAMS, "seed": 3})
        for name, plan in (("Fastest", fast), ("Shortest", short), ("Avoid jams", calm)):
            print(f"      {name:<11} {summary_line(plan)}")
        print(
            f"      -> Shortest: {short['total_distance_km'] / fast['total_distance_km'] - 1:+.0%} km, {short['total_time_min'] / fast['total_time_min'] - 1:+.0%} minutes, "
            f"{short['total_delay_min'] / max(fast['total_delay_min'], 1e-9) - 1:+.0%} congestion delay: it saves a little distance and drives into the jams (Finding 16)"
        )
        print(
            f"      -> Avoid jams is milder and noisy at this size: {calm['total_delay_min'] / max(fast['total_delay_min'], 1e-9) - 1:+.0%} delay, "
            f"{calm['total_time_min'] / fast['total_time_min'] - 1:+.0%} minutes; mention it, do not build the scene on it"
        )
        check(short["total_time_min"] >= fast["total_time_min"] * 0.99, "the distance-only plan is not quicker than the fastest one", warn_only=True)

        # ------------------------------------------------------------------------------------------ 6
        scene("6. Block a road (what-if) on that real map. Use the route search for this scene: it is steadier (Finding 19)")
        view = api.get(f"/api/graph/{cid}")
        stop_args = {**problem_of(free), "algorithm": "route_search", "time_limit_sec": 3, "seed": 3}
        open_plan = api.post("/api/optimize", {"graph_id": cid, **stop_args})
        print("      open roads: " + summary_line(open_plan))
        impacts = []
        for u, v in used_roads(open_plan, view)[:6]:
            api.put(f"/api/graph/{cid}/closures", {"roads": [[u, v]]})
            try:
                closed = api.post("/api/optimize", {"graph_id": cid, **stop_args})
            except RuntimeError as error:
                impacts.append((u, v, None, str(error)[:90]))
                continue
            finally:
                cut = api.get(f"/api/graph/{cid}")["cut_off"]
            impacts.append((u, v, closed["total_time_min"] / open_plan["total_time_min"] - 1, f"cut off: {cut}" if cut else ""))
        api.put(f"/api/graph/{cid}/closures", {"roads": []})
        for u, v, change, note in impacts:
            lat_lon = [(n[1], n[2]) for n in view["nodes"] if int(n[0]) in (u, v)]
            where = f"({lat_lon[0][0]:.4f}, {lat_lon[0][1]:.4f})" if lat_lon else ""
            print(f"      close road {u}-{v} {where}: " + (f"{change:+.1%} driving time" if change is not None else "plan failed") + (f"  {note}" if note else ""))
        worked = [c for _, _, c, _ in impacts if c is not None]
        check(len(used_roads(open_plan, view)) > 0, "found roads that the plan drives on")
        check(bool(worked) and max(worked) > 0.005, "closing a used road visibly costs time", f"largest {max(worked):+.1%}" if worked else "")
        check(api.get(f"/api/graph/{cid}")["closed"] == [], "reopening restores the map")

    # ------------------------------------------------------------------------------------------------ 7
    scene("7. Shortest path A -> B on the synthetic map: Dijkstra (exact) against the QPSO, PSO and GA searches")
    nodes = [int(n[0]) for n in synthetic["nodes"]]
    lat = {int(n[0]): n[1] for n in synthetic["nodes"]}
    a_node, b_node = min(nodes, key=lambda n: lat[n]), max(nodes, key=lambda n: lat[n])  # far apart, north to south
    path = api.post("/api/shortest-path", {"graph_id": sid, "source": a_node, "target": b_node, "algorithms": ["dijkstra", "qpso", "pso", "ga"], "seed": 1})
    for r in path["results"]:
        print(f"      {r['algorithm']:<9}{r['time_min']:>7.2f} min  {r['hops']:>3} segments  {'optimal' if r['gap_pct'] < 1e-9 else '+%.2f%%' % r['gap_pct']:>9}  {1000 * r['runtime_sec']:>8.1f} ms")
    check(all(r["gap_pct"] > -1e-9 for r in path["results"]), "no search beats Dijkstra (it is exact)")
    print("      -> honest reading: Dijkstra is exact and about a thousand times faster; the swarms are near-optimal, and QPSO is not better than PSO or the GA (Finding 18)")

    # ------------------------------------------------------------------------------------------------ 8
    scene("8. Time windows (short): ignoring them vs pricing lateness, 15 stops on the synthetic map")
    api.post(f"/api/graph/{sid}/congestion", {"mode": "random", "seed": 1})
    windows = {}
    for label, penalty in (("ignoring windows", 0.0), ("pricing lateness", 10.0)):
        windows[label] = api.post("/api/optimize", {"graph_id": sid, "n_stops": 15, "seed": 1, "random_windows": True, "service_time_min": 5, "time_window_penalty": penalty})
        p = windows[label]
        print(f"      {label:<17} {p['late_stops']} stops late, {p['total_late_min']:.0f} min late in total, {p['total_time_min']:.1f} min driving")
    check(windows["pricing lateness"]["total_late_min"] <= windows["ignoring windows"]["total_late_min"], "pricing lateness never leaves more lateness than ignoring it")

    # ------------------------------------------------------------------------------------------------ 9
    scene("9. Live traffic")
    if args.live:
        if not status["live_available"]:
            check(False, "live fetch needs a TomTom key in backend/.env")
        else:
            live = timed("fetch live TomTom traffic on MG Road (about 25 s)", lambda: api.post(f"/api/graph/{cid}/congestion", {"mode": "live"}))
            tr = live["summary"]["traffic"]
            print(f"      badge says {tr['kind'].upper()} ({tr['provider']}, {tr['roads_measured']} of {tr['roads_total']} roads measured)")
            check(tr["kind"] == "live", "a live fetch is labelled LIVE")
    else:
        print("      skipped (pass --live to fetch once; the recorded snapshot in scene 4 is the offline stand-in)")

    print(f"\nRehearsal took {time.perf_counter() - began:.0f} s. {len(failures)} check(s) failed, {len(warnings)} warning(s).")
    for what in failures:
        print("  FAILED:", what)
    for what in warnings:
        print("  warning:", what)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
