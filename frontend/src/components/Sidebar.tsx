import { useEffect, useState } from "react";
import type { Algorithm, CongestionMode, GraphView, Preset, SnapshotInfo, TrafficStatus } from "../api/types";
import { ALGORITHM_LABELS, formatCaptured } from "../lib/helpers";
import type { Busy, SolverParams } from "../lib/params";

interface Props {
  graph: GraphView | null;
  presets: Preset[];
  busy: Busy;
  depot: number | null;
  stops: number[];
  nStops: number;
  onNStops: (n: number) => void;
  params: SolverParams;
  onParams: (patch: Partial<SolverParams>) => void;
  autoReoptimize: boolean;
  onAutoReoptimize: (value: boolean) => void;
  onCreateSynthetic: (body: { n_nodes: number; area_size_km: number; seed: number }) => void;
  onLoadCity: (body: { lat: number; lon: number; radius_m: number; name: string }) => void;
  onRandomStops: () => void;
  onClearStops: () => void;
  onOptimize: () => void;
  onBenchmark: () => void;
  onTraffic: (mode: CongestionMode, snapshotId?: string) => void;
  trafficStatus: TrafficStatus | null;
  snapshots: SnapshotInfo[];
  onSaveSnapshot: () => void;
}

const ALGORITHMS: Algorithm[] = ["qpso", "pso", "ga", "nearest_neighbor"];

function numberInput(value: number, onChange: (n: number) => void, min: number, max: number, step = 1) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => {
        const n = Number(e.target.value);
        if (Number.isFinite(n)) onChange(Math.min(max, Math.max(min, n)));
      }}
    />
  );
}

