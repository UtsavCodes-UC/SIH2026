import type { OptimizeResponse } from "../api/types";
import { ALGORITHM_COLORS, ALGORITHM_LABELS, fmt, vehicleColor } from "../lib/helpers";
import ConvergenceChart from "./ConvergenceChart";
import TrafficBadge from "./TrafficBadge";

export default function ResultsPanel({ result }: { result: OptimizeResponse | null }) {
  if (!result) {
    return <p className="empty">Pick a network, choose a depot and stops, then press <strong>Optimize routes</strong>.</p>;
  }

  const { problem, routes } = result;
  const gain = result.polished && result.raw_cost > 0 ? (1 - result.cost / result.raw_cost) * 100 : null;
  // Vehicles drive in parallel, so the job is done when the slowest one is home.
  const finishMin = Math.max(...routes.map((r) => r.time_min));

  return (
    <div className="results">
      {result.warnings.map((w) => (
        <p key={w} className="notice" role="alert">
          {w}
        </p>
      ))}
      <TrafficBadge info={result.traffic} inline />
      <div className="kpis">
        <div className="kpi" title="All vans' driving minutes added together: what the optimizer minimizes (a cost measure)">
          <span>Total driving, all vans</span>
          <strong>{fmt(result.total_time_min)} min</strong>
          <small>sum · what we minimize</small>
        </div>
        <div className="kpi" title="The vans drive at the same time, so the job ends when the longest route is finished">
          <span>Job finishes in</span>
          <strong>{fmt(finishMin)} min</strong>
          <small>longest van · driving only</small>
        </div>
        <div className="kpi">
          <span>Total distance</span>
          <strong>{fmt(result.total_distance_km)} km</strong>
        </div>
        <div className="kpi">
          <span>Vehicles used</span>
          <strong>
            {routes.length} / {problem.n_vehicles}
          </strong>
        </div>
        <div className="kpi">
          <span>Capacity</span>
          <strong className={result.feasible ? "ok" : "warn"}>{result.feasible ? "all respected" : `over by ${fmt(result.capacity_violation, 0)}`}</strong>
        </div>
        <div className="kpi">
          <span>{ALGORITHM_LABELS[result.algorithm]} solve time</span>
          <strong>{fmt(result.runtime_sec, 2)} s</strong>
        </div>
        {gain !== null && (
          <div className="kpi">
            <span>Polish saved</span>
            <strong>{fmt(gain)}%</strong>
          </div>
        )}
      </div>

      <div className="results-body">
        <div>
          <table className="table">
            <thead>
              <tr>
                <th>Vehicle</th>
                <th className="num">Stops</th>
                <th className="num">Load / cap.</th>
                <th className="num">Time (min)</th>
                <th className="num">Distance (km)</th>
              </tr>
            </thead>
            <tbody>
              {routes.map((r) => (
                <tr key={r.vehicle}>
                  <td>
                    <i className="swatch" style={{ background: vehicleColor(r.vehicle - 1) }} />
                    {r.vehicle}
                  </td>
                  <td className="num">{r.nodes.length - 2}</td>
                  <td className={r.load > problem.vehicle_capacity ? "num warn" : "num"}>
                    {fmt(r.load, 0)} / {fmt(problem.vehicle_capacity, 0)}
                  </td>
                  <td className={r.time_min === finishMin && routes.length > 1 ? "num longest" : "num"} title={r.time_min === finishMin && routes.length > 1 ? "the longest route: sets when the job finishes" : undefined}>
                    {fmt(r.time_min)}
                  </td>
                  <td className="num">{fmt(r.distance_km)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {routes.length > 1 && (
            <p className="hint">
              The vans drive at the same time, so the job ends when the longest route (<strong>bold</strong>) is finished. Loading and unloading time is not counted.
            </p>
          )}
        </div>

        <div className="chart-card">
          <h3>Search progress — best cost per iteration</h3>
          {result.convergence.length > 1 ? (
            <ConvergenceChart series={[{ name: ALGORITHM_LABELS[result.algorithm], values: result.convergence, color: ALGORITHM_COLORS[result.algorithm === "pso" ? "classical_pso" : result.algorithm === "ga" ? "genetic_algorithm" : result.algorithm] ?? "#d1495b" }]} />
          ) : (
            <p className="empty">{ALGORITHM_LABELS[result.algorithm]} builds its answer in one pass, so there is no convergence curve.</p>
          )}
          <p className="hint">Cost = travel time in minutes plus a heavy penalty for any capacity overload. The curve is the algorithm's own result, before the polish{result.warm_start ? "; it starts from a nearest-neighbour route, so it begins low" : ""}.</p>
        </div>
      </div>
    </div>
  );
}
