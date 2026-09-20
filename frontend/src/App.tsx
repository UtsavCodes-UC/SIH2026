import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  createCityGraph,
  createSyntheticGraph,
  errorMessage,
  getPresets,
  getTrafficStatus,
  listSnapshots,
  optimize,
  runBenchmark,
  saveSnapshot,
  setClosures,
  setCongestion,
  shortestPath,
} from "./api/client";
import type {
  BenchmarkResponse,
  CongestionMode,
  GraphView,
  OptimizeResponse,
  PathAlgorithm,
  Preset,
  ProblemSpec,
  ShortestPathResponse,
  SnapshotInfo,
  TimeWindow,
  TrafficStatus,
} from "./api/types";
import BenchmarkPanel from "./components/BenchmarkPanel";
import MapView, { type SelectMode } from "./components/MapView";
import PathPanel from "./components/PathPanel";
import ResultsPanel from "./components/ResultsPanel";
import Sidebar from "./components/Sidebar";
import { centralNode, fmt, normalizedWeights, sample } from "./lib/helpers";
import { type Busy, DEFAULT_PARAMS, type SolverParams } from "./lib/params";

const BUSY_LABEL: Record<Exclude<Busy, null>, string> = {
  graph: "Loading the road network…",
  optimize: "Optimizing routes…",
  benchmark: "Benchmarking every algorithm on this problem…",
  traffic: "Updating traffic…",
  live: "Fetching live traffic from TomTom (about 25 seconds)…",
  path: "Finding the route…",
};