export default function Sidebar(props: Props) {
  const { graph, presets, busy, depot, stops, params, onParams } = props;
  const [source, setSource] = useState<"synthetic" | "city">("synthetic");
  const [syn, setSyn] = useState({ n_nodes: 80, area_size_km: 8, seed: 1 });
  const [presetIndex, setPresetIndex] = useState(0);
  const [radius, setRadius] = useState(1200);
  const idle = busy === null;
  const isCity = graph?.summary.source === "city";
  const trafficKind = graph?.summary.traffic.kind;
  const canSave = trafficKind === "live" || trafficKind === "recorded";
  const [snapshotId, setSnapshotId] = useState("");
  useEffect(() => {
    if (!props.snapshots.some((x) => x.id === snapshotId)) setSnapshotId(props.snapshots[0]?.id ?? "");
  }, [props.snapshots, snapshotId]);
  const ready = graph !== null && depot !== null && stops.length > 0;

  return (
    <aside className="sidebar">
      <header className="brand">
        <h1>Quantum-inspired route optimizer</h1>
        <p>SIH26137 · QPSO for traffic-aware vehicle routing</p>
      </header>

      <section>
        <h2>1 · Road network</h2>
        <div className="tabs" role="tablist">
          {(["synthetic", "city"] as const).map((s) => (
            <button key={s} role="tab" aria-selected={source === s} className={source === s ? "tab tab-active" : "tab"} onClick={() => setSource(s)}>
              {s === "synthetic" ? "Synthetic" : "Real city"}
            </button>
          ))}
        </div>

        {source === "synthetic" ? (
          <>
            <div className="grid-2">
              <label>Intersections{numberInput(syn.n_nodes, (n) => setSyn({ ...syn, n_nodes: n }), 10, 300)}</label>
              <label>Area (km){numberInput(syn.area_size_km, (n) => setSyn({ ...syn, area_size_km: n }), 1, 50)}</label>
              <label>Seed{numberInput(syn.seed, (n) => setSyn({ ...syn, seed: n }), 0, 9999)}</label>
            </div>
            <button className="btn" disabled={!idle} onClick={() => props.onCreateSynthetic(syn)}>
              {busy === "graph" ? "Generating…" : "Generate network"}
            </button>
          </>
        ) : (
          <>
            <label>
              Place
              <select value={presetIndex} onChange={(e) => setPresetIndex(Number(e.target.value))}>
                {presets.map((p, i) => (
                  <option key={p.name} value={i}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>Radius (m){numberInput(radius, setRadius, 300, 4000, 100)}</label>
            <button
              className="btn"
              disabled={!idle || presets.length === 0}
              onClick={() => props.onLoadCity({ lat: presets[presetIndex].lat, lon: presets[presetIndex].lon, radius_m: radius, name: presets[presetIndex].name })}
            >
              {busy === "graph" ? "Loading from OpenStreetMap…" : "Load road network"}
            </button>
            <p className="hint">The first load of a place downloads it from OpenStreetMap (up to a couple of minutes); later loads are instant.</p>
          </>
        )}

        {graph && (
          <p className="graph-info">
            <strong>{graph.summary.label}</strong>
            <br />
            {graph.summary.node_count} intersections · {graph.edges.length} roads · mean congestion ×{graph.summary.mean_congestion.toFixed(2)}
          </p>
        )}
      </section>

      <section>
        <h2>2 · Delivery problem</h2>
        <p className="hint">
          Depot: <strong>{depot ?? "—"}</strong> · Stops: <strong>{stops.length}</strong>. Use the map toolbar to click a depot or stops, or draw a random set.
        </p>
        <div className="row">
          <label className="grow">Random stops{numberInput(props.nStops, props.onNStops, 1, 80)}</label>
          <button className="btn btn-secondary" disabled={!idle || !graph} onClick={props.onRandomStops}>
            Draw
          </button>
          <button className="btn btn-ghost" disabled={!idle || stops.length === 0} onClick={props.onClearStops}>
            Clear
          </button>
        </div>
        <div className="grid-2">
          <label>
            Vehicles
            <input
              type="number"
              min={1}
              max={40}
              placeholder="auto"
              value={params.nVehicles ?? ""}
              onChange={(e) => onParams({ nVehicles: e.target.value === "" ? null : Math.max(1, Math.min(40, Number(e.target.value))) })}
            />
          </label>
          <label>Capacity{numberInput(params.capacity, (n) => onParams({ capacity: n }), 10, 1000, 10)}</label>
        </div>
        <p className="hint">Demands are random (5–25 per stop). Leave vehicles empty to size the fleet for ~85% utilization.</p>
      </section>

      <section>
        <h2>3 · Solver</h2>
        <label>
          Algorithm
          <select value={params.algorithm} onChange={(e) => onParams({ algorithm: e.target.value as Algorithm })}>
            {ALGORITHMS.map((a) => (
              <option key={a} value={a}>
                {ALGORITHM_LABELS[a]}
              </option>
            ))}
          </select>
        </label>
        <div className="grid-2">
          <label>Particles{numberInput(params.nParticles, (n) => onParams({ nParticles: n }), 5, 200, 5)}</label>
          <label>Iterations{numberInput(params.nIterations, (n) => onParams({ nIterations: n }), 10, 3000, 50)}</label>
          <label>Seed{numberInput(params.seed, (n) => onParams({ seed: n }), 0, 9999)}</label>
        </div>
        <label className="check">
          <input type="checkbox" checked={params.polish} onChange={(e) => onParams({ polish: e.target.checked })} />2-opt polish on each route
        </label>
        <div className="row">
          <button className="btn grow" disabled={!idle || !ready} onClick={props.onOptimize}>
            {busy === "optimize" ? "Optimizing…" : "Optimize routes"}
          </button>
          <button className="btn btn-secondary" disabled={!idle || !ready} onClick={props.onBenchmark} title="Run every algorithm on this problem and compare">
            {busy === "benchmark" ? "Running…" : "Benchmark"}
          </button>
        </div>
      </section>

      <section>
        <h2>4 · Traffic</h2>
        <p className="hint">Simulated conditions, for any network:</p>
        <div className="row">
          {(
            [
              ["clear", "Free flow"],
              ["random", "Random"],
              ["rush_hour", "Rush hour"],
            ] as const
          ).map(([mode, label]) => (
            <button key={mode} className="btn btn-secondary grow" disabled={!idle || !graph} onClick={() => props.onTraffic(mode)}>
              {busy === "traffic" ? "…" : label}
            </button>
          ))}
        </div>

        <h3 className="subhead">Real traffic (TomTom)</h3>
        <div className="row">
          <button className="btn grow" disabled={!idle || !isCity} onClick={() => props.onTraffic("live")}>
            {busy === "live" ? "Fetching…" : "Fetch live traffic"}
          </button>
          <button className="btn btn-secondary" disabled={!idle || !canSave} onClick={props.onSaveSnapshot} title="Record the current real traffic so it can be replayed later, even offline">
            Save snapshot
          </button>
        </div>
        {props.snapshots.length > 0 && (
          <div className="row">
            <label className="grow">
              Recorded traffic
              <select value={snapshotId} onChange={(e) => setSnapshotId(e.target.value)}>
                {props.snapshots.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.captured_at ? formatCaptured(x.captured_at) : x.id}
                    {x.roads_measured !== null ? ` · ${x.roads_measured} roads` : ""}
                  </option>
                ))}
              </select>
            </label>
            <button className="btn btn-secondary" disabled={!idle || !snapshotId} onClick={() => props.onTraffic("snapshot", snapshotId)}>
              Replay
            </button>
          </div>
        )}
        {!isCity && <p className="hint">Real traffic works on real-city networks: use the Real city tab.</p>}
        {isCity && props.trafficStatus && !props.trafficStatus.live_available && (
          <p className="hint">
            No TomTom key found. Add <code>TOMTOM_API_KEY</code> to <code>backend/.env</code>, then press Fetch. Recorded traffic can still be replayed.
          </p>
        )}
        {isCity && props.trafficStatus?.live_available && (
          <p className="hint">
            Asks TomTom about roads across the map (about 25 seconds). Presses within {Math.round(props.trafficStatus.min_interval_sec / 60)} minutes reuse the last reading, to save the free daily quota.
          </p>
        )}

        <label className="check">
          <input type="checkbox" checked={props.autoReoptimize} onChange={(e) => props.onAutoReoptimize(e.target.checked)} />
          Re-optimize automatically after traffic changes
        </label>
      </section>
    </aside>
  );
}
