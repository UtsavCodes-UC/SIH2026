import { useEffect, useState } from "react";
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
  setCongestion,
} from "./api/client";
import type {
  BenchmarkResponse,
  CongestionMode,
  GraphView,
  OptimizeResponse,
  Preset,
  ProblemSpec,
  SnapshotInfo,
  TrafficStatus,
} from "./api/types";
import BenchmarkPanel from "./components/BenchmarkPanel";
import MapView, { type SelectMode } from "./components/MapView";
import ResultsPanel from "./components/ResultsPanel";
import Sidebar from "./components/Sidebar";
import { centralNode, sample } from "./lib/helpers";
import { type Busy, DEFAULT_PARAMS, type SolverParams } from "./lib/params";

const BUSY_LABEL: Record<Exclude<Busy, null>, string> = {
  graph: "Loading the road network…",
  optimize: "Optimizing routes…",
  benchmark: "Benchmarking every algorithm on this problem…",
  traffic: "Updating traffic…",
  live: "Fetching live traffic from TomTom (about 25 seconds)…",
};

export default function App() {
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
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"results" | "benchmark">("results");
  const [trafficStatus, setTrafficStatus] = useState<TrafficStatus | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotInfo[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

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
    setDepot(nextDepot);
    setStops(sample(view.nodes.map((n) => n[0]).filter((id) => id !== nextDepot), nStops));
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
    return {
      graph_id: graph!.summary.graph_id,
      depot,
      stops,
      demands: covered ? demands : undefined,
      n_vehicles: params.nVehicles,
      vehicle_capacity: params.capacity,
      seed: params.seed,
    };
  }

  const ready = graph !== null && depot !== null && stops.length > 0;

  async function doOptimize() {
    if (!ready) return;
    const out = await run("optimize", () =>
      optimize({ ...problemBody(), algorithm: params.algorithm, n_particles: params.nParticles, n_iterations: params.nIterations, polish: params.polish, warm_start: params.warmStart }),
    );
    if (out) {
      setResult(out);
      setDemands(out.problem.demands);
      setTab("results");
    }
  }

  async function doBenchmark() {
    if (!ready) return;
    const out = await run("benchmark", () =>
      runBenchmark({ ...problemBody(), n_particles: params.nParticles, n_iterations: params.nIterations, polish: params.polish, warm_start: params.warmStart }),
    );
    if (out) {
      setBenchmark(out);
      setDemands(out.problem.demands);
      setTab("benchmark");
    }
  }

  async function doTraffic(mode: CongestionMode, snapshotId?: string) {
    if (!graph) return;
    const view = await run(mode === "live" ? "live" : "traffic", () => setCongestion(graph.summary.graph_id, mode, params.seed, snapshotId));
    if (mode === "live") getTrafficStatus().then(setTrafficStatus).catch(() => undefined); // a key may have been added since the page loaded
    if (!view) return;
    setGraph(view);
    if (autoReoptimize && result) await doOptimize();
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
    setStops(sample(graph.nodes.map((n) => n[0]).filter((id) => id !== depot), nStops));
    invalidate();
  }

  return (
    <div className="app">
      <Sidebar
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
        onOptimize={doOptimize}
        onBenchmark={doBenchmark}
        onTraffic={doTraffic}
        trafficStatus={trafficStatus}
        snapshots={snapshots}
        onSaveSnapshot={doSaveSnapshot}
      />

      <main className="main">
        <div className="map-area">
          {graph ? (
            <MapView
              graph={graph}
              depot={depot}
              stops={stops}
              demands={demands}
              result={result}
              selectMode={selectMode}
              onPickNode={pickNode}
              onSelectMode={setSelectMode}
            />
          ) : (
            <div className="placeholder">{busy ? BUSY_LABEL[busy] : error ?? "No network loaded."}</div>
          )}
          {busy && graph && (
            <div className="banner busy" role="status">
              <span className="spinner" aria-hidden /> {BUSY_LABEL[busy]}
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

        <section className="bottom">
          <div className="tabs" role="tablist">
            {(["results", "benchmark"] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab tab-active" : "tab"} onClick={() => setTab(t)}>
                {t === "results" ? "Route plan" : "Algorithm benchmark"}
              </button>
            ))}
          </div>
          <div className="bottom-scroll">{tab === "results" ? <ResultsPanel result={result} /> : <BenchmarkPanel benchmark={benchmark} />}</div>
        </section>
      </main>
    </div>
  );
}
