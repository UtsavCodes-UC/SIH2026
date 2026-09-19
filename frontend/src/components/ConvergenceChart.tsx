import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { downsample, fmt } from "../lib/helpers";

export interface Series {
  name: string;
  values: number[];
  color: string;
}

export default function ConvergenceChart({ series, height = 220 }: { series: Series[]; height?: number }) {
  // merge the series into one row per iteration so the lines share an x axis
  const rows = new Map<number, Record<string, number>>();
  for (const s of series) {
    for (const { x, y } of downsample(s.values)) {
      rows.set(x, { ...(rows.get(x) ?? { x }), [s.name]: y });
    }
  }
  const data = [...rows.values()].sort((a, b) => a.x - b.x);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e3e7ec" />
        <XAxis dataKey="x" type="number" domain={[0, "dataMax"]} tick={{ fontSize: 11 }} label={{ value: "iteration", position: "insideBottomRight", offset: -2, fontSize: 11 }} />
        <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} width={52} tickFormatter={(v: number) => fmt(v, 0)} />
        <Tooltip formatter={(v: number) => fmt(v, 1)} labelFormatter={(l) => `iteration ${l}`} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s) => (
          <Line key={s.name} type="monotone" dataKey={s.name} stroke={s.color} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
