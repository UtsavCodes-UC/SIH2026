# SIH26137 — Quantum-Inspired Intelligent Traffic Route Optimization

A quantum-inspired metaheuristic (**QPSO**, Quantum Particle Swarm Optimization) that plans
capacitated multi-vehicle routes over a weighted road graph with live, changeable traffic,
benchmarked against classical PSO, a genetic algorithm, a nearest-neighbour heuristic and an
exact solver. Includes a REST API and a map UI, on synthetic networks or real OpenStreetMap cities.

**Read [docs/BENCHMARKS.md](docs/BENCHMARKS.md) before quoting any performance number.** In short:
QPSO is a much stronger optimizer than classical PSO on its own (13-28% cheaper routes, p < 0.02),
but once both get a 2-opt local search the gap shrinks to +0.5-3.6% and is mostly not significant, and
with several vehicles the edge holds at ~20 customers, ties at 50 and reverses at 100.

## Run it

Needs Python 3.11 and Node 20+. From the repo root:

```bash
# backend (API on :8000)
cd backend
python -m venv .venv
source .venv/Scripts/activate          # Windows Git Bash; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt        # pins numpy 1.26.4 / networkx 3.3; results are reproducible only with these
python -m uvicorn app.main:app --port 8000

# frontend, in a second terminal (dev server on :5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. For a single-process deployment, run `npm run build` in `frontend/`:
the backend then serves the built UI itself at http://localhost:8000.

Real cities download from OpenStreetMap on first use (1-2 minutes) and are cached under
`backend/data/cache/`. To pre-download the preset places so a demo works offline:

```bash
cd backend && python scripts/warm_city_cache.py
```

## Using the UI

1. **Road network** — generate a synthetic network, or load a real place.
2. **Delivery problem** — draw random stops, or click the map ("set depot" / "toggle stops");
   set the fleet size (blank = auto) and vehicle capacity.
3. **Solver** — pick QPSO / PSO / GA / nearest neighbour and press *Optimize routes*: routes are drawn
   along the roads, numbered by visiting order, with per-vehicle load, time and distance and the
   search's convergence curve. *Benchmark* runs every algorithm on the same problem.
4. **Live traffic** — free flow / random / rush hour repaints the roads and (optionally) re-plans
   automatically, so you can watch routes detour around a jam.

## API

Interactive docs at http://localhost:8000/docs.

| Endpoint | Purpose |
|---|---|
| `POST /api/graph/synthetic` · `POST /api/graph/city` | create a network; returns nodes, roads and a `graph_id` |
| `GET /api/graph/presets` · `GET /api/graph/{id}` | ready-made places · read a network back |
| `POST /api/graph/{id}/congestion` | `random` / `rush_hour` / `clear`: the dynamic weight update |
| `POST /api/optimize` | solve one problem; routes come back as polylines along the roads |
| `POST /api/benchmark` | run every algorithm on one problem (raw and 2-opt-polished costs) |

Anything left out of a problem (depot, stops, demands, fleet size) is filled in from `seed` and
echoed back in the response, so the same problem can be re-solved after the traffic changes.

## Repo layout

```
backend/
  app/core/        graph model, VRP formulation + decoder, QPSO, baselines/, 2-opt, traffic, benchmark
  app/data/        synthetic graph generator, OSMnx city loader (with disk cache)
  app/services/    graph store, problem builder, solver dispatch, map/route views
  app/api/         FastAPI routers          app/schemas/   request/response models
  scripts/         benchmark CLIs (compare_qpso_vs_pso.py, compare_multi_vehicle.py, ...)
  tests/           pytest suite (run from backend/: python -m pytest tests/)
  results/         per-run CSVs behind the numbers in docs/BENCHMARKS.md
frontend/          React + TypeScript + Leaflet + Recharts map UI
docs/              BENCHMARKS.md (results and caveats)
```

## Status

Day 1 (engine, baselines, benchmarking) and Day 2 (multi-vehicle capacity model, REST API, OSM
loader, map UI) are done. Open for Day 3: closing QPSO's gap at 50-100 customers, time windows,
mathematical-formulation write-up, packaging (Docker) and demo polish.
