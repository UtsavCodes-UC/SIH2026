# Idea PPT: slide-by-slide content

For the SIH 2026 template (`SIH2026-IDEA-Presentation-Format`). The rules in the template's own last slide decide the shape of this
outline: **at most 6 slides including the title slide**, points / diagrams / pictures instead of paragraphs, the template's headings
and pointers kept as they are, and the **file uploaded as a PDF**. The template's 7th slide ("Important instructions") is deleted before
export. So the six slides are: 1 Title, 2 Idea title + Proposed solution, 3 Technical approach, 4 Feasibility and viability,
5 Impact and benefits, 6 Research and references.

Every number below was re-derived from the result CSVs in `backend/results/` (or the demo rehearsal) and is explained in
[BENCHMARKS.md](BENCHMARKS.md). Where a figure belongs to one solver only, the slide text names the solver. Do not drop that label.

**Fill in yourselves:** Team ID, registered team name (the oval on slides 2 to 6 says "Your Team Name"), the GitHub link and the demo-video
link. "Egreen Quanta" is the organisation that set the problem, not your team.

---

## Slide 1: Title page (fill the template's own lines)

| Template line | Put |
|---|---|
| Problem Statement ID | SIH26137 (check it against the portal) |
| Problem Statement Title | Quantum-Inspired Intelligent Traffic Route Optimization in Transportation Systems Using Metaheuristic Optimization |
| Theme | as shown on the portal for this problem (the problem PDF places it under the Quantum Technology vertical) |
| PS Category | Software |
| Team ID / Team Name | yours |

Nothing else. Do not squeeze the prototype's name in here; it goes in the idea title on slide 2.

---

## Slide 2: IDEA TITLE + Proposed Solution

**Idea title (the big heading):** *QuantumRoute: a quantum-inspired route optimizer for delivery fleets on real city roads under live traffic*

Keep the template's four pointers as bold labels and put these under them.

**Proposed solution**
- A working web platform: pick a city, drop a depot and stops, press Optimize, and get colour-coded van routes on the map.
- The road network is a weighted directed graph: every road carries travel time, distance and a live congestion factor.
- The core solver is **QPSO** (Quantum-behaved Particle Swarm Optimization), a quantum-inspired metaheuristic. It runs on ordinary hardware.

**Detailed explanation** (draw this as a five-box arrow strip, not as text)

`Real map` → `Traffic` → `Problem` → `Solver` → `Answer`

- Real map: OpenStreetMap, any place in the world, 4 ready-made Indian cities (Connaught Place Delhi, Sector 18 Noida, MG Road Bengaluru, CST/Fort Mumbai), or a synthetic city.
- Traffic: live (TomTom), recorded replay, simulated (random, rush hour), and road closures.
- Problem: depot, up to 150 stops, fleet size, van capacity, optional time windows, what to minimize.
- Solver: QPSO with a warm start and a polish; PSO, genetic algorithm, nearest neighbour and a route search as alternatives.
- Answer: routes on the map, per-van load / time / distance / delay, convergence curve, side-by-side benchmark.

**How it addresses the problem** (one line per objective of the problem statement, with a tick)
- Objective 1, VRP **and** shortest path: multi-van capacitated routing, and A-to-B shortest path (exact Dijkstra plus QPSO / PSO / GA searching for the same route).
- Objective 2, minimize time, distance **and** congestion: three weights, four one-click presets (Fastest, Shortest, Avoid jams, Balanced).
- Objective 3, convergence and quality against classical methods: benchmarked against PSO, GA, nearest neighbour, Google OR-Tools and exact optima.
- Objective 4, scalability: 150 stops in the app, 200 customers in the benchmarks, 22 standard 100 to 199 customer instances.

**Innovation and uniqueness** (icon + one line each)
- **Traffic in the loop:** real TomTom readings, recorded replays, and simulated rush hour, each labelled LIVE / RECORDED / SIMULATED on the map.
- **What-if roads:** click a road to close it; every solver plans around it; the app names any stop that becomes unreachable.
- **A tuned QPSO:** the jump size is scaled with the problem size, the search starts from a warm route, and a polish moves stops between vans.
- **Proof, not claims:** benchmarked against exact optima and proven-optimal standard instances, with 20 written-up findings.
- **Usable today:** in-app Guide, one-command Docker, public live site, 431 automated tests.

**Bottom strip: three stat boxes** (large number, small caption)
1. **13.6 to 28.1%** cheaper routes than classical PSO: QPSO, raw output, 20 to 50 stops, significant in all 9 test settings.
2. **1.5%** above the proven optimum after 2 min: the platform's *Route search* option on 22 standard instances (100 to 199 customers). OR-Tools' 60 s solution: 5.5%.
3. **150 of 150** small problems solved to the exact optimum: the platform's *Route search* option (10 to 16 stops).

**Pictures:** the app overview screenshot (`frontend/public/guide/overview.webp`) on the right half.

---

## Slide 3: TECHNICAL APPROACH