/** One line of the what-if banner: how a plan or route changed when the roads did. */
function compare(subject: string, beforeMin: number, beforeKm: number, afterMin: number, afterKm: number, closing: boolean): string {
  const dMin = afterMin - beforeMin;
  if (Math.abs(dMin) < 0.05 && Math.abs(afterKm - beforeKm) < 0.005) return `${subject}: unchanged at ${fmt(afterMin)} min, ${fmt(afterKm)} km.`;
  const signed = (x: number, unit: string) => `${x >= 0 ? "+" : "-"}${fmt(Math.abs(x))} ${unit}`;
  const pct = beforeMin > 0 ? ` (${dMin >= 0 ? "+" : "-"}${fmt(Math.abs((100 * dMin) / beforeMin), 1)}%)` : "";
  const line = `${subject}: ${fmt(beforeMin)} → ${fmt(afterMin)} min, ${signed(dMin, "min")}${pct}; ${fmt(beforeKm)} → ${fmt(afterKm)} km.`;
  // Closing a road cannot shorten the best possible plan, so a saving means the earlier plan was not the best the search could find.
  return closing && dMin < -0.05 ? `${line} A closure cannot really save time: the earlier plan was not optimal (the search is heuristic and varies from run to run).` : line;
}

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(340);
  const [isResizing, setIsResizing] = useState(false);
  const [graph, setGraph] = useState<GraphView | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [depot, setDepot] = useState<number | null>(null);
  const [stops, setStops] = useState<number[]>([]);
  const [nStops, setNStops] = useState(15);
  const [selectMode, setSelectMode] = useState<SelectMode>("off");
  const [params, setParams] = useState<SolverParams>(DEFAULT_PARAMS);
  const [autoReoptimize, setAutoReoptimize] = useState(true);
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkResponse | null>(null);
  // Demands are drawn by the server on the first solve, then kept so that re-solving after a
  // traffic change is the *same* problem under different conditions.
  const [demands, setDemands] = useState<Record<string, number> | null>(null);
  // Demo time windows too: drawn by the server once, then kept for the same stops.
  const [windows, setWindows] = useState<Record<string, TimeWindow> | null>(null);
  // Shortest path between two chosen places, separate from the vehicle-routing problem.
  const [pathA, setPathA] = useState<number | null>(null);
  const [pathB, setPathB] = useState<number | null>(null);
  const [pathResult, setPathResult] = useState<ShortestPathResponse | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"results" | "benchmark" | "path">("results");
  const [panelState, setPanelState] = useState<"minimized" | "default" | "maximized">("default");
  const [panelHeight, setPanelHeight] = useState(320); // px, used when panelState === "default"
  const [dragging, setDragging] = useState(false);
  const bottomRef = useRef<HTMLElement | null>(null);
  const [trafficStatus, setTrafficStatus] = useState<TrafficStatus | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotInfo[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  // What the last road closure (or reopening) did to the plan and the route, shown until the next change.
  const [whatIf, setWhatIf] = useState<{ head: string; lines: string[] } | null>(null);
  // The plan and the route as they were with every road open, so each closure is compared with that and not with the previous click.
  const [openRoads, setOpenRoads] = useState<{ plan?: [number, number]; path?: [number, number] } | null>(null);

  async function run<T>(kind: Exclude<Busy, null>, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError(null);
    try {
      return await action();
    } catch (e) {
      setError(errorMessage(e));
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  const invalidate = () => {
    setResult(null);
    setBenchmark(null);
    setDemands(null);
    setWindows(null);
    setWhatIf(null);
    setOpenRoads(null);
  };

  function refreshSnapshots(view: GraphView) {
    if (view.summary.source !== "city") {
      setSnapshots([]);
      return;
    }
    listSnapshots(view.summary.graph_id).then(setSnapshots).catch(() => setSnapshots([]));
  }

  function adoptGraph(view: GraphView) {
    const nextDepot = centralNode(view.nodes);
    refreshSnapshots(view);
    setGraph(view);
    setPathA(null);
    setPathB(null);
    setPathResult(null);
    setDepot(nextDepot);
    setStops(sample(view.nodes.map((n) => n[0]).filter((id) => id !== nextDepot && !view.cut_off.includes(id)), nStops));
    invalidate();
  }

  useEffect(() => {
    getPresets().then(setPresets).catch(() => undefined);
    getTrafficStatus().then(setTrafficStatus).catch(() => undefined);
    run("graph", () => createSyntheticGraph({ n_nodes: 80, area_size_km: 8, seed: 1 })).then((view) => view && adoptGraph(view));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const patchParams = (patch: Partial<SolverParams>) => setParams((p) => ({ ...p, ...patch }));

  function problemBody(): ProblemSpec {
    const covered = demands !== null && stops.every((s) => String(s) in demands);
    const windowsCovered = windows !== null && stops.every((s) => String(s) in windows);
    return {
      graph_id: graph!.summary.graph_id,
      depot,
      stops,
      demands: covered ? demands : undefined,
      n_vehicles: params.nVehicles,
      vehicle_capacity: params.capacity,
      cost_weights: normalizedWeights(params.weights),
      ...(params.timeWindows ? { time_windows: windowsCovered ? windows : undefined, random_windows: !windowsCovered, service_time_min: params.serviceTime } : {}),
      seed: params.seed,
    };
  }

  const ready = graph !== null && depot !== null && stops.length > 0;

  // the route search runs for up to its time limit, so say so instead of a bare "Optimizing…"
  const busyLabel = (kind: Exclude<Busy, null>) =>
    params.algorithm === "route_search" && kind === "optimize"
      ? `Route search running (up to ${params.timeLimit} s)…`
      : params.algorithm === "route_search" && kind === "benchmark"
        ? `Benchmarking every algorithm, including the route search (up to ${params.timeLimit} s)…`
        : BUSY_LABEL[kind];

  async function doOptimize() {
    if (!ready) return;
    const out = await run("optimize", () =>
      optimize({
        ...problemBody(),
        algorithm: params.algorithm,
        n_particles: params.nParticles,
        n_iterations: params.nIterations,
        polish: params.polish,
        warm_start: params.warmStart,
        time_limit_sec: params.timeLimit,
      }),
    );
    if (out) {
      setResult(out);
      setDemands(out.problem.demands);
      setWindows(out.problem.time_windows);
      setTab("results");
    }
    return out;
  }

  async function doBenchmark() {
    if (!ready) return;
    const out = await run("benchmark", () =>
      runBenchmark({
        ...problemBody(),
        n_particles: params.nParticles,
        n_iterations: params.nIterations,
        polish: params.polish,
        warm_start: params.warmStart,
        include_route_search: params.algorithm === "route_search",
        time_limit_sec: params.timeLimit,
      }),
    );
    if (out) {
      setBenchmark(out);
      setDemands(out.problem.demands);
      setWindows(out.problem.time_windows);
      setTab("benchmark");
    }
  }

  async function doShortestPath(all: boolean) {
    if (!graph || pathA === null || pathB === null) return;
    const algorithms: PathAlgorithm[] = all ? ["dijkstra", "qpso", "pso", "ga"] : [params.pathAlgorithm];
    const out = await run("path", () =>
      shortestPath({
        graph_id: graph.summary.graph_id,
        source: pathA,
        target: pathB,
        algorithms,
        cost_weights: normalizedWeights(params.weights),
        n_particles: params.pathParticles,
        n_iterations: params.pathIterations,
        warm_start: true,
        seed: params.seed,
      }),
    );
    if (out) {
      setPathResult(out);
      setTab("path");
    }
    return out;
  }

  /** Close exactly these roads, then plan again so the effect is visible (when re-optimizing automatically is on). */
  async function changeClosures(roads: [number, number][]) {
    if (!graph) return;
    const planBefore = result;
    const pathBefore = pathResult;
    const pathTime = (r: ShortestPathResponse) => {
      const best = r.results.find((x) => x.algorithm === "dijkstra") ?? r.results[0];
      return [best.time_min, best.distance_km] as [number, number];
    };
    // with every road open now, remember how things stood; with closures already in force the baseline was taken earlier
    const base = graph.closed.length === 0
      ? { plan: planBefore ? ([planBefore.total_time_min, planBefore.total_distance_km] as [number, number]) : undefined, path: pathBefore ? pathTime(pathBefore) : undefined }
      : openRoads;
    const view = await run("traffic", () => setClosures(graph.summary.graph_id, roads));
    if (!view) return;
    setGraph(view);
    setWhatIf(null);
    setOpenRoads(view.closed.length > 0 ? base : null);
    if (!autoReoptimize) return;
    const n = view.closed.length;
    const lines: string[] = [];
    if (planBefore) {
      const out = await doOptimize();
      const fromOpen = n > 0 && base?.plan !== undefined;
      const was = fromOpen ? base!.plan! : ([planBefore.total_time_min, planBefore.total_distance_km] as [number, number]);
      if (out) lines.push(compare(fromOpen ? "Delivery plan, against all roads open" : "Delivery plan", was[0], was[1], out.total_time_min, out.total_distance_km, n > 0));
      else setResult(null); // the old plan drives on roads that are now closed
    }
    if (pathBefore) {
      const out = await doShortestPath(pathBefore.results.length > 1);
      const fromOpen = n > 0 && base?.path !== undefined;
      const was = fromOpen ? base!.path! : pathTime(pathBefore);
      if (out) {
        const now = pathTime(out);
        lines.push(compare(fromOpen ? "Route A to B, against all roads open" : "Route A to B", was[0], was[1], now[0], now[1], n > 0));
      } else setPathResult(null);
    }
    if (lines.length) setWhatIf({ head: n === 0 ? "All roads reopened" : `${n} road${n === 1 ? "" : "s"} closed`, lines });
  }

  function pickRoad(u: number, v: number, isClosed: boolean) {
    if (!graph || busy) return;
    const same = ([a, b]: [number, number]) => (a === u && b === v) || (a === v && b === u);
    changeClosures(isClosed ? graph.closed.filter((road) => !same(road)) : [...graph.closed, [u, v]]);
  }

  async function doTraffic(mode: CongestionMode, snapshotId?: string) {
    if (!graph) return;
    const view = await run(mode === "live" ? "live" : "traffic", () => setCongestion(graph.summary.graph_id, mode, params.seed, snapshotId));
    if (mode === "live") getTrafficStatus().then(setTrafficStatus).catch(() => undefined); // a key may have been added since the page loaded
    if (!view) return;
    setGraph(view);
    setWhatIf(null);
    setOpenRoads(null); // new traffic: the earlier open-road figures no longer describe the same conditions
    if (autoReoptimize && result) await doOptimize();
    if (autoReoptimize && pathResult) await doShortestPath(pathResult.results.length > 1);
  }

  async function doSaveSnapshot() {
    if (!graph) return;
    const saved = await run("traffic", () => saveSnapshot(graph.summary.graph_id));
    if (saved) {
      refreshSnapshots(graph);
      setNotice("Snapshot saved. You can replay it later, even offline.");
      window.setTimeout(() => setNotice(null), 5000);
    }
  }

  function pickNode(id: number) {
    if (selectMode === "pathA" || selectMode === "pathB") {
      (selectMode === "pathA" ? setPathA : setPathB)(id);
      setPathResult(null);
      return;
    }
    if (selectMode === "depot") {
      setDepot(id);
      setStops((s) => s.filter((x) => x !== id));
    } else if (selectMode === "stops") {
      if (id === depot) return;
      setStops((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
    } else {
      return;
    }
    invalidate();
  }

  function randomStops() {
    if (!graph) return;
    setStops(sample(graph.nodes.map((n) => n[0]).filter((id) => id !== depot && !graph.cut_off.includes(id)), nStops));
    invalidate();
  }

  function startResize(e: ReactMouseEvent<HTMLDivElement>) {
  e.preventDefault();
  const el = bottomRef.current;
  if (!el) return;

  const startY = e.clientY;
  const startHeight = el.getBoundingClientRect().height;
  // grabbing the handle always drops into free-drag mode, even from minimized/maximized —
  // same feel as dragging VS Code's collapsed terminal back open.
  setPanelHeight(startHeight);
  setPanelState("default");
  setDragging(true);

    const parentHeight = el.parentElement?.getBoundingClientRect().height ?? window.innerHeight;

  function onMove(ev: MouseEvent) {
    const delta = startY - ev.clientY; // dragging up = taller panel
    const maxH = parentHeight - 160;
    setPanelHeight(Math.min(Math.max(startHeight + delta, 100), Math.max(maxH, 160)));
  }
  function onUp() {
    setDragging(false);
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  }
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

  function toggleSidebar() {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
      setTimeout(() => window.dispatchEvent(new Event("resize")), 220);
      return next;
    });
  }

  return (
    <div
      className={`app ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${isResizing ? "is-resizing" : ""}`}
      style={{ "--sidebar-width": `${sidebarWidth}px` } as React.CSSProperties}
    >
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggleCollapsed={toggleSidebar}
        sidebarWidth={sidebarWidth}
        onResizeWidth={setSidebarWidth}
        isResizing={isResizing}
        onResizeActive={setIsResizing}
        graph={graph}
        presets={presets}
        busy={busy}
        depot={depot}
        stops={stops}
        nStops={nStops}
        onNStops={setNStops}
        params={params}
        onParams={patchParams}
        autoReoptimize={autoReoptimize}
        onAutoReoptimize={setAutoReoptimize}
        onCreateSynthetic={(body) => run("graph", () => createSyntheticGraph(body)).then((view) => view && adoptGraph(view))}
        onLoadCity={(body) => run("graph", () => createCityGraph(body)).then((view) => view && adoptGraph(view))}
        onRandomStops={randomStops}
        onClearStops={() => {
          setStops([]);
          invalidate();
        }}
        onOptimize={() => {
          setOpenRoads(null); // a deliberate new solve: earlier open-road figures may be for other settings
          doOptimize();
        }}
        onBenchmark={doBenchmark}
        pathA={pathA}
        pathB={pathB}
        onFindPath={(all) => {
          setOpenRoads((base) => (base ? { ...base, path: undefined } : base));
          doShortestPath(all);
        }}
        onTraffic={doTraffic}
        trafficStatus={trafficStatus}
        snapshots={snapshots}
        onSaveSnapshot={doSaveSnapshot}
        closedRoads={graph?.closed.length ?? 0}
        cutOff={graph?.cut_off.length ?? 0}
        onReopenAll={() => changeClosures([])}
      />

      <main className="main" data-panel={panelState}>
        <div className="map-area">
          {graph ? (
            <MapView
              graph={graph}
              depot={depot}
              stops={stops}
              demands={demands}
              result={tab === "path" ? null : result}
              pathA={pathA}
              pathB={pathB}
              pathResult={tab === "path" ? pathResult : null}
              selectMode={selectMode}
              onPickNode={pickNode}
              onPickRoad={pickRoad}
              onSelectMode={setSelectMode}
            />
          ) : (
            <div className="placeholder">{busy ? busyLabel(busy) : error ?? "No network loaded."}</div>
          )}
          {busy && graph && (
            <div className="banner busy" role="status">
              <span className="spinner" aria-hidden /> {busyLabel(busy)}
            </div>
          )}
          {whatIf && !busy && (
            <div className="banner whatif" role="status">
              <div>
                <strong>What-if · {whatIf.head}</strong>
                {whatIf.lines.map((line) => (
                  <div key={line}>{line}</div>
                ))}
              </div>
              <button className="banner-close" onClick={() => setWhatIf(null)} aria-label="Dismiss">
                ×
              </button>
            </div>
          )}
          {notice && (
            <div className="banner ok" role="status">
              {notice}
            </div>
          )}
          {error && (
            <div className="banner error" role="alert">
              {error}
              <button className="banner-close" onClick={() => setError(null)} aria-label="Dismiss">
                ×
              </button>
            </div>
          )}
        </div>

        <section
          className="bottom"
          ref={bottomRef}
          style={{
            height: panelState === "maximized" ? undefined : panelState === "minimized" ? 42 : panelHeight,
            transition: dragging ? "none" : "height 150ms ease",
          }}
        >
          <div
            className="panel-resize-handle"
            onMouseDown={startResize}
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize panel"
          />
          <div className="tabs" role="tablist">
            {(["results", "benchmark", "path"] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab tab-active" : "tab"} onClick={() => setTab(t)}>
                {t === "results" ? "Route plan" : t === "benchmark" ? "Algorithm benchmark" : "Shortest path"}
              </button>
            ))}
            <div className="panel-controls">
              <button
                type="button"
                className="panel-btn"
                title={panelState === "minimized" ? "Restore panel" : "Minimize panel"}
                aria-label={panelState === "minimized" ? "Restore panel" : "Minimize panel"}
                onClick={() => setPanelState((s) => (s === "minimized" ? "default" : "minimized"))}
              >
                {panelState === "minimized" ? "▢" : "—"}
              </button>
              <button
                type="button"
                className="panel-btn"
                title={panelState === "maximized" ? "Restore panel" : "Maximize panel"}
                aria-label={panelState === "maximized" ? "Restore panel" : "Maximize panel"}
                onClick={() => setPanelState((s) => (s === "maximized" ? "default" : "maximized"))}
              >
                {panelState === "maximized" ? "❐" : "▢"}
              </button>
            </div>
          </div>
          {panelState !== "minimized" && (
            <div className="bottom-scroll">
              {tab === "results" ? <ResultsPanel result={result} /> : tab === "benchmark" ? <BenchmarkPanel benchmark={benchmark} /> : <PathPanel response={pathResult} />}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
