import axios from "axios";
import type {
  BenchmarkRequest,
  BenchmarkResponse,
  CongestionMode,
  GraphView,
  OptimizeRequest,
  OptimizeResponse,
  PlaceSearchResult,
  Preset,
  SnapshotInfo,
  TrafficStatus,
} from "./types";

const http = axios.create({
  baseURL: "/api",
  timeout: 5 * 60 * 1000, // GA and first-time city downloads can take a while
});

/** Pulls a human-readable message out of a FastAPI error response (string or validation-error list). */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: (string | number)[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
        .join("; ");
    }
    if (error.code === "ECONNABORTED") return "The request timed out.";
    if (!error.response) return "Cannot reach the API. Is the backend running on port 8000?";
    return `Request failed (${error.response.status}).`;
  }
  return error instanceof Error ? error.message : String(error);
}

export const getPresets = () => http.get<Preset[]>("/graph/presets").then((r) => r.data);

/** Suggestions for a place name typed so far. Pass a signal so a newer keystroke can cancel the old request. */
export const searchPlaces = (q: string, signal?: AbortSignal, near?: { lat: number; lon: number } | null) =>
  http.get<PlaceSearchResult>("/graph/places", { params: { q, lat: near?.lat, lon: near?.lon }, signal, timeout: 15_000 }).then((r) => r.data);

export const createSyntheticGraph = (body: { n_nodes: number; area_size_km: number; seed: number }) =>
  http.post<GraphView>("/graph/synthetic", body).then((r) => r.data);

export const createCityGraph = (body: { lat?: number; lon?: number; radius_m: number; place?: string; refresh?: boolean }) =>
  http.post<GraphView>("/graph/city", body).then((r) => r.data);

export const setCongestion = (graphId: string, mode: CongestionMode, seed?: number, snapshotId?: string) =>
  http.post<GraphView>(`/graph/${graphId}/congestion`, { mode, seed, snapshot_id: snapshotId }).then((r) => r.data);

export const getTrafficStatus = () => http.get<TrafficStatus>("/traffic/status").then((r) => r.data);

export const listSnapshots = (graphId: string) =>
  http.get<SnapshotInfo[]>(`/graph/${graphId}/traffic/snapshots`).then((r) => r.data);

export const saveSnapshot = (graphId: string) =>
  http.post<SnapshotInfo>(`/graph/${graphId}/traffic/snapshots`).then((r) => r.data);

export const optimize = (body: OptimizeRequest) => http.post<OptimizeResponse>("/optimize", body).then((r) => r.data);

export const runBenchmark = (body: BenchmarkRequest) =>
  http.post<BenchmarkResponse>("/benchmark", body).then((r) => r.data);
