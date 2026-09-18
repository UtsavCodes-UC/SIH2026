# SIH26137 — Quantum-Inspired Intelligent Traffic Route Optimization

SIH 2026 prototype for **Problem Statement SIH26137**: a Quantum-Inspired
Metaheuristic Optimization framework (QPSO) that generates near-optimal
vehicle routes over a weighted transportation graph, benchmarked against
classical metaheuristics and exact methods.

## Repo layout

```
SIH2026/
├── backend/            FastAPI service: graph model, QPSO engine, baselines, benchmarking
│   ├── app/
│   │   ├── api/        REST endpoints
│   │   ├── core/       algorithms (qpso.py, baselines/, vrp_formulation.py, benchmark.py)
│   │   ├── data/       synthetic graph generator + OSMnx real-city loader
│   │   └── schemas/    Pydantic request/response models
│   └── tests/
├── frontend/            React + Leaflet UI: map view, route controls, benchmark charts
│   └── src/
│       ├── api/         backend client
│       ├── components/  MapView, RouteControls, BenchmarkChart, ConvergencePlot
│       └── pages/
└── docs/                 problem statement notes, math formulation, benchmark reports
```

## Status

Scaffold stage — see `docs/ROADMAP.md` for the 3-day phase plan.
