/**
 * Day 2 shell. Will render:
 *   - components/MapView        (Leaflet map: graph nodes/edges + optimized route overlay)
 *   - components/RouteControls  (source/destination/vehicle-constraint inputs -> /optimize)
 *   - components/BenchmarkChart (QPSO vs PSO vs GA vs exact, from /benchmark)
 *   - components/ConvergencePlot(best-cost-per-iteration curve)
 */
export default function App() {
  return (
    <div style={{ fontFamily: "sans-serif", padding: "1rem" }}>
      <h1>SIH26137 — Quantum-Inspired Traffic Route Optimization</h1>
      <p>Scaffold stage — see docs/ROADMAP.md.</p>
    </div>
  );
}
