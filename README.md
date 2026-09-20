# SIH26137 — Quantum-Inspired Intelligent Traffic Route Optimization

A quantum-inspired metaheuristic (**QPSO**, Quantum Particle Swarm Optimization) that plans
capacitated multi-vehicle routes over a weighted road graph with live, changeable traffic,
benchmarked against classical PSO, a genetic algorithm, a nearest-neighbour heuristic and an
exact solver. Includes a REST API and a map UI, on synthetic networks or real OpenStreetMap cities.

**Read [docs/BENCHMARKS.md](docs/BENCHMARKS.md) before quoting any performance number.** In short:
QPSO is a much stronger optimizer than classical PSO on its own (13-28% cheaper routes, p < 0.02),
but once both get a 2-opt local search the gap shrinks to +0.5-3.6% and is mostly not significant. With
several vehicles QPSO's edge over PSO holds at ~20 customers and ties at 50; at 100 a jump size that
shrinks with problem size wins it back against a random-start PSO, but a genetic algorithm is stronger
than either from a random start, and what really makes 100 customers work is the pipeline around the
search: a warm start from a nearest-neighbour route plus a polish that moves stops between vans (40%
lower cost at 100 customers than before; Finding 10). A hybrid QPSO (elite archive, 2-opt, restarts) lands within
about 3% of OR-Tools on 100-stop single-vehicle tours, but a hybrid PSO built the same way does exactly as well
(Finding 11). On the multi-vehicle problem our pipelines are still about 6-9% above OR-Tools' 60 s solution, and
an optimal split decoder closes only about 1% of that (Finding 12; the OR-Tools references were corrected, see there).
What does close it is a stronger search between vans (2-opt\*, SWAP\*, neighbour lists, iterated local search): 2.6% below the
OR-Tools 60 s solution in about 10 s on 100 customers, and starting it from a QPSO, PSO or GA adds nothing (Finding 13).
On the standard CVRPLIB instances with proven optima (100-199 customers) it averages 2.9% above optimal after 10 s and
1.5% after two minutes, against 5.5% for OR-Tools and 10.2% for the app's earlier default (Finding 14); it is not a
state-of-the-art solver. Do not read this as "QPSO scales best".

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

1. **Road network** — generate a synthetic network, or load a real place: pick one of the four presets,
   or choose *Search for another place…* and start typing: suggestions appear as you type (arrow keys +
   Enter, or click), so the spelling is right and the map lands exactly on the spot you picked. Enter
   without picking searches for exactly what you typed. A place you loaded once is remembered and
   suggested again later, even without the internet.
2. **Delivery problem** — draw random stops, or click the map ("set depot" / "toggle stops");
   set the fleet size (blank = auto) and vehicle capacity.
3. **Solver** — pick QPSO / PSO / GA / nearest neighbour and press *Optimize routes*: routes are drawn
   along the roads, numbered by visiting order, with per-vehicle load, time and distance and the
   search's convergence curve. *Benchmark* runs every algorithm on the same problem. Two options are on
   by default: *Warm start* (the search begins with a nearest-neighbour route in its population; needed
   from about 50 stops, and switch it off to watch the algorithms compete from scratch) and *Polish
   routes* (2-opt inside each route, then moving stops between vans). Up to 150 stops.
4. **Traffic** — free flow / random / rush hour repaints the roads and (optionally) re-plans
   automatically, so you can watch routes detour around a jam. On a real city, *Fetch live traffic*
   loads real TomTom readings instead (see below). A badge on the map and on every result always says
   where the congestion came from: LIVE, RECORDED, SIMULATED or FREE FLOW.

## Place suggestions