**Left third, technologies** (a compact table or a row of logos)
- Backend: Python 3.11, FastAPI, NumPy, NetworkX, OSMnx
- Frontend: React 18, TypeScript, Vite, Leaflet map, Recharts
- Data: OpenStreetMap roads, TomTom Traffic Flow API
- Reference solvers: Google OR-Tools, exact dynamic programming (Held-Karp and our own capacitated solver)
- Delivery: Docker (`docker compose up`), REST API with interactive docs, deployed on Render
- Quality: 431 automated tests, written mathematical formulation

**Right two thirds, the flow chart** (this is the picture the template asks for: "Flow Charts / Images / working prototype")

```
OpenStreetMap / synthetic city
        │
        ▼
Weighted directed graph  ◄──  Traffic layer: live TomTom · recorded · random · rush hour · closed roads
 (nodes = intersections,
  arcs = roads with time, distance, congestion)
        │
        ▼
Problem: depot · stops · vans · capacity · time windows · cost weights (time / distance / congestion)
        │
        ▼
QPSO search  →  warm start  →  polish (2-opt + moving stops between vans)
        │                     (alternatives: PSO · GA · nearest neighbour · route search)
        ▼
Routes on the map · per-van table · convergence curve · benchmark · shortest path
```

**Methodology in four bullets** (under the chart)
- **Encoding:** each particle is a vector of random keys; sorting the keys gives the visiting order, and the order is cut into vans by capacity.
- **Update rule:** each step *samples* a new position around an attractor between the particle's best and the swarm's best (a quantum particle in a potential well, no velocity); the jump size shrinks over time, exploring first and refining later.
- **Fitness:** the weighted cost of the plan: driving time, distance, congestion delay, plus penalties for overload and lateness.
- **Defaults:** 40 particles, 800 iterations; a default plan takes about a second on a laptop.

**Picture:** one screenshot of a solved plan (`results.webp`) or the map with coloured routes. Put the flow chart bigger than the screenshot.

---

## Slide 4: FEASIBILITY AND VIABILITY

**Feasibility of the idea** (each bullet with a tick)
- **Already built and running:** live public site, source on GitHub, runs from one Docker command.
- **No special hardware:** quantum-inspired means it runs on an ordinary CPU; a default plan takes about a second.
- **Free, open data:** OpenStreetMap maps; TomTom's free tier (2,500 requests a day).
- **Real Indian cities ready:** Delhi, Noida, Bengaluru, Mumbai load at once and work offline.
- **Checked in the open:** 431 automated tests; every claim traceable to a result file.

**Potential challenges and risks → strategies** (a two-column table; this is where the honest points become strengths)

| Challenge | Our strategy |
|---|---|
| Routing is NP-hard; exact methods do not scale | Metaheuristics with a warm start and polish, validated against exact optima on small problems and proven optima on standard ones |
| Local search narrows the gap between metaheuristics | We report raw and polished results side by side, keep QPSO as the default, and add a route-search option for the best plans |
| Live traffic depends on the network, a key and a daily quota | Recorded replays, reuse of a recent reading, and a badge that always says LIVE, RECORDED or SIMULATED |
| Traffic sensors do not cover every road (541 of 1,223 roads measured on MG Road) | Unmeasured roads are estimated from measured neighbours, and the badge reports how many were measured |
| A road closes or a stop becomes unreachable | The road is removed for every solver; the app names the cut-off stops instead of drawing a nonsense route |
| Free hosting is slow (about a tenth of a CPU) | The public demo is limited to the ready-made cities and says so; the full app runs at full speed in Docker or locally |

**Picture:** the traffic badge / traffic panel screenshot (`traffic.webp`), or a small "LIVE / RECORDED / SIMULATED" badge strip.

---

## Slide 5: IMPACT AND BENEFITS

**Potential impact on the target audience** (icons for each audience)
- **Delivery and logistics fleets:** plans that see traffic and van capacity, and answer "what if this road closes?" in seconds.
- **City traffic and transport authorities:** a transparent tool to test closures and congestion scenarios on a real network.
- **Researchers and students:** a reproducible benchmark bench for quantum-inspired optimization, with the mathematics written out.

**Why traffic-aware planning matters** (measured in the prototype; one big number each)
- **About 2×:** the same 15-stop job took 72 to 103% longer under recorded evening traffic on MG Road than in free flow (mean 93%, 12 random draws).
- **+51%:** simulated rush hour makes the same job take 32 to 60% longer (mean 51%, 12 random draws).
- **Time, distance and congestion are different goals:** asking only for the fewest kilometres saves about 6 to 7% distance but costs 13 to 15% more minutes and about 60% more congestion delay; the app shows all three, so the trade-off is visible.
- **Deadlines:** plans that ignore time windows arrive late at about a third of the stops; pricing lateness gets vans on time.

**Benefits** (three columns)
- **Economic:** fewer van-minutes and kilometres; capacity-checked plans; costs of every choice shown in real minutes and kilometres.
- **Environmental:** less driving and less time stuck in jams (congestion delay is reported for every plan).
- **Social:** reliable delivery times, and quick, informed reaction to closures and incidents.

**Next steps (one line):** custom network upload, hard time windows, mixed fleets, live incident feeds.

