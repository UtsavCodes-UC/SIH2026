# Reference

Details behind the [README](../README.md): running the app, what each control does, live traffic, the REST API, hosting and the code layout.
Results are in [BENCHMARKS.md](BENCHMARKS.md), the mathematics in [MATH_FORMULATION.md](MATH_FORMULATION.md).

1. [Running the app](#1-running-the-app)
2. [Using the interface](#2-using-the-interface)
3. [Live traffic (TomTom)](#3-live-traffic-tomtom)
4. [REST API](#4-rest-api)
5. [Hosting](#5-hosting)
6. [Code layout](#6-code-layout)

## 1. Running the app

### With Docker

One container serves the API and the built interface on one port.

```bash
docker compose up --build          # http://localhost:8000
PORT=8080 docker compose up --build   # if 8000 is taken (PowerShell: $env:PORT=8080; docker compose up --build)
```

- After changing code, `docker compose up -d --build` rebuilds. Dependency layers are cached, so an interface-only change takes seconds.
- Live traffic: put `TOMTOM_API_KEY=...` in `backend/.env` (optional). The key is passed in when the container starts and is never copied into the image.
- Downloaded maps (`backend/data/cache/`) and saved traffic (`backend/data/traffic_snapshots/`) are mounted from the host, so they survive rebuilds.
  On Linux create both folders first so they belong to you.
- The container runs one worker on purpose: loaded maps and their traffic live in that process's memory.
- Tests inside the image: `docker compose run --rm app python -m pytest tests -q`. Stop with `docker compose down`.

### Without Docker

Needs Python 3.11 and Node 20+.

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt        # numpy 1.26.4 and networkx 3.3 are pinned; the benchmark numbers reproduce only with these
python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173, proxies /api to the backend
```

`npm run build` in `frontend/` makes the backend serve the interface itself on port 8000.

### Maps

The four ready-made cities ship in `backend/data/presets/` (1200 m and 2000 m, OpenStreetMap data, ODbL) and load at once, with no
download. Any smaller radius is cut from the 2000 m map without internet; on the MG Road map a 1300 m cut has 1049 intersections against
1045 in a fresh download. Other places and larger radii are downloaded from OpenStreetMap on first use (one to two minutes), trying four
public Overpass servers in turn, and are cached. To prepare places for offline use: `cd backend && python scripts/warm_city_cache.py`.

## 2. Using the interface

The **Guide** button at the top of the sidebar walks through every control with screenshots. The images are in `frontend/public/guide/`;
regenerate them with `cd frontend && BASE=http://127.0.0.1:8000 npm run guide:screenshots` (needs Node 22+ and Chrome).

**1. Road network.** Generate a synthetic city, or load a real place: choose a ready-made city, or *Search for another place* and type.
Suggestions appear as you type, so the map lands exactly on the spot you pick. A place you loaded once is remembered, even offline.

**2. Delivery problem.** Draw random stops or click the map (*set depot*, *toggle stops*), set the number of vans (blank means automatic) and their
capacity, up to 150 stops. *Time windows* gives every stop an earliest and latest minute; early vans wait, late arrivals are charged per minute,
and the results show each stop's arrival against its window. Windows work with QPSO, PSO, GA and nearest neighbour, not with the route search.

**3. Solver.**
- *What to minimize*: travel time (default), distance, congestion delay (minutes lost to jams compared with free flow), or a blend, with the
  presets *Fastest*, *Shortest*, *Avoid jams*, *Balanced* or three sliders. Results always show real minutes, kilometres and delay.
- *Algorithm*: QPSO (default), PSO, genetic algorithm, nearest neighbour, or *route search*. *Optimize routes* draws the routes along the roads,
  numbered by visiting order, with each van's load, time and distance and the convergence curve. *Benchmark* runs every algorithm on the same problem.
- *Warm start* (the swarm begins with a nearest-neighbour route in its population; needed from about 50 stops) and *Polish routes* (2-opt inside each
  route, then moving stops between vans) are on by default.
- *Route search* starts from a nearest-neighbour plan and keeps moving, swapping and re-inserting stops between vans until its time limit (10 s by
  default). It uses no swarm and is built for several vans. Evidence: BENCHMARKS.md, Findings 13 to 15.

**4. Traffic.** Free flow, random and rush hour repaint the roads and can re-plan automatically. On a real city, *Fetch live traffic* loads TomTom readings,
and *Replay* plays back a recording. A badge on the map and on every result says where the congestion came from: LIVE, RECORDED, SIMULATED or FREE FLOW.

**Road closures.** *block road* in the map toolbar closes the road you click (red with a cross); click it again or press *Reopen all* to reopen.
A closed road is removed from the network, so every plan and route goes around it. With automatic re-optimizing on, a banner shows what the closures
cost against the same plan with every road open. A stop that closures cut off cannot be served, and the app names it. The search is heuristic, so a
closure can occasionally appear to save time; the banner says so (BENCHMARKS.md, Finding 19).

**5. Shortest path.** Press *set A* and *set B* on the map, pick a method, then *Find route* or *Compare all four*. Dijkstra is exact and takes milliseconds.
QPSO, PSO and the genetic algorithm search for the same route with particles, and the table reports how far above the exact optimum each ended
(BENCHMARKS.md, Finding 18).

**Place suggestions** come from [Photon](https://photon.komoot.io) (OpenStreetMap data), with OpenStreetMap's Nominatim used only for the final exact lookup.
Typing is sent to Photon after a 300 ms pause and cached for an hour. Set `PLACE_SEARCH_URL` in `backend/.env` to use your own Photon, or `off` to keep only
ready-made and remembered places.

## 3. Live traffic (TomTom)

The backend samples about 80 roads across the map and asks TomTom's Traffic Flow API for each road's current and free-flow speed. Each reading becomes a
slowdown factor for the road along the reported segment, and roads nobody measured are estimated from measured neighbours of the same class. On MG Road,
Bengaluru, 541 of 1,223 roads got a direct reading and the fetch took about 24 seconds. The badge always reports "N of M roads measured".

**Setup** (free, no card):
1. Create a key at https://developer.tomtom.com with the *Traffic API* and *Traffic Flow API* products, and domain whitelisting off (the backend calls TomTom
   server to server, which sends no Referer header).
2. Copy `backend/.env.example` to `backend/.env` and set `TOMTOM_API_KEY=...`. It is read on every request. `.env` is git-ignored.
3. Check it: `cd backend && python scripts/check_tomtom.py` (one request, never prints the key).

**Recorded traffic.** Fetch at a busy time, press *Save snapshot*, and replay it later without internet. A replay is always labelled RECORDED with its original
timestamp. One MG Road recording (541 of 1,223 roads measured, 19 September 2026, 6:23 pm) ships in `backend/data/recorded_traffic/`.

**Limits.** The free plan allows 2,500 requests a day and one refresh uses about 80, so presses within five minutes reuse the last reading.
Live traffic is refused on synthetic maps, whose roads are not real streets. Traffic data © TomTom.

## 4. REST API

Interactive documentation is at `/docs` on the running server.

| Endpoint | Purpose |
|---|---|
| `POST /api/graph/synthetic`, `POST /api/graph/city` | Create a network (a city from `place` or `lat`/`lon` plus `radius_m`). Returns nodes, roads and a `graph_id`. |
| `GET /api/graph/presets`, `GET /api/graph/{id}` | Ready-made places; read a network back. |
| `GET /api/graph/places?q=` | Place-name suggestions: ready-made and remembered places first, then Photon. |
| `POST /api/graph/{id}/congestion` | `random`, `rush_hour`, `clear` (simulated), `live` (TomTom), `snapshot` (replay): the dynamic weight update. |
| `PUT /api/graph/{id}/closures` | Block roads. The body `{"roads": [[u, v], ...]}` is the complete set of closed roads; `[]` reopens everything. The view lists `closed` roads and `cut_off` intersections. |
| `GET /api/traffic/status` | Whether a TomTom key is configured (never returns the key). |
| `GET`, `POST /api/graph/{id}/traffic/snapshots` | List recordings for a map; record the current real traffic. |
| `POST /api/optimize` | Solve one problem. `algorithm` is `qpso` (default), `pso`, `ga`, `nearest_neighbor` or `route_search` (which takes `time_limit_sec`, 1 to 60). Routes come back as road polylines. |
| `POST /api/benchmark` | Run every algorithm on one problem, raw and 2-opt-polished; `include_route_search` adds the route search. |
| `POST /api/shortest-path` | Quickest route between two intersections. Dijkstra is always computed as the exact reference and every result carries its `gap_pct` above it. |
| `GET /api/config` | Where the server runs (see Hosting). |

- **Cost weights.** Both solve endpoints take `cost_weights` (default time 1, distance 0, congestion 0; non-negative, only the ratios matter). `optimize` returns
  `total_time_min`, `total_distance_km`, `total_delay_min` in real units, and `cost` as the weighted value that was minimized.
- **Time windows.** `time_windows` maps a stop id to `{"earliest", "latest"}` in minutes after the vans leave, or `random_windows: true` draws demo windows from `seed`.
  `service_time_min` and `time_window_penalty` (cost per minute late, default 10) tune the model. The response gives each route's `schedule` (arrival, waiting,
  lateness per stop) and `total_late_min`, `total_wait_min`, `late_stops`.
- **Defaults.** Anything left out of a problem (depot, stops, demands, fleet size) is filled in from `seed` and echoed back, so the same problem can be re-solved
  after traffic changes.
- **Warnings.** Both solve endpoints return `warnings` for problems that cannot be planned cleanly: demand above the fleet's capacity, a single stop whose demand
  exceeds one van's capacity (named), and windows that close before a van could arrive. A stop that closed roads cut off is a 422 that names it.

## 5. Hosting

The public site (https://quantum-inspired-route-optimizer.onrender.com) runs the same Docker image on Render's free plan, described by `render.yaml`. The image
reads `PORT` from the host, so it also runs on Google Cloud Run and similar services.

- **Speed.** The free instance has about a tenth of a CPU. Measured with the same limits on a laptop, the default plan takes about 7 s instead of 0.3 s and the full
  benchmark about 40 s instead of 2 s. Everything works, only slower.
- **Sleep.** A free instance sleeps after 15 minutes without a visit and needs about a minute to wake. `.github/workflows/keepalive.yml` visits `/health` every
  10 minutes to prevent that.
- **Limits of the free host.** Live map downloads from OpenStreetMap do not finish there, so the server (which detects `RENDER=true`, or `HOSTED_DEMO=1`) refuses
  anything that is not one of the four ready-made cities up to 2000 m, and the interface says so. This is a limit of the free hosting, not of the software: in
  Docker or on any normal machine every place works, up to 4000 m.
- **Live traffic on the public site** needs `TOMTOM_API_KEY` set as a private environment variable in Render, never in the repository. The recorded MG Road traffic
  works without it. Each visitor's first live fetch uses about 80 of the 2,500 daily requests.
- **State.** Loaded maps are in memory. If the host restarts, a page that was open reports an unknown map, and reloading creates a new one.

## 6. Code layout

```
backend/
  app/core/        graph model, VRP formulation and decoder, QPSO, hybrid swarm, route search, baselines, 2-opt, traffic, live traffic, benchmark
  app/data/        synthetic graph generator, OpenStreetMap loader with disk cache, TomTom adapter, place suggestions, CVRPLIB adapter
  app/services/    graph store, problem builder, solver dispatch, map and route views, live traffic, snapshots
  app/api/         FastAPI routers           app/schemas/   request and response models
  scripts/         benchmark experiments (one per finding), demo_rehearsal.py, check_tomtom.py, warm_city_cache.py
  tests/           pytest suite (run from backend/: python -m pytest tests -q)
  results/         the per-run CSV files behind the numbers in BENCHMARKS.md
frontend/          React, TypeScript, Leaflet and Recharts interface
docs/              MATH_FORMULATION.md, BENCHMARKS.md, this file
Dockerfile         multi-stage image: builds the interface, then the backend that serves it
docker-compose.yml one service, one port, maps and traffic recordings mounted from the host
render.yaml        the free Render web service
```
