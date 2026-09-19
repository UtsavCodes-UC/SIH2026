import type { GraphView, LatLng } from "../api/types";

/** Okabe-Ito colour-blind-safe palette (yellow dropped: too faint on a light map). */
export const VEHICLE_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#7A3E9D", "#333333"];

export const vehicleColor = (index: number) => VEHICLE_COLORS[index % VEHICLE_COLORS.length];

export const ALGORITHM_LABELS: Record<string, string> = {
  qpso: "QPSO",
  pso: "Classical PSO",
  classical_pso: "Classical PSO",
  ga: "Genetic algorithm",
  genetic_algorithm: "Genetic algorithm",
  nearest_neighbor: "Nearest neighbour",
  held_karp_exact: "Exact (Held-Karp)",
};

export const ALGORITHM_COLORS: Record<string, string> = {
  qpso: "#d1495b",
  classical_pso: "#2e6f95",
  genetic_algorithm: "#3c8d5a",
  nearest_neighbor: "#8a8f98",
  held_karp_exact: "#1b1b1e",
};

export interface CongestionBucket {
  min: number;
  color: string;
  weight: number;
  label: string;
}

export const CONGESTION_BUCKETS: CongestionBucket[] = [
  { min: 0, color: "#a9b4bf", weight: 2, label: "free flow" },
  { min: 1.2, color: "#e8b923", weight: 2.5, label: "busy" },
  { min: 1.8, color: "#ef8a2b", weight: 3, label: "slow" },
  { min: 2.4, color: "#d7263d", weight: 3.5, label: "jammed" },
];

export function bucketIndex(congestion: number): number {
  let index = 0;
  CONGESTION_BUCKETS.forEach((b, i) => {
    if (congestion >= b.min) index = i;
  });
  return index;
}

/** Node nearest the centroid of the network: a sensible default depot. */
export function centralNode(nodes: GraphView["nodes"]): number {
  const lat = nodes.reduce((s, n) => s + n[1], 0) / nodes.length;
  const lon = nodes.reduce((s, n) => s + n[2], 0) / nodes.length;
  let best = nodes[0][0];
  let bestDistance = Infinity;
  for (const [id, la, lo] of nodes) {
    const d = (la - lat) ** 2 + (lo - lon) ** 2;
    if (d < bestDistance) {
      bestDistance = d;
      best = id;
    }
  }
  return best;
}

/** Random sample without replacement (partial Fisher-Yates). */
export function sample<T>(items: T[], count: number): T[] {
  const pool = items.slice();
  const n = Math.min(count, pool.length);
  for (let i = 0; i < n; i++) {
    const j = i + Math.floor(Math.random() * (pool.length - i));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, n);
}

export function coordinateIndex(nodes: GraphView["nodes"]): Map<number, LatLng> {
  return new Map(nodes.map(([id, lat, lon]) => [id, [lat, lon] as LatLng]));
}

export const fmt = (value: number, digits = 1) => value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });

/** "Sat 19 Sep, 6:15 pm" in the viewer's own time zone. */
export function formatCaptured(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

/** Keeps a chart responsive: at most `max` evenly spaced points, always including the last. */
export function downsample(values: number[], max = 240): { x: number; y: number }[] {
  if (values.length <= max) return values.map((y, x) => ({ x, y }));
  const step = (values.length - 1) / (max - 1);
  return Array.from({ length: max }, (_, i) => {
    const x = Math.round(i * step);
    return { x, y: values[x] };
  });
}