The suggestions come from [Photon](https://photon.komoot.io), a search-as-you-type service built on
OpenStreetMap data (© OpenStreetMap contributors). OpenStreetMap's own Nominatim server is used only for
the final exact lookup, because its usage policy forbids auto-complete requests. What you type is sent
to Photon after a 300 ms pause and cached for an hour; it is a free shared service, so for heavy use
run your own Photon and set `PLACE_SEARCH_URL` in `backend/.env`, or set it to `off` to keep only the
ready-made and remembered places. If Photon is unreachable the box still lists those places, says so,
and Enter still searches for what you typed. When a real city is loaded, results near it rank first
(a typo like "indiranagr" finds Bengaluru's Indiranagar before other cities'), without hiding places
elsewhere.

## Live traffic (TomTom)

The Real city tab can use real congestion instead of simulated. The backend samples about 80 roads
across the map, asks TomTom's *Traffic Flow* API for each road's current and free-flow speed, turns
each into a slowdown factor, applies it to every road along the reported segment, and estimates the
roads nobody measured from their measured neighbours (same road class counts most). Measured on MG
Road, Bengaluru: 541 of 1,223 roads got a direct reading, and the fetch took about 24 seconds.

**One-time setup** (free, no credit card):

1. Create an account at https://developer.tomtom.com and open *Keys → Create key*.
2. Under *Self-service APIs* tick **Traffic API** and **Traffic Flow API** (add **Traffic Incidents API**
   if you later want road closures). Leave the Orbis and map-tile products unticked.
3. Leave **Domain whitelisting OFF**. The backend calls TomTom server-to-server, which sends no browser
   Referer header, so a whitelisted key is rejected with HTTP 403.
4. Copy `backend/.env.example` to `backend/.env` and set `TOMTOM_API_KEY=...`. It is read on every
   request, so no restart is needed. `.env` is git-ignored: never commit a key.
5. Check it: `cd backend && python scripts/check_tomtom.py` (one request; never prints the key).

**Demo without depending on the internet.** Live means "right now", which may not be rush hour. Fetch
at a busy time, press *Save snapshot*, and later pick that snapshot and press *Replay*. A replay is
always labelled RECORDED with its original timestamp, never LIVE. Snapshots live in
`backend/data/traffic_snapshots/` (git-ignored, tied to the exact downloaded map); check TomTom's terms
before redistributing them.

**Limits to know about.** The free plan allows 2,500 non-tile requests a day and one refresh spends
about 80, so presses within 5 minutes reuse the last reading (`LIVE_TRAFFIC_MIN_INTERVAL_SEC`). Roads
without a reading are estimates, not measurements; the badge reports "N of M roads measured". Traffic
data © TomTom (the badge carries the credit). Live traffic is refused on synthetic maps, whose roads
are not real streets.

## API

Interactive docs at http://localhost:8000/docs.

| Endpoint | Purpose |
|---|---|
| `POST /api/graph/synthetic` · `POST /api/graph/city` | create a network (a city from `place` or `lat`/`lon` + `radius_m`); returns nodes, roads and a `graph_id`. An unknown place is a 422 with advice, a failed lookup a 503 |
| `GET /api/graph/presets` · `GET /api/graph/{id}` | ready-made places · read a network back |
| `GET /api/graph/places?q=` | place-name suggestions (optional `lat`/`lon` to prefer results near a map): presets and remembered places first, then Photon |
| `POST /api/graph/{id}/congestion` | `random` / `rush_hour` / `clear` (simulated), `live` (TomTom, real cities), `snapshot` (replay a recording): the dynamic weight update |
| `GET /api/traffic/status` | whether a TomTom key is configured (never returns the key) |
| `GET` · `POST /api/graph/{id}/traffic/snapshots` | list recorded traffic for a map · record the current real traffic |
| `POST /api/optimize` | solve one problem; routes come back as polylines along the roads |
| `POST /api/benchmark` | run every algorithm on one problem (raw and 2-opt-polished costs) |

Anything left out of a problem (depot, stops, demands, fleet size) is filled in from `seed` and
echoed back in the response, so the same problem can be re-solved after the traffic changes.

## Repo layout

```
backend/
  app/core/        graph model, VRP formulation + decoder, QPSO, hybrid_swarm, route_search, baselines/, 2-opt, traffic, live_traffic, benchmark
  app/data/        synthetic graph generator, OSMnx city loader (with disk cache), TomTom adapter, place-name suggestions, CVRPLIB benchmark adapter
  app/services/    graph store, problem builder, solver dispatch, map/route views, live traffic, snapshots
  app/api/         FastAPI routers          app/schemas/   request/response models
  scripts/         benchmark CLIs (compare_qpso_vs_pso.py, scale_experiments.py, hybrid_experiments.py, decoder_analysis.py, ortools_reference.py, route_search_experiments.py, route_search_ablation.py, cvrplib_benchmark.py, fetch_cvrplib.py, ...), check_tomtom.py, warm_city_cache.py
  tests/           pytest suite (run from backend/: python -m pytest tests/)
  results/         per-run CSVs behind the numbers in docs/BENCHMARKS.md
frontend/          React + TypeScript + Leaflet + Recharts map UI
docs/              BENCHMARKS.md (results and caveats)
```

## Status

Day 1 (engine, baselines, benchmarking), Day 2 (multi-vehicle capacity model, REST API, OSM loader,
map UI, live TomTom traffic with recorded snapshots) and the first part of Day 3 (scaling to 100
customers: warm start, a size-aware QPSO jump, a polish that moves stops between vans) are done.
The hybrid engine, the optimal split decoder and the stronger route search (Findings 11-13) are
built and benchmarked but not yet wired into the API or the UI.
Still open for Day 3: the mathematical-formulation write-up, "block a road" what-if events, a
time / distance / fuel cost model, Docker packaging and the demo script.
