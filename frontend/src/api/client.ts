import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
});

// Day 2: getGraph(), loadCity(name), optimizeRoute(request), runBenchmark(config)