**Picture:** the road-closure what-if screenshot (`closures.webp`): a red closed road with the banner showing what it cost.

---

## Slide 6: RESEARCH AND REFERENCES

**Links** (large, top; make them clickable in the PDF)
- Live prototype: https://quantum-inspired-route-optimizer.onrender.com
- Source code and documentation: your GitHub link (the repo has `docs/MATH_FORMULATION.md` and `docs/BENCHMARKS.md`)
- Demo video: your link

**Our research results** (a four-row table; this is the "research work" the template asks for)

| Experiment | Result |
|---|---|
| QPSO vs classical PSO, 20 to 50 stops, 9 settings x 30 instances | Raw output 13.6 to 28.1% cheaper; QPSO wins 21 to 30 of 30 in every setting; reaches PSO's final quality in about 1/8 of the iterations at 20 stops, 1/4 at 30, 1/2 at 50 |
| 150 small problems (10 to 16 stops) with a computed exact optimum | Route search option: optimal on 150 of 150. Default QPSO pipeline: 1.5 to 3.6% above the optimum on average |
| 22 standard CVRPLIB instances (100 to 199 customers, proven optima) | Route search option: 2.9% above optimal after 10 s, 1.5% after 2 min. OR-Tools 60 s: 5.5% |
| Shortest path, 4 map sizes x 50 pairs | Dijkstra exact in under 1 ms; QPSO / PSO / GA find the exact route on 78 to 90% of pairs on a 40-intersection map (42 to 44% on 300) |

*Footnote to add in small type (recommended, it protects your credibility):* the default QPSO pipeline averaged 10.2% above optimal on the 100 to 199 customer instances; the route search is the platform's option for large problems (BENCHMARKS.md, Finding 14).

**References** (small type, one line each)
- Sun, Feng & Xu (2004). Particle swarm optimization with particles having quantum behavior. IEEE CEC.
- Kennedy & Eberhart (1995). Particle swarm optimization. IEEE ICNN.
- Bean (1994). Genetic algorithms and random keys for sequencing and optimization. ORSA Journal on Computing.
- Prins (2004). A simple and effective evolutionary algorithm for the vehicle routing problem. Computers & Operations Research.
- Vidal (2022). Hybrid genetic search for the CVRP: open-source implementation and SWAP* neighborhood. Computers & Operations Research.
- Uchoa et al. (2017). New benchmark instances for the capacitated vehicle routing problem. European Journal of Operational Research.
- Held & Karp (1962). A dynamic programming approach to sequencing problems. Journal of SIAM.
- Boeing (2017). OSMnx: new methods for acquiring, constructing, analyzing, and visualizing complex street networks. Computers, Environment and Urban Systems.
- Data and tools: OpenStreetMap (ODbL), TomTom Traffic Flow API, Google OR-Tools.

---

## Coverage check: every feature of the site, and the slide that carries it

| Feature on the website | Slide |
|---|---|
| Synthetic city; real OpenStreetMap city; 4 ready-made Indian cities; search any place with suggestions | 2, 3 |
| Depot and stops (random or clicked), fleet size, van capacity, capacity check | 2, 3 |
| Soft time windows with lateness reporting | 2, 5 |
| Cost weights (time, distance, congestion) and the four presets | 2, 5 |
| QPSO (default), PSO, genetic algorithm, nearest neighbour, route search; warm start; polish | 2, 3, 6 |
| Results: routes on the map, per-van table, convergence curve | 2, 3 |
| Benchmark tab: raw vs polished, every algorithm on the same problem | 2, 6 |
| Traffic: free flow, random, rush hour, live TomTom, recorded replay, LIVE / RECORDED / SIMULATED badges, automatic re-plan | 2, 4, 5 |
| Road closures (what-if) and cut-off detection | 2, 4, 5 |
| Shortest path A to B: Dijkstra plus QPSO / PSO / GA and the gap to exact | 2, 6 |
| Guide with screenshots; REST API with interactive docs | 2, 3 |
| Docker, live public site, 431 tests, written mathematics, 20 findings | 2, 3, 4, 6 |

## Wording rules (so nothing on the slides can be contradicted by our own repository)

Say:
- "QPSO is 13.6 to 28.1% better than classical PSO on raw output", always with "raw" and the 20 to 50 stop range.
- "Quantum-inspired, runs on ordinary hardware."
- "Route search option" whenever the 1.5% / 2.9% / 150-of-150 figures are quoted.

Do not say:
- "QPSO beats the genetic algorithm / all metaheuristics" or "QPSO scales best". After the same local search the methods end within about 1 to 3% of each other.
- "We use a quantum computer."
- "Better than other teams" or any comparison with competitors we have not measured.
- "Live traffic" for a replay.

## Making the PDF

Edit the template in PowerPoint (keep the headings), delete the "Important instructions" slide, then File, Export, PDF. Check that the
links on slide 6 still click, that the file is at most 6 pages, and that fonts and screenshots look sharp. PowerPoint cannot use the `.webp`
Guide images directly: ask for PNG copies (or take a fresh screenshot at 100% zoom).
