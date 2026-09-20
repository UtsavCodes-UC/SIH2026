import type { ShortestPathResponse } from "../api/types";
import { PATH_COLORS, PATH_LABELS, describeWeights, fmt, isTimeOnly } from "../lib/helpers";
import ConvergenceChart from "./ConvergenceChart";
import TrafficBadge from "./TrafficBadge";

export default function PathPanel({ response }: { response: ShortestPathResponse | null }) {
  if (!response) {
    return (
      <p className="empty">
        Choose two places with <strong>set A</strong> and <strong>set B</strong> on the map, then press <strong>Find route</strong> or <strong>Compare all four</strong>.
      </p>
    );
  }

  const { results } = response;
  const shown = results.find((r) => r.algorithm === "dijkstra") ?? results[0];
  const timeOnly = isTimeOnly(response.cost_weights);
  const searches = results.filter((r) => r.algorithm !== "dijkstra" && r.convergence.length > 1);
  const curveLength = Math.max(0, ...searches.map((r) => r.convergence.length));
  const series = [
    ...searches.map((r) => ({ name: PATH_LABELS[r.algorithm], values: r.convergence, color: PATH_COLORS[r.algorithm] })),
    { name: PATH_LABELS.dijkstra, values: Array(curveLength).fill(response.exact_cost), color: PATH_COLORS.dijkstra },
  ];

  return (
    <div className="results">
      <TrafficBadge info={response.traffic} inline />
      <div className="kpis">
        <div className="kpi" title="Real minutes driving from A to B, congestion included">
          <span>Driving time</span>
          <strong>{fmt(shown.time_min)} min</strong>
          <small>{PATH_LABELS[shown.algorithm]}</small>
        </div>
        <div className="kpi">
          <span>Distance</span>
          <strong>{fmt(shown.distance_km)} km</strong>
        </div>
        <div className="kpi" title="Of the driving time, the minutes lost to congestion compared with free flow">
          <span>Congestion delay</span>
          <strong>{fmt(shown.delay_min)} min</strong>
        </div>
        <div className="kpi">
          <span>Road segments</span>
          <strong>{shown.hops}</strong>
        </div>
        <div className="kpi" title="The best possible cost for this pair, from Dijkstra">
          <span>Exact optimum</span>
          <strong>{fmt(response.exact_cost, 2)}</strong>
          <small>{timeOnly ? "minutes" : describeWeights(response.cost_weights)}</small>
        </div>
      </div>

      <div className="results-body">
        <div>
          <table className="table">
            <thead>
              <tr>
                <th>Method</th>
                <th className="num" title={timeOnly ? "minutes" : "the weighted cost that was minimized"}>Cost</th>
                <th className="num">Minutes</th>
                <th className="num">km</th>
                <th className="num" title="minutes lost to congestion">Delay</th>
                <th className="num">Segments</th>
                <th className="num" title="how far above the exact optimum this route's cost is">Above optimum</th>
                <th className="num">Time (ms)</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.algorithm} className={r.gap_pct <= 1e-9 ? "best" : undefined}>
                  <td>
                    <i className="swatch" style={{ background: PATH_COLORS[r.algorithm] }} />
                    {PATH_LABELS[r.algorithm]}
                  </td>
                  <td className="num">{fmt(r.cost, 2)}</td>
                  <td className="num">{fmt(r.time_min)}</td>
                  <td className="num">{fmt(r.distance_km)}</td>
                  <td className="num">{fmt(r.delay_min)}</td>
                  <td className="num">{r.hops}</td>
                  <td className={r.gap_pct > 1e-9 ? "num warn" : "num"}>{r.gap_pct > 1e-9 ? `+${fmt(r.gap_pct, 2)}%` : "optimal"}</td>
                  <td className="num">{fmt(1000 * r.runtime_sec, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">
            {!timeOnly && `Costs are the weighted blend (${describeWeights(response.cost_weights)}), not minutes. `}
            Dijkstra is exact and answers in milliseconds. The other methods search for the same route with random-key particles, so they can land
            above the optimum and are much slower; on the map the exact route is the wide line and each search a dotted line on top of it. Where a
            search is optimal its line hides on the exact one. See docs/BENCHMARKS.md, Finding 18.
          </p>
        </div>

        <div className="chart-card">
          <h3>Search progress — best cost per iteration</h3>
          {searches.length > 0 ? (
            <ConvergenceChart series={series} />
          ) : (
            <p className="empty">Dijkstra is exact: it finds the answer in one pass, so there is no convergence curve. Use Compare all four to see the searches.</p>
          )}
        </div>
      </div>
    </div>
  );
}
