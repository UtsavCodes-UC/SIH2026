import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BenchmarkResponse } from "../api/types";
import { ALGORITHM_COLORS, ALGORITHM_LABELS, fmt } from "../lib/helpers";
import ConvergenceChart from "./ConvergenceChart";
import TrafficBadge from "./TrafficBadge";

export default function BenchmarkPanel({ benchmark }: { benchmark: BenchmarkResponse | null }) {
  if (!benchmark) {
    return <p className="empty">Press <strong>Benchmark</strong> to run every algorithm on the current problem and compare them.</p>;
  }

  const { algorithms } = benchmark;
  // The route search has no separate polish: its raw cost is its whole result. So when it is in the table the fair
  // comparison is each row's final cost (after the polish, where there is one), and that is what gets highlighted.
  const hasSearch = algorithms.some((a) => a.name === "route_search");
  const comparedCost = (a: (typeof algorithms)[number]) => (hasSearch ? a.polished_cost ?? a.raw_cost : a.raw_cost);
  const bestCost = Math.min(...algorithms.map(comparedCost));
  const hasGaps = algorithms.some((a) => a.raw_gap_pct !== null);
  const barData = algorithms.map((a) => ({
    name: ALGORITHM_LABELS[a.name] ?? a.name,
    raw: Number(a.raw_cost.toFixed(1)),
    polished: a.polished_cost === null ? undefined : Number(a.polished_cost.toFixed(1)),
  }));
  const curves = algorithms.filter((a) => a.convergence.length > 1);

  return (
    <div className="results">
      {benchmark.warnings.map((w) => (
        <p key={w} className="notice" role="alert">
          {w}
        </p>
      ))}
      <TrafficBadge info={benchmark.traffic} inline />
      <div className="results-body">
        <div>
          <table className="table">
            <thead>
              <tr>
                <th>Algorithm</th>
                <th className="num" title="what the algorithm itself found, no local search: travel time plus a heavy penalty for any capacity overload">Raw cost</th>
                <th className="num" title="travel time of the raw result, without the penalty">Travel (min)</th>
                <th className="num" title="total capacity overload of the raw result">Overload</th>
                {hasGaps && <th className="num">Gap to optimum</th>}
                <th className="num" title="the same result after the polish: 2-opt inside each route, then moving stops between vans">+ Polish cost</th>
                {hasGaps && <th className="num">Gap</th>}
                <th className="num">Time (s)</th>
              </tr>
            </thead>
            <tbody>
              {algorithms.map((a) => (
                <tr key={a.name} className={comparedCost(a) === bestCost ? "best" : undefined}>
                  <td>
                    <i className="swatch" style={{ background: ALGORITHM_COLORS[a.name] ?? "#888" }} />
                    {ALGORITHM_LABELS[a.name] ?? a.name}
                  </td>
                  <td className="num">{fmt(a.raw_cost)}</td>
                  <td className="num">{fmt(a.time_min)}</td>
                  <td className={a.capacity_violation > 0 ? "num warn" : "num"}>{a.capacity_violation > 0 ? fmt(a.capacity_violation, 0) : "—"}</td>
                  {hasGaps && <td className="num">{a.raw_gap_pct === null ? "—" : `${fmt(a.raw_gap_pct)}%`}</td>}
                  <td className="num">{a.polished_cost === null ? "—" : fmt(a.polished_cost)}</td>
                  {hasGaps && <td className="num">{a.polished_gap_pct === null ? "—" : `${fmt(a.polished_gap_pct)}%`}</td>}
                  <td className="num">{fmt(a.runtime_sec, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">
            {benchmark.n_stops} stops, {benchmark.problem.n_vehicles} vehicle{benchmark.problem.n_vehicles === 1 ? "" : "s"}.
            {benchmark.exact_cost === null ? " No exact optimum is computed for multi-vehicle or larger problems." : ` Exact optimum: ${fmt(benchmark.exact_cost)}.`} Lower is better. The
            raw column is the like-for-like algorithm comparison; the polish helps every method and narrows the differences.
            {benchmark.warm_start
              ? " Warm start is on: every search begins with the same nearest-neighbour route, which is fair but shrinks the gaps between them; turn it off to compare them from scratch."
              : " Warm start is off: every search begins from random routes."}
            {hasSearch &&
              " Route search has no separate polish (it starts from nearest neighbour and includes its own local search), so its cost is its whole result: compare it with the other rows' + Polish cost, not their raw cost. The highlighted row has the lowest of those final costs."}{" "}
            One problem instance is an illustration, not a statistical result.
          </p>
        </div>

        <div className="chart-grid">
          <div className="chart-card">
            <h3>Convergence (raw)</h3>
            <ConvergenceChart
              height={200}
              series={curves.map((a) => ({ name: ALGORITHM_LABELS[a.name] ?? a.name, values: a.convergence, color: ALGORITHM_COLORS[a.name] ?? "#888" }))}
            />
          </div>
          <div className="chart-card">
            <h3>Final cost: raw vs + polish</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={barData} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e3e7ec" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} />
                <YAxis tick={{ fontSize: 11 }} width={48} tickFormatter={(v: number) => fmt(v, 0)} />
                <Tooltip formatter={(v: number) => fmt(v, 1)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="raw" name="raw" fill="#d1495b" isAnimationActive={false} />
                <Bar dataKey="polished" name="+ polish" fill="#2e6f95" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
