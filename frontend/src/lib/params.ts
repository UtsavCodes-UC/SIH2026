import type { Algorithm } from "../api/types";

export interface SolverParams {
  algorithm: Algorithm;
  nVehicles: number | null; // null = let the server size the fleet
  capacity: number;
  nParticles: number;
  nIterations: number;
  polish: boolean;
  warmStart: boolean;
  timeLimit: number; // seconds; route search only
  seed: number;
}

// The default solver is QPSO with a warm start and the polish. The route search is an option, not the default.
export const DEFAULT_PARAMS: SolverParams = {
  algorithm: "qpso",
  nVehicles: null,
  capacity: 100,
  nParticles: 40,
  nIterations: 800,
  polish: true,
  warmStart: true,
  timeLimit: 10,
  seed: 1,
};

export type Busy = null | "graph" | "optimize" | "benchmark" | "traffic" | "live";
