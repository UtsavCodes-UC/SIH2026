import { useEffect, useState } from "react";
import type { Algorithm, CongestionMode, GraphView, PlaceSuggestion, Preset, SnapshotInfo, TrafficStatus } from "../api/types";
import { ALGORITHM_LABELS, formatCaptured } from "../lib/helpers";
import type { Busy, SolverParams } from "../lib/params";
import PlaceSearchBox from "./PlaceSearchBox";

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
  // presets carry their coordinates; a typed place name is looked up by the server
  onLoadCity: (body: { place: string; radius_m: number; lat?: number; lon?: number }) => void;
  onRandomStops: () => void;
  onClearStops: () => void;
  onOptimize: () => void;
  onBenchmark: () => void;
  onTraffic: (mode: CongestionMode, snapshotId?: string) => void;
  trafficStatus: TrafficStatus | null;
  snapshots: SnapshotInfo[];
  onSaveSnapshot: () => void;
}

const ALGORITHMS: Algorithm[] = ["qpso", "pso", "ga", "nearest_neighbor", "route_search"];

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
  const [customPlace, setCustomPlace] = useState("");
  const [chosen, setChosen] = useState<PlaceSuggestion | null>(null); // the suggestion the box text still stands for
  const idle = busy === null;
  const routeSearch = params.algorithm === "route_search";
  const isCity = graph?.summary.source === "city";
  const trafficKind = graph?.summary.traffic.kind;
  const canSave = trafficKind === "live" || trafficKind === "recorded";
  const [snapshotId, setSnapshotId] = useState("");
  useEffect(() => {
    if (!props.snapshots.some((x) => x.id === snapshotId)) setSnapshotId(props.snapshots[0]?.id ?? "");
  }, [props.snapshots, snapshotId]);
  const ready = graph !== null && depot !== null && stops.length > 0;
  const searching = presetIndex === presets.length; // the last dropdown entry: type any place
  const typed = customPlace.trim();
  const canLoad = idle && (searching ? typed.length >= 2 : presets.length > 0);

  function loadCity() {
    if (!canLoad) return;
    if (searching && chosen && chosen.label === typed) {
      props.onLoadCity({ place: chosen.label, lat: chosen.lat, lon: chosen.lon, radius_m: radius }); // exactly the spot that was picked
    } else if (searching) {
      props.onLoadCity({ place: typed, radius_m: radius }); // free text: the server looks it up
    } else {
      const p = presets[presetIndex];
      props.onLoadCity({ place: p.name, lat: p.lat, lon: p.lon, radius_m: radius });
    }
  }

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
                <option value={presets.length}>Search for another place…</option>
              </select>
            </label>
            {searching && (
              <div className="field">
                <label htmlFor="place-search">Place name</label>
                <PlaceSearchBox
                  id="place-search"
                  value={customPlace}
                  onChange={(text) => {
                    setCustomPlace(text);
                    if (chosen && text.trim() !== chosen.label) setChosen(null);
                  }}
                  onPick={(place) => {
                    setChosen(place);
                    setCustomPlace(place.label);
                  }}
                  onSubmit={loadCity}
                  near={isCity && graph ? { lat: graph.summary.center[0], lon: graph.summary.center[1] } : null}
                />
                {chosen && chosen.label === typed && (
                  <p className="hint picked">
                    ✓ Picked from the suggestions ({chosen.lat.toFixed(4)}, {chosen.lon.toFixed(4)}). Radius below, then Load.
                  </p>
                )}
              </div>
            )}
            <label>Radius (m){numberInput(radius, setRadius, 300, 4000, 100)}</label>
            <button className="btn" disabled={!canLoad} onClick={loadCity}>
              {busy === "graph" ? "Loading from OpenStreetMap…" : "Load road network"}
            </button>
            <p className="hint">
              {searching
                ? "Start typing and pick a suggestion, so the spelling is right and the map lands exactly there. Any place OpenStreetMap knows, anywhere in the world. Or press Enter to search for exactly what you typed. "
                : ""}
              The first load of a place downloads it from OpenStreetMap (up to a couple of minutes); later loads are instant.
            </p>
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
          <label className="grow">Random stops{numberInput(props.nStops, props.onNStops, 1, 150)}</label>
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
        {routeSearch ? (
          <>
            <div className="grid-2">
              <label title="How long the search may keep improving the routes. A small problem that stops improving finishes sooner.">
                Time limit (s){numberInput(params.timeLimit, (n) => onParams({ timeLimit: n }), 1, 60, 1)}
              </label>
              <label>Seed{numberInput(params.seed, (n) => onParams({ seed: n }), 0, 9999)}</label>
            </div>
            <p className="hint">
              Starts from a nearest-neighbour plan, then keeps moving, swapping and re-inserting stops between vans until the time limit. It uses no swarm and
              no separate polish. In our tests on synthetic road networks it found cheaper plans than QPSO with the polish at 15 to 100 stops
              (docs/BENCHMARKS.md, Finding 15). Built for several vans; with one van it is slow.
            </p>
          </>
        ) : (
          <>
            <div className="grid-2">
              <label>Particles{numberInput(params.nParticles, (n) => onParams({ nParticles: n }), 5, 200, 5)}</label>
              <label>Iterations{numberInput(params.nIterations, (n) => onParams({ nIterations: n }), 10, 3000, 50)}</label>
              <label>Seed{numberInput(params.seed, (n) => onParams({ seed: n }), 0, 9999)}</label>
            </div>
            <label className="check" title="Start the search with a nearest-neighbour route in its population. A random start cannot find good routes for 50+ stops; without this a large problem comes out far worse than a simple heuristic.">
              <input type="checkbox" checked={params.warmStart} onChange={(e) => onParams({ warmStart: e.target.checked })} />Warm start from a good route
            </label>
            <label className="check" title="After the search: fix crossing roads inside each route (2-opt), then move stops from one van to another whenever that saves time.">
              <input type="checkbox" checked={params.polish} onChange={(e) => onParams({ polish: e.target.checked })} />Polish routes (2-opt + move stops between vans)
            </label>
            {params.warmStart && stops.length > 0 && stops.length <= 20 && (
              <p className="hint">Tip: with few stops, turn warm start off to see the algorithms compete from scratch (that is where QPSO's edge shows).</p>
            )}
          </>
        )}
        <div className="row">
          <button className="btn grow" disabled={!idle || !ready} onClick={props.onOptimize}>
            {busy === "optimize" ? "Optimizing…" : "Optimize routes"}
          </button>
          <button
            className="btn btn-secondary"
            disabled={!idle || !ready}
            onClick={props.onBenchmark}
            title={routeSearch ? "Run every algorithm on this problem, including the route search, and compare" : "Run every algorithm on this problem and compare"}
          >
            {busy === "benchmark" ? "Running…" : "Benchmark"}
          </button>
        </div>
        <p className="hint">
          {routeSearch
            ? `Benchmark also runs the route search (up to ${params.timeLimit} s) next to QPSO, PSO, GA and nearest neighbour.`
            : "Benchmark compares QPSO, PSO, GA and nearest neighbour; choose Route search in the list to add it."}
        </p>
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
