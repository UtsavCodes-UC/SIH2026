# Demo script

A click-by-click run of the demo, with what to say, what you should see, and what to do if it goes wrong. It is written to be
performed live (about 8 minutes) and cut down for a recorded video (about 4.5 minutes; see the end). Everything in it was
rehearsed against the running app; the numbers quoted come from that rehearsal or from [BENCHMARKS.md](BENCHMARKS.md).

**Before you start, every time:** run the rehearsal (below). It checks that the server, the map cache, the recorded traffic and the
key are all there, and prints what each scene should look like. It takes about 15 seconds.

## 0. Setup, ten minutes before

1. Start the app you will present from. Either way it ends up on one address:
   - Docker: `docker compose up -d` (http://localhost:8000; `PORT=8080 docker compose up -d` if 8000 is taken), or
   - local: `python -m uvicorn app.main:app --port 8000` in `backend/` after `npm run build` in `frontend/`, or the two dev servers (http://localhost:5173).
2. Rehearse it against that address:

   ```bash
   cd backend && python scripts/demo_rehearsal.py --base http://127.0.0.1:8000
   ```

   All lines must say `ok`. A `WARN` about the TomTom key only means the optional live scene is unavailable; recorded traffic still works.
   (`--live` also fetches real traffic once, about 80 of the free 2,500 daily requests; do that only when you intend to show it.)
3. Browser: full screen, 100% zoom, one tab, no bookmarks bar. Open the address. The app starts on an 80-intersection synthetic map
   with random traffic and 15 stops already drawn.
4. Restarted the backend? Reload the page; loaded maps live in the server's memory.

## What we claim, and what we do not

Say these with confidence; each is measured (Finding numbers are in BENCHMARKS.md):

| We claim | Evidence |
|---|---|
| QPSO is a much stronger optimizer than classical PSO on raw output | 13.6-28.1% cheaper routes, significant in all 9 raw cells (Finding 7) |
| The app plans multi-vehicle routes on real road networks with changing traffic, live or recorded | this demo |
| A stronger search between vans (the "Route search" option) gets within 1.5-2.9% of proven optimal on standard benchmarks | Finding 14 (22 CVRPLIB instances, 10 s to 2 min) |
| Every plan is checked: capacity, closed roads, unreachable stops are reported, never hidden | tests, warnings in the UI |

Do **not** say, because the evidence says otherwise:

- "QPSO beats GA / PSO / everything." After the same local search the swarms end within about 1-3% of each other, mostly not significantly (Findings 7, 10, 17, 18). QPSO's clear win is over classical PSO on raw output.
- "QPSO scales best." At 50-100 customers a genetic algorithm is stronger from a random start, and the pipeline (warm start + polish), not the quantum update, does the work (Findings 10-11).
- "We use a quantum computer." QPSO is *quantum-inspired*: a classical algorithm that models each particle like a quantum particle in a potential well. It runs on ordinary hardware.
- "Live traffic" for anything recorded. The badge says LIVE only for a real fetch, RECORDED for a replay.

## The scenes

### Scene 1 · A delivery plan (about 60 s)

**Do:** the app opens on the synthetic map. In section 2 press **Draw** (15 random stops) if you want a fresh set. In section 3 press **Optimize routes**.

**Say:** "A depot in the middle, fifteen delivery stops, vans that can carry 100 units each. The app decides which van serves which stop and in what order, to minimize total driving time. The solver is QPSO: a swarm of candidate plans that moves towards better ones."

**You should see:** coloured routes along the roads with numbered stops; below, *Route plan* with **Total driving, all vans** (about 90 minutes in the rehearsal), vans used 3 / 3, **Capacity: all respected**, the **Congestion delay**, and the **Search progress** curve dropping fast then flattening.

**If asked what "polish" is:** a 2-opt clean-up inside each route plus moving stops between vans; the *Polish saved* tile shows what it added.

### Scene 2 · The benchmark, told honestly (about 45 s)

**Do:** press **Benchmark** (next to Optimize), then read the table in the *Algorithm benchmark* tab.

**Say:** "The same problem given to QPSO, classical PSO, a genetic algorithm and plain nearest-neighbour, all with the same budget. Look at the raw column, what each algorithm found by itself: QPSO is clearly ahead of classical PSO. Then look at the polished column: once a good local search is added they end close together. So the honest summary is that QPSO is a much stronger optimizer than classical PSO on its own, and the local search closes most of the gap."

**You should see (rehearsal, one instance):** raw QPSO 93 min, GA 102, PSO 109, nearest neighbour 129; after the polish PSO, GA and nearest neighbour all 96.4 and QPSO 93. On this instance QPSO stays ahead after the polish; across many instances that is not reliable (Finding 7), so do not present it as a rule.

### Scene 3 · Traffic changes, the plan changes (about 60 s)

**Do:** section 4 **Traffic**: press **Free flow**, then **Rush hour**. *Re-optimize automatically* is ticked, so the plan recomputes each time. Watch the map and the total.

**Say:** "Traffic is part of the model: every road has a congestion factor and the planner sees it. In free flow the same job takes [read the total off the screen] minutes; in rush hour [read the new total], and the plan is different: several stops are now served by a different van, because the quickest way round has moved."

**You should see (rehearsal):** free flow 65.5 min with 0 minutes lost to congestion; rush hour 104.8 min with 35.6 lost, and 8 of the 15 stops in a different van. The colours on the map turn from grey/yellow to orange/red towards the centre. The badge at the top right of the map reads FREE FLOW, then SIMULATED.

**Invariant to rely on if your numbers differ:** over 12 random draws of 15 stops, rush hour was 32% to 60% slower than free flow (mean 51%).

### Scene 4 · A real city with real traffic (about 75 s)

**Do:** section 1 tab **Real city** → choose **MG Road, Bengaluru** → **Load road network** (about 2 seconds; it is cached). Press **Optimize routes**. Note the total (free flow). Then section 4 **Traffic**: under *Recorded traffic* the recorded snapshot is selected; press **Replay**.

**Say:** "This is real OpenStreetMap data: 871 intersections around MG Road. The first plan uses free-flow speeds. Now I replay traffic we recorded from TomTom's live traffic feed at 6:23 pm on the 19th: 541 of the roads were measured directly and the rest are estimated from their neighbours. The badge says RECORDED, never LIVE, because this is a replay. The same stops now take almost twice as long."

**You should see (rehearsal, 12 stops):** free flow 26.5 min → recorded 52.6 min (+99%), 26 minutes lost to congestion; the badge reads RECORDED with the capture time and "541 of 1223 roads measured". The UI draws 15 stops; over 12 random draws of 15 the recorded traffic made the job 72% to 103% slower (mean 93%), so "about twice as long" is safe to say.

**Optional wow, only if the rehearsal with `--live` passed and you have internet:** press **Fetch live traffic** (about 25 seconds, the badge turns LIVE). If it fails, say "live needs the network; here is the recording of it" and use Replay. The recorded snapshot is the reliable path for a room with unknown wifi.

### Scene 5 · What to minimize (about 30 s)

**Do:** first note the current **Total driving** and **Congestion delay**. Section 3 **What to minimize**: press **Shortest**, then **Optimize routes**. Compare.

**Say:** "Minutes are not the only goal. If we ask for the shortest distance instead, the plan saves a few kilometres but drives straight into the jams: more minutes and much more time stuck in congestion. The planner can weigh time, distance and congestion in any blend, and the app always reports all three, so the trade-off is visible."

**You should see (rehearsal, recorded MG Road traffic):** distance a few per cent lower, driving time about 10% higher, congestion delay about 25% higher. Over 12 random draws of 15 stops the direction never changed for minutes (+1% to +17%, mean +10.6%) or for delay (+12% to +42%, mean +27%); the kilometres saved were smaller and less certain (mean -4%, from -11% to +5%). On the synthetic map with random traffic: minutes +14%, delay +62%, km -6%. Finding 16 measured -6 to -7% km, +13 to +15% minutes and about +60% delay at 30 and 60 stops.

**Do not build this scene on "Avoid jams".** At 15 stops it is mild and noisy (on the recorded MG Road traffic the congestion delay changed by -2% on average, from -6% to +8%); its clear effect of about -6 to -8% delay for +1% minutes was measured at 30 and 60 stops (Finding 16). Mention it in one sentence if asked.

### Scene 6 · Block a road (about 60 s)

**Do:** section 3 **Algorithm** → **Route search**, **Time limit** 3, then **Optimize routes**. On the map toolbar press **block road**. Click a busy road on one of the routes, near the middle of the map. Wait for the plan to update and read the orange banner. Click the red road again to reopen it, or press **Reopen all**.

**Say:** "A bridge is closed, or an accident. I click the road and it is removed from the network for every algorithm. The plan is recomputed straight away and the banner says what the closure cost against the same plan with every road open. I used the route search for this scene because it is steadier than the swarm for comparing two plans: closing a road can only make the best plan slower, and a randomized solver can wobble by a couple of percent."

**You should see (rehearsal, MG Road):** closing a road the plan uses costs anywhere from nothing (the plan barely needed it) to +10% (+3.5%, +7.0%, +7.0%, +10.4% for the roads tried). The banner shows the change in minutes, per cent and kilometres. Roads are drawn red with a cross.

**Two things that can happen, both good to show:**
- *A road that costs nothing:* the plan did not need it. Say so; it is correct.
- *A road that cuts stops off* (in the rehearsal, closing one particular road made all twelve stops unreachable from the depot): the app refuses to plan and says which stops cannot be reached because of the closed roads, and cut-off intersections show as red circles. Say: "the app tells us instead of drawing a nonsense route", then **Reopen all**.

### Scene 7 · Shortest path, A to B (about 45 s)

**Do:** on whichever map you are on, press **set A** on the map toolbar and click an intersection at one end (click right on a dot), then **set B** and click one at the far end. In section 5 press **Compare all four**. Read the table in the *Shortest path* tab.

**Say:** "The other question in the problem: the quickest way from A to B. Dijkstra's algorithm solves this exactly, in under a millisecond, so it is our reference. We also let QPSO, PSO and a genetic algorithm search for the same route, to show the same machinery works on a second kind of problem. They come close: on this pair QPSO is about 1% above the exact route and takes several hundred times longer. So for a single route you would just use Dijkstra; the value is that the same framework handles both problems and we can measure the gap."

**You should see (rehearsal):** Dijkstra 18.17 min, 0.3 ms; QPSO 18.41 (+1.29%), PSO 18.33 (+0.87%), GA 18.33 (+0.87%), each 140-250 ms. The exact route is the wide dark line on the map; each search is a dotted line on top. Across 50 pairs at each size the searches find the exact route on 78-90% of pairs on a 40-intersection map and 42-44% on a 300-intersection map (Finding 18); QPSO is not better than PSO or the GA.

### Scene 8 · Time windows (optional, about 30 s)

**Do:** section 2 tick **Time windows (demo)**, keep *Service time* at 5, **Optimize routes**. Open the schedule under the route table.

**Say:** "Some stops must be served within a window. Late arrivals are charged per minute. If the planner ignores the windows, on average about a third of the stops arrive late; pricing lateness makes the vans arrive on time at the cost of driving more."

**You should see (rehearsal):** ignoring the windows: 9 of 15 stops late, 157 minutes late in total, 96 minutes driving; pricing lateness: 0 late, 111 minutes driving (Finding 17: +26% driving at 15 stops, +36% at 30).

### Closing (about 30 s)

**Say:** "To sum up: a road-network model with live or recorded traffic and closures; QPSO as the quantum-inspired core, benchmarked honestly against classical PSO, a genetic algorithm, OR-Tools and proven optima; a stronger route search as an option; shortest path and time windows on the same framework; and the whole thing runs with one command, `docker compose up`. Where QPSO clearly wins is over classical PSO on raw output; where it does not, we say so and show the numbers."

## Questions you will probably get

| Question | Answer |
|---|---|
| Is this really quantum? | No quantum hardware. QPSO is a classical algorithm inspired by quantum mechanics: each particle is a wave function in a potential well, sampled instead of moved by velocity. That is what "quantum-inspired" means here. |
| Does QPSO beat the genetic algorithm? | Not reliably. It beats classical PSO clearly on raw output (Finding 7); against the GA it is level once both are given a good starting solution and local search (Findings 10, 17, 18). |
| How good are the plans? | Small problems, where we can compute the true optimum (10-14 stops, several vans): the default QPSO pipeline is on average 1.5-3.6% above it, the route search option found the exact optimum on all 150 instances tested (Finding 20). Large problems: against proven optima on 22 standard instances (100-199 customers) the route search is 2.9% above optimal after 10 s and 1.5% after 2 minutes, better than OR-Tools' 60 s solution (5.5%); the app's default QPSO pipeline averaged 10.2% above optimal (Finding 14). Say both, and say which is which. |
| Why is the default not the best one? | QPSO is the project's core method and stays the default; the route search is one dropdown away. |
| Is the traffic real? | Recorded traffic is real TomTom data replayed and labelled RECORDED. Live is real too, needs a key and network. Random and rush hour are simulated and labelled SIMULATED. |
| What happens when a road closes? | It is removed from the map for every solver. If it cuts a stop off, the app says so; otherwise the plan is recomputed. |
| Why a heuristic and not exact? | The problem is NP-hard. We check against exact solutions on small instances and proven optima on standard ones. |
| How big can it go? | The app takes up to 150 stops; benchmarks run to 200 customers. |
| What is not done? | Custom network upload, hard time windows, a route search that understands time windows, a heterogeneous fleet. |

## When something goes wrong

| Symptom | Do this |
|---|---|
| Page blank or "Cannot reach the API" | The server is not running or is on another port. Start it, reload the page. |
| Map shows no streets underneath | Tile server unreachable (no wifi). The roads and routes still draw; carry on. |
| Real city does not load | Only the four presets and the places you loaded before are cached; a new place needs the internet. Use a preset. |
| "Fetch live traffic" fails | Use **Replay**. Do not retry live in front of an audience. |
| The plan looks odd after a restart | Reload the page (loaded maps are lost when the server restarts). |
| Closing a road says stops are not reachable | That road was a single access. **Reopen all**, choose another road. |
| A what-if shows a *saving* | The banner says a closure cannot really save time; it is the randomized solver. Switch to Route search or press Optimize again. |
| Port 8000 is taken | `PORT=8080 docker compose up -d`, or start uvicorn on another port. |

## Recording the video

A cut for about 4.5 minutes: Setup shot (5 s: the Docker or terminal command), Scene 1 (45 s), Scene 3 (45 s), Scene 4 (60 s), Scene 6 (50 s), Scene 7 (35 s), Closing (25 s). Skip the benchmark, cost weights and time windows in the video and mention them in the voice-over on the closing screen.

- Record at 1920 x 1080, browser at 100% zoom, cursor highlighted. Record the screen and the voice separately so either can be redone.
- Do each scene as its own take, starting from the app in the state the scene begins with, then cut them together; the loading spinner is short but the route search takes up to 3 seconds, so keep that in the take.
- Read the numbers off the screen in the take, not from this script: the UI draws random stops, so its figures differ from the rehearsal, though the pattern does not.
- Put the badge (FREE FLOW, SIMULATED, RECORDED) in frame whenever traffic is mentioned.
