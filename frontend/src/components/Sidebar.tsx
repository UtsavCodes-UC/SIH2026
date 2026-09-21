import { useEffect, useRef, useState } from "react";
import type { Algorithm, CongestionMode, DeploymentInfo, GraphView, PathAlgorithm, PlaceSuggestion, Preset, SnapshotInfo, TrafficStatus } from "../api/types";
import { ALGORITHM_LABELS, PATH_LABELS, formatCaptured } from "../lib/helpers";
import type { Busy, SolverParams } from "../lib/params";
import PlaceSearchBox from "./PlaceSearchBox";
import AboutPanel from "./AboutPanel";
import Logo from "./Logo";

interface Props {
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  sidebarWidth?: number;
  onResizeWidth?: (width: number) => void;
  isResizing?: boolean;
  onResizeActive?: (active: boolean) => void;
  graph: GraphView | null;
  presets: Preset[];
  deployment: DeploymentInfo | null;
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
  pathA: number | null;
  pathB: number | null;
  onFindPath: (all: boolean) => void;
  onTraffic: (mode: CongestionMode, snapshotId?: string) => void;
  trafficStatus: TrafficStatus | null;
  snapshots: SnapshotInfo[];
  onSaveSnapshot: () => void;
  closedRoads: number;
  cutOff: number;
  onReopenAll: () => void;
}

const ALGORITHMS: Algorithm[] = ["qpso", "pso", "ga", "nearest_neighbor", "route_search"];

const PATH_ALGORITHMS: PathAlgorithm[] = ["dijkstra", "qpso", "pso", "ga"];

