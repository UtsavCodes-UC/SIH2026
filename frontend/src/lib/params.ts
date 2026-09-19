import type { Algorithm } from "../api/types";

export interface SolverParams {
  algorithm: Algorithm;
  nVehicles: number | null; // null = let the server size the fleet
  capacity: number;
  nParticles: number;
  nIterations: number;
  polish: boolean;
  warmStart: boolean;
  seed: number;
}

export const DEFAULT_PARAMS: SolverParams = {
  algorithm: "qpso",
  nVehicles: null,
  capacity: 100,
  nParticles: 40,
  nIterations: 800,
  polish: true,
  warmStart: true,
  seed: 1,
};

export type Busy = null | "graph" | "optimize" | "benchmark" | "traffic" | "live";
