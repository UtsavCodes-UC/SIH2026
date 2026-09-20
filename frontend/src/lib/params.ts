import type { Algorithm, CostWeights } from "../api/types";

/** How much each of the three things matters, as sliders from 0 to 100. Only the ratios count. */
export type WeightPercents = CostWeights;

export interface SolverParams {
  weights: WeightPercents;
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
  weights: { time: 100, distance: 0, congestion: 0 }, // minimize travel time, as always
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