const WEIGHT_LABELS = { time: "Travel time", distance: "Distance", congestion: "Congestion" } as const;
const WEIGHT_HELP = {
  time: "Minutes spent driving, congestion included",
  distance: "Kilometres driven",
  congestion: "Minutes lost to congestion: how much longer the roads take than in free flow",
} as const;
const WEIGHT_PRESETS = [
  { name: "Fastest", title: "Minimize travel time only (the default)", weights: { time: 100, distance: 0, congestion: 0 } },
  { name: "Shortest", title: "Minimize kilometres driven", weights: { time: 0, distance: 100, congestion: 0 } },
  { name: "Avoid jams", title: "Half travel time, half congestion delay", weights: { time: 50, distance: 0, congestion: 50 } },
  { name: "Balanced", title: "40% time, 30% distance, 30% congestion", weights: { time: 40, distance: 30, congestion: 30 } },
];

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
  const [aboutOpen, setAboutOpen] = useState(false);
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
  // On a free demo host only the ready-made places load, up to a capped radius (see the note under the Load button).
  const maxRadius = props.deployment?.max_radius_m ?? null;
  const overLimit = maxRadius !== null && radius > maxRadius;
  const otherPlaceBlocked = props.deployment?.presets_only === true && searching;
  const canLoad = idle && !overLimit && !otherPlaceBlocked && (searching ? typed.length >= 2 : presets.length > 0);

  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const collapsed = props.collapsed ?? internalCollapsed;
  const toggleCollapsed = () => {
    if (props.onToggleCollapsed) {
      props.onToggleCollapsed();
    } else {
      setInternalCollapsed((c) => !c);
      setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
    }
  };

  function handleSectionClick(sectionId: string) {
    if (collapsed) {
      toggleCollapsed();
      setTimeout(() => {
        const el = document.getElementById(sectionId);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 100);
    }
  }

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

  const resizingRef = useRef(false);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || collapsed) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    resizingRef.current = true;
    props.onResizeActive?.(true);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!resizingRef.current) return;
    e.preventDefault();
    const maxAllowed = Math.min(520, Math.max(320, window.innerWidth - 200));
    const nextWidth = Math.min(maxAllowed, Math.max(320, e.clientX));
    props.onResizeWidth?.(nextWidth);
    window.dispatchEvent(new Event("resize"));
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!resizingRef.current) return;
    resizingRef.current = false;
    props.onResizeActive?.(false);
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // safe ignore
    }
    window.dispatchEvent(new Event("resize"));
  };

  const handleDoubleClick = () => {
    if (collapsed) return;
    props.onResizeWidth?.(340);
    window.dispatchEvent(new Event("resize"));
  };

  useEffect(() => {
    if (!props.isResizing) return;
    const onWindowPointerUp = () => {
      if (resizingRef.current) {
        resizingRef.current = false;
        props.onResizeActive?.(false);
        window.dispatchEvent(new Event("resize"));
      }
    };
    window.addEventListener("pointerup", onWindowPointerUp);
    window.addEventListener("pointercancel", onWindowPointerUp);
    return () => {
      window.removeEventListener("pointerup", onWindowPointerUp);
      window.removeEventListener("pointercancel", onWindowPointerUp);
    };
  }, [props.isResizing, props.onResizeActive]);

  return (
    <aside className="sidebar">
      <div className="sidebar-sticky-header">
        <header className="brand">
          <div className="brand-title-row">
            <button
              type="button"
              className="sidebar-toggle-btn"
              onClick={toggleCollapsed}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect width="18" height="18" x="3" y="3" rx="2" />
                  <path d="M9 3v18" />
                  <path d="m13 15 3-3-3-3" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect width="18" height="18" x="3" y="3" rx="2" />
                  <path d="M9 3v18" />
                  <path d="m14 9-3 3 3 3" />
                </svg>
              )}
            </button>
            <Logo size={34} />
            <div className="brand-text">
              <h1>QuantumRoute</h1>
              <p>Quantum-inspired route optimizer</p>
            </div>
          </div>
        </header>

        <button className="about-bar" onClick={() => setAboutOpen((open) => !open)} title="How to use this app, with screenshots">
          <span className="about-bar-icon">?</span>
          <span className="about-bar-label">Guide</span>
          <span className="about-bar-chevron">›</span>
        </button>
      </div>

      {aboutOpen && <AboutPanel onClose={() => setAboutOpen(false)} />}

      <nav className="sidebar-collapsed-nav" aria-label="Collapsed navigation">
        <button
          type="button"
          className="rail-item"
          onClick={() => setAboutOpen((open) => !open)}
          title="Guide"
          aria-label="Guide"
        >
          <span className="rail-icon">?</span>
        </button>
        <button
          type="button"
          className="rail-item"
          onClick={() => handleSectionClick("section-road-network")}
          title="Road Network"
          aria-label="Road Network"
        >
          <span className="rail-icon">◉</span>
        </button>
        <button
          type="button"
          className="rail-item"
          onClick={() => handleSectionClick("section-delivery-problem")}
          title="Delivery Problem"
          aria-label="Delivery Problem"
        >
          <span className="rail-icon">◇</span>
        </button>
        <button
          type="button"
          className="rail-item"
          onClick={() => handleSectionClick("section-solver")}
          title="Solver"
          aria-label="Solver"
        >
          <span className="rail-icon">⚙</span>
        </button>
        <button
          type="button"
          className="rail-item"
          onClick={() => handleSectionClick("section-traffic")}
          title="Traffic"
          aria-label="Traffic"
        >
          <span className="rail-icon">≋</span>
        </button>
        <button
          type="button"
          className="rail-item"
          onClick={() => handleSectionClick("section-shortest-path")}
          title="Shortest Path"
          aria-label="Shortest Path"
        >
          <span className="rail-icon">↗</span>
        </button>
      </nav>

      <section id="section-road-network">
        <h2><span className="section-num">01</span> · Road network</h2>
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
              The ready-made places load at once at any radius up to 2000 m. Any other place, or a bigger radius, is downloaded from OpenStreetMap the
              first time (up to a couple of minutes, longer on a slow server); later loads are instant.
            </p>
            {props.deployment?.limit_note && (
              <p className={overLimit || otherPlaceBlocked ? "hosted-note over" : "hosted-note"} role={overLimit || otherPlaceBlocked ? "alert" : undefined}>
                <strong>
                  {overLimit
                    ? `Radius ${radius} m is above this demo's ${maxRadius} m limit.`
                    : otherPlaceBlocked
                      ? "Other places can't be loaded on this demo server."
                      : "Demo server limits."}
                </strong>{" "}
                {props.deployment.limit_note}
              </p>
            )}
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

      <section id="section-delivery-problem">
        <h2><span className="section-num">02</span> · Delivery problem</h2>
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
        <label
          className="check"
          title="Give every stop a time window: the earliest and latest minute a van may serve it. Vans leave the depot at minute 0."
        >
          <input
            type="checkbox"
            checked={params.timeWindows}
            onChange={(e) => onParams({ timeWindows: e.target.checked, ...(e.target.checked && params.algorithm === "route_search" ? { algorithm: "qpso" as Algorithm } : {}) })}
          />
          Time windows (demo)
        </label>
        {params.timeWindows && (
          <>
            <label>Service time per stop (min){numberInput(params.serviceTime, (n) => onParams({ serviceTime: n }), 0, 60, 1)}</label>
            <p className="hint">
              Each stop gets a random window 30–60 minutes wide, opening up to 80 minutes after the quickest a van could get there. A van that arrives
              early waits; one that arrives late is charged 10 per minute. Route search cannot handle windows yet, and the polish is only kept when it does
              not make the plan later.
            </p>
          </>
        )}
      </section>

      <section id="section-solver">
        <h2><span className="section-num">03</span> · Solver</h2>
        <h3 className="subhead">What to minimize</h3>
        <div className="grid-2 presets">
          {WEIGHT_PRESETS.map((p) => (
            <button key={p.name} className="btn btn-secondary" disabled={!idle} title={p.title} onClick={() => onParams({ weights: p.weights })}>
              {p.name}
            </button>
          ))}
        </div>
        {(["time", "distance", "congestion"] as const).map((key) => {
          const total = params.weights.time + params.weights.distance + params.weights.congestion;
          return (
            <label key={key} className="weight" title={WEIGHT_HELP[key]}>
              <span>
                {WEIGHT_LABELS[key]} <strong>{total > 0 ? Math.round((100 * params.weights[key]) / total) : 0}%</strong>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={params.weights[key]}
                onChange={(e) => {
                  const next = { ...params.weights, [key]: Number(e.target.value) };
                  if (next.time + next.distance + next.congestion > 0) onParams({ weights: next }); // something must stay to minimize
                }}
              />
            </label>
          );
        })}
        <p className="hint">
          Time is minutes driven, distance is kilometres, congestion is the minutes lost to jams compared with free flow. The optimizer minimizes
          the weighted blend; the results always show the real minutes, kilometres and delay.
          {params.weights.congestion > 0 && graph && graph.summary.mean_congestion <= 1 && " The map is at free flow, so there is no congestion to avoid."}
        </p>
        <label>
          Algorithm
          <select value={params.algorithm} onChange={(e) => onParams({ algorithm: e.target.value as Algorithm })}>
            {ALGORITHMS.map((a) => (
              <option key={a} value={a} disabled={a === "route_search" && params.timeWindows}>
                {ALGORITHM_LABELS[a]}
                {a === "route_search" && params.timeWindows ? " (no time windows yet)" : ""}
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

      <section id="section-traffic">
        <h2><span className="section-num">04</span> · Traffic</h2>
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
          Re-optimize automatically after traffic or road changes
        </label>

        <h3 className="subhead">Road closures (what-if)</h3>
        <p className="hint">
          Press <strong>block road</strong> on the map toolbar, then click a road to close it; click a closed road to reopen it. Plans and
          routes avoid closed roads, and a banner shows what the closure cost.
        </p>
        <div className="row">
          <span className="grow graph-info inline">
            Closed roads: <strong>{props.closedRoads}</strong>
          </span>
          <button className="btn btn-secondary" disabled={!idle || props.closedRoads === 0} onClick={props.onReopenAll}>
            Reopen all
          </button>
        </div>
        {props.cutOff > 0 && (
          <p className="hint warn">
            {props.cutOff} intersection{props.cutOff === 1 ? " is" : "s are"} cut off from the rest of the network (red circles on the map). Stops there
            cannot be served.
          </p>
        )}
      </section>

      <section id="section-shortest-path">
        <h2><span className="section-num">05</span> · Shortest path</h2>
        <p className="hint">
          The cheapest way between two places, for the same "What to minimize" as above. Press <strong>set A</strong> or <strong>set B</strong> on the
          map toolbar, then click the map.
        </p>
        <p className="graph-info inline">
          A: <strong>{props.pathA ?? "—"}</strong> · B: <strong>{props.pathB ?? "—"}</strong>
        </p>
        <label>
          Method
          <select value={params.pathAlgorithm} onChange={(e) => onParams({ pathAlgorithm: e.target.value as PathAlgorithm })}>
            {PATH_ALGORITHMS.map((a) => (
              <option key={a} value={a}>
                {PATH_LABELS[a]}
              </option>
            ))}
          </select>
        </label>
        {params.pathAlgorithm !== "dijkstra" && (
          <div className="grid-2">
            <label>Particles{numberInput(params.pathParticles, (n) => onParams({ pathParticles: n }), 5, 200, 5)}</label>
            <label>Iterations{numberInput(params.pathIterations, (n) => onParams({ pathIterations: n }), 10, 3000, 50)}</label>
          </div>
        )}
        <div className="row">
          <button className="btn grow" disabled={!idle || props.pathA === null || props.pathB === null} onClick={() => props.onFindPath(false)}>
            {busy === "path" ? "Searching…" : "Find route"}
          </button>
          <button
            className="btn btn-secondary"
            disabled={!idle || props.pathA === null || props.pathB === null}
            onClick={() => props.onFindPath(true)}
            title="Run Dijkstra, QPSO, classical PSO and the genetic algorithm on this pair and compare them"
          >
            Compare all four
          </button>
        </div>
        <p className="hint">Dijkstra is exact and takes milliseconds. The other three search for the same route with particles, so they can end above the optimum.</p>
      </section>

      {!collapsed && (
        <div
          className={`sidebar-resizer ${props.isResizing ? "is-dragging" : ""}`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onDoubleClick={handleDoubleClick}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sidebar width"
          title="Drag to resize sidebar width (double-click to reset)"
        >
          <div className="sidebar-resizer-grip" />
        </div>
      )}
    </aside>
  );
}
