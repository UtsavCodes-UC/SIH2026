// Mirrors backend/app/schemas/{graph,solve}.py

export type LatLng = [number, number];

export interface GraphSummary {
  graph_id: string;
  source: "synthetic" | "city";
  label: string;
  node_count: number;
  edge_count: number;
  center: LatLng;
  bounds: [LatLng, LatLng]; // [south, west], [north, east]
  mean_congestion: number;
}

export interface GraphView {
  summary: GraphSummary;
  nodes: [number, number, number][]; // id, lat, lon
  edges: [number, number, number][]; // u, v, congestion of the worse direction
}

export interface Preset {
  name: string;
  lat: number;
  lon: number;
}

export type Algorithm = "qpso" | "pso" | "ga" | "nearest_neighbor";
export type CongestionMode = "random" | "rush_hour" | "clear";

export interface ProblemSpec {
  graph_id: string;
  depot?: number | null;
  stops?: number[] | null;
  n_stops?: number;
  demands?: Record<string, number> | null;
  n_vehicles?: number | null;
  vehicle_capacity?: number;
  seed?: number | null;
}

export interface OptimizeRequest extends ProblemSpec {
  algorithm: Algorithm;
  n_particles: number;
  n_iterations: number;
  polish: boolean;
}

export interface BenchmarkRequest extends ProblemSpec {
  n_particles: number;
  n_iterations: number;
  polish: boolean;
}

export interface RouteOut {
  vehicle: number;
  nodes: number[]; // depot, stop, ..., depot
  path: LatLng[]; // polyline along the road network
  load: number;
  time_min: number;
  distance_km: number;
}

export interface ResolvedProblem {
  depot: number;
  stops: number[];
  demands: Record<string, number>;
  n_vehicles: number;
  vehicle_capacity: number;
}

export interface OptimizeResponse {
  graph_id: string;
  algorithm: Algorithm;
  problem: ResolvedProblem;
  routes: RouteOut[];
  total_time_min: number;
  total_distance_km: number;
  capacity_violation: number;
  feasible: boolean;
  raw_cost: number;
  cost: number;
  polished: boolean;
  convergence: number[];
  runtime_sec: number;
  iterations: number;
  warnings: string[];
}

export interface BenchmarkAlgorithm {
  name: string;
  raw_cost: number;
  time_min: number; // the raw result's travel time alone
  capacity_violation: number; // its total overload (0 = within capacity)
  polished_cost: number | null;
  raw_gap_pct: number | null;
  polished_gap_pct: number | null;
  runtime_sec: number;
  iterations: number;
  convergence: number[];
}

export interface BenchmarkResponse {
  graph_id: string;
  problem: ResolvedProblem;
  n_nodes: number;
  n_stops: number;
  exact_cost: number | null;
  algorithms: BenchmarkAlgorithm[];
  warnings: string[];
}
