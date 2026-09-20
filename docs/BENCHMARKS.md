# Benchmark results

## Read this first — current headline (Findings 7-20)

The problem statement's core claim is that QPSO gives "stronger global
search, faster convergence, and a better balance between exploration and
exploitation" than classical metaheuristics. We checked that empirically.
Two metrics are reported side by side, and they answer different questions:

- **raw** — what the metaheuristic itself found, with no local search. Same
  encoding, same fitness, same 40-particle / 800-iteration budget for both.
  This is the like-for-like algorithm comparison and the **headline**.
- **+2-opt (hybrid)** — the same output after a uniform 2-opt polish
  (`app/core/local_search.py`), i.e. what a production engine would run.

Single-vehicle tour, 30 random instances at each of 20 / 30 / 50 stops, three
classical-PSO parameter sets:

| | raw (no local search) | +2-opt hybrid |
|---|---|---|
| QPSO wins vs classical PSO | 70-100% of instances (21-30 of 30) | 50-73% (15-22 of 30) |
| Mean cost reduction | +13.6% to +28.1% | +0.5% to +3.6% |
| Statistically significant? | p <= 0.02 in every cell, p <= 0.0002 in 8 of 9 | p < 0.05 in only 2 of 9 cells |

So the defensible pitch is: **QPSO is a much stronger optimizer than classical
PSO on its own, and reaches PSO's final quality in roughly an eighth to a
half of the iterations; a good local search closes most of that gap, so the
hybrid advantage is small and mostly not significant.**

**The caveat that matters most.** With several vehicles and capacity
constraints the raw edge holds at about 20 customers (+10.6%, p = 0.0002), is a
statistical tie at 50 (+3.7% to -4.2% depending on PSO settings and fleet
tightness, p >= 0.41), and reverses at 100 (PSO wins 15-20 of 20) (Finding 9).
Finding 10 investigated this. A jump size that shrinks with problem size
restores QPSO's raw lead over classical PSO at 100 customers (+12.4%, 19 of 20).
But a permutation GA is far stronger than either swarm from a random start (raw
25% / 35% lower cost at 50 / 100 customers), and what really makes 100 customers
work is the pipeline around the search: **warm start + moving stops between
vehicles** cut the app's default cost by 23% / 40% at 50 / 100 customers. Once
everything is warm-started, QPSO, PSO and GA end within about 1% of each other at
50-100 customers, and QPSO is 0.4% (not significant) ahead of plain
nearest-neighbour + polish at 100. Do not claim QPSO beats GA or scales better
than other methods; the supported claim is QPSO's edge over classical PSO at
about 20 customers, and a hybrid pipeline that handles 100.

Finding 11 then built the architecture "adaptive random-key QPSO + elite archive +
2-opt + diversity restart + hybrid initialization" and tested it on single-vehicle
tours up to 200 stops. It beats classical PSO by 17.5% at 100 stops (20 of 20
instances) and lands within about 3% of OR-Tools' guided local search (1% at 50
stops, 6% at 200), but a hybrid **PSO** built from the same components does exactly as well, so the credit belongs
to the architecture (local search plus kicks and restarts), not to the quantum
update. On the multi-vehicle problem it adds nothing over warm start + polish.

Finding 12 then tested the most-suggested fix for the multi-vehicle problem, an
optimal Split decoder in place of the greedy cut. It is worth about 1% for every
method (including plain nearest neighbour), which is the size of the noise from
changing the local search's starting point, and it is 30-80x slower per evaluation.
Against an OR-Tools capacitated reference (60 s), our multi-vehicle pipelines are
still 6-9% above it whichever decoder is used, so the remaining gap is not the decoder.

**Correction to the OR-Tools references.** Findings 11 and 12 were first written against
references produced with Python cost callbacks, which slow OR-Tools' search badly.
Re-running them with the cost matrix handed over as data (`scripts/ortools_reference.py`)
made every reference better, by 1.1-3.3% on the tours and 2.4% on the capacitated
instances, so the gaps below use the corrected ones. The original text said the hybrid
QPSO was within 0.1% of OR-Tools at 100 stops and the multi-vehicle pipelines 4-6% above
it; corrected, they are 3.2% and 6-9%. The conclusions about which components matter do
not change, but "matches OR-Tools" does not survive.

Finding 13 then built the stronger search Finding 12 pointed at: moves between routes (2-opt\*, SWAP\*) with neighbour
lists, and an iterated local search on top (`app/core/route_search.py`). From nearest neighbour it reaches 4.9% above
the 60 s OR-Tools reference in 0.05 s, and with 1,000 iterations (about 10 s) it is 2.6% below it on all 20 instances
(100 customers, synthetic graphs). Starting it from the routes of a QPSO, a PSO or a GA instead adds nothing
measurable, and given the swarm's running time as extra iterations nearest neighbour is equal or better: what beats
OR-Tools here is the search, not the swarm. It is built for fleets and is slow on a single long tour, and it was not
tested with the swarm inside the loop or on real road graphs.

Finding 14 then measured it against the standard CVRPLIB "X" instances, whose optimal costs are proven (22 instances,
100-199 customers). The new search averages 2.9% above optimal after 10 s and 1.5% after two minutes (18 of 22 within
2%), beating OR-Tools' 60 s solution, which averages 5.5% above, on 19 of 22 instances at 10 s. The app's default before
this work averaged 10.2% above optimal. It is not a state-of-the-art solver: it stalls on some instances (4-6% above),
and the instances are Euclidean, with no traffic or roads.

The search is now an option in the app (the default is unchanged: QPSO with warm start and polish). Finding 15 compared
the two at the sizes the app is used at, 15-100 stops on synthetic road graphs: the route search is cheaper by about 3% at
15 stops and by 6-10% from 30 stops up, on every instance from 30 stops, and one second of it is already ahead of the
default. Which one is the default is a product decision; the benchmark says the option is the better plan-finder.

Finding 16 covers the objective. The optimizer can now minimize a weighted blend of travel time, distance and congestion
delay (the default is time alone, unchanged), and the results report real minutes, kilometres and delay. Weighting
distance alone saves about 6-7% of the kilometres at the price of 13-15% more minutes and roughly 60% more congestion delay;
half weight on congestion cuts the delay by 6-8% for about 1% more minutes.

Finding 17 adds soft time windows: a stop may be served between an earliest and a latest minute; early vans wait, late vans are
charged per minute. QPSO, PSO and the GA plan around them (plans that ignore the windows are late at a third of the stops, plans
that price lateness are on time, for roughly 26-36% more driving on the random demo windows), but the route search and the exact
solver do not handle windows. The algorithms only did well once all three were given a window-aware starting solution; then QPSO
ties with the GA and PSO. It is not better than them here.

Finding 18 covers the problem statement's first objective, the quickest route between two places. Dijkstra's algorithm is exact and
takes under a millisecond; QPSO, PSO and a genetic algorithm search for the same path with random-key priorities and are checked
against it on 50 pairs at each of four map sizes (40 to 300 intersections). They find the exact route on 78-90% of pairs on the
smallest map and 42-44% on the largest (average gap under 1% growing to 2.6-4%), several hundred times slower, and never better than
Dijkstra. QPSO is not better than PSO or the GA (one significant win over the GA at 40 intersections, none elsewhere). A starting
particle that points at the target is what keeps them competitive as maps grow.

Finding 19 covers road closures ("block a road"). A closed road is removed from the network, so every method plans around it. Closing
a random road that a plan uses costs about 1% of the plan on the synthetic maps (route search), but the app's default solver varies
by 1.5-3% between reruns of the same open network, so its what-if figure is only good to about that: 6 of 40 default comparisons
showed a closure "saving" time, which cannot be true. The route search is steadier (under 0.3% noise) and is the better choice for
what-ifs; the app says when a saving is an artefact.

Finding 20 answers "how near-optimal?" where the optimum can be computed exactly (a new exact solver, checked against exhaustive search). On
problems of 10-14 stops with several vans, the app's default QPSO pipeline is on average 1.5-3.6% above the optimum (exactly optimal on 22, 12 and 7 of 30
instances; worst cases 12-18%), and most of that comes from the polish. The route search option found the exact optimum on all 150 instances
(several vans to 14 stops, one van to 16) within 3 s. QPSO's raw advantage over classical PSO reproduces (significant at 10 and 12 stops) and disappears
after the polish; against the genetic algorithm it is not significant. This replaces the 2.4% of Finding 1.

Findings 1-6 below are the original tuning log. **They were measured on the
polished metric with a 2-opt that had a bug (Finding 8), so their polished
numbers are superseded by Finding 7.**

Ground truth for small single-vehicle instances is exact (Held-Karp DP,
`app/core/baselines/exact_held_karp.py`).

**Reproducing.** Numbers in Findings 7 and 9 were generated in the pinned
environment (`requirements.txt`: numpy 1.26.4, networkx 3.3). The per-run CSVs
are in `backend/results/pinned_env/`.

```
python scripts/compare_qpso_vs_pso.py --stops 20 30 50 --pso-preset ours --csv-dir results/pinned_env
python scripts/compare_qpso_vs_pso.py --stops 20 30 50 --pso-preset ours --seeds 1 2 3 --csv-dir results/pinned_env/crossed_3seeds
python scripts/compare_multi_vehicle.py
```

An earlier run of the same experiments under numpy 2.4.6 / networkx 3.6.1 uses
different random streams, so individual numbers differ. It reached the same
conclusions: raw wins 25-30 of 30 with +17% to +27% mean improvement, and
polished results between -0.9% and +4.6% whose sign at 50 stops changed from run
to run. That the polished sign flips with the random stream is itself evidence
that the hybrid advantage is within noise. Where the earlier run differed
materially (multi-vehicle at 50 customers), Finding 9 says so.

## Finding 7 — raw vs polished, three PSO baselines, crossed seeds

Setup (`app/core/benchmark.run_qpso_vs_pso`): 30 random instances per size
(instance seeds 300-329), single-vehicle tour over a directed congested graph,
40 particles, 800 iterations. Improvement = (PSO - QPSO) / PSO, positive =
QPSO better. p = one-sided exact sign test on decisive instances (ties
excluded), deliberately conservative. Polished numbers use the corrected 2-opt
(Finding 8).

**Our PSO baseline, one algorithm seed per instance:**

| stops | raw win/tie/loss | raw improvement | raw p | +2-opt win/tie/loss | +2-opt improvement | +2-opt p |
|---|---|---|---|---|---|---|
| 20 | 28/0/2 | +17.2% | <0.0001 | 18/0/12 | +0.5% | 0.18 |
| 30 | 26/0/4 | +27.6% | <0.0001 | 17/0/13 | +1.1% | 0.29 |
| 50 | 25/0/5 | +18.7% | 0.0002 | 18/0/12 | +1.9% | 0.18 |

**Is it an artifact of the PSO baseline?** Same instances, three classical-PSO
parameter sets: ours (inertia 0.9->0.4, c=2.0, v_max 0.5), the teammate
engine's (inertia 0.7, c=1.5, v_max 0.2), and standard Clerc constriction
(0.729, c=1.494). Cells: raw QPSO wins out of 30 (raw improvement); polished
improvement (p):

| PSO baseline | 20 stops | 30 stops | 50 stops |
|---|---|---|---|
| ours | 28 (+17.2%); +0.5% (0.18) | 26 (+27.6%); +1.1% (0.29) | 25 (+18.7%); +1.9% (0.18) |
| teammate | 30 (+18.7%); +2.5% (0.18) | 30 (+28.1%); +2.9% (0.57) | 21 (+13.6%); +2.5% (0.18) |
| Clerc | 29 (+19.1%); +3.6% (0.02) | 26 (+25.5%); +2.9% (0.29) | 28 (+17.4%); +3.2% (0.008) |

The raw result holds against all three, so it is not a weak-baseline artifact.
The polished result is small everywhere and significant in only 2 of 9 cells.

**Crossed design** (30 instances x 3 algorithm seeds; each algorithm's cost is
averaged over seeds per instance, then compared across instances, since seeds
on one instance are not independent evidence):

| stops | raw win/tie/loss | raw improvement | worst instance | +2-opt win/loss | +2-opt improvement (p) | seed-to-seed std QPSO / PSO | QPSO matches PSO's final cost after |
|---|---|---|---|---|---|---|---|
| 20 | 30/0/0 | +16.4% | +7.0% | 20/10 | +1.3% (0.049) | 44.1 / 57.1 | median 96 iters (12% of budget), 91% of runs |
| 30 | 30/0/0 | +26.2% | +1.7% | 18/12 | +1.9% (0.18) | 100.8 / 106.0 | median 201 (25%), 93% of runs |
| 50 | 29/0/1 | +18.8% | -15.0% | 17/13 | +2.1% (0.29) | 269.2 / 162.5 | median 431 (54%), 86% of runs |

What this does and doesn't support:

- **Solution quality (raw):** QPSO wins 89 of 90 instance-level comparisons
  with a 16-26% lower cost. This is the strongest, most robust result.
- **Convergence speed:** to reach the quality PSO ends with, QPSO needs
  roughly 12% / 25% / 54% of the iterations at 20 / 30 / 50 stops. This counts
  iterations, not wall-clock; per-iteration cost is comparable because both
  are vectorized (0.36 s vs 0.34 s for 800 iterations at 12 stops, measured
  unloaded). The advantage narrows as the problem grows.
- **Repeatability:** QPSO's seed-to-seed std is lower at 20 stops (44 vs 57),
  about level at 30 (101 vs 106), and **higher at 50 (269 vs 162)**. In the
  single-seed runs the worst raw instance is 16% / 10% / 20% worse than PSO at
  20 / 30 / 50 stops. Averaging seeds removes most such outliers, but occasional
  bad QPSO runs at 50 stops are real; don't claim QPSO is uniformly more reliable.
- **Hybrid (+2-opt):** the local search helps PSO far more than QPSO. Mean cost
  falls 22.6% / 39.8% / 56.0% for PSO at 20 / 30 / 50 stops versus 5.7% / 17.1% /
  46.8% for QPSO, so polished costs end up within 1-3% (20 stops: QPSO 528.5 vs
  PSO 533.9). Any claim about the deployed hybrid should be modest.
- **Cross-validation:** the teammate's independent engine (multi-vehicle CVRP,
  no local search) gets 28/30 wins and +15.5% on a feasible 20-customer
  instance, the same direction and magnitude as our raw result from a
  different codebase and problem formulation.

## Finding 8 — the 2-opt polish had a bug on asymmetric costs (fixed)

Found while adding an assertion that 2-opt never makes a route worse.
`two_opt` used the textbook swap delta, which assumes `leg(u, v) == leg(v,
u)`. Our graphs are directed and each direction gets its own congestion
factor, so reversing a segment also changes the direction every internal leg
is driven in. On random asymmetric costs the old code returned a **worse**
tour in 77 of 2,000 cases (up to +46%); on symmetric costs, 0 of 2,000. Fixed
with forward/reverse prefix sums, which give the exact cost of a reversal in
O(1) (`app/core/local_search.two_opt`); 0 of 2,000 now get worse. Regression
test: `test_two_opt_is_exact_for_asymmetric_costs`.

Impact:

- **Raw numbers (Finding 7 headline) are unaffected** — no local search
  involved.
- **Every "polished" figure in Findings 1-6 was computed with the buggy
  2-opt.** Same 30 instances at 50 stops, our PSO, same environment: buggy
  polish gave QPSO 18 wins / 2 ties / 10 losses (+2.2%); corrected polish gave
  14 / 0 / 16 (-0.8%). Treat the polished tables in Findings 1-6 as historical.
- **The memetic mechanism (Finding 3) was affected directly:** it wrote the
  polished route back over each particle's personal best, and the buggy 2-opt
  could make that route worse. See the Finding 3 update.

## Finding 9 — multi-vehicle capacity-constrained routing: the raw edge holds at 20 customers, ties at 50, reverses at 100

Why this was checked: the problem statement asks for capacity constraints and
multiple vehicles, but our engine started out single-vehicle (its capacity
penalty doesn't depend on visiting order), and the teammate's multi-vehicle
engine had PSO ahead on a feasible 50-customer instance (10 of 10 seeds at 200
iterations; still behind at 800). So we tested whether QPSO's raw edge survives
that formulation. (Their 100-customer instance is infeasible, demand 1,520 vs
fleet capacity 1,500, so it isn't usable evidence either way.)

The giant-tour decoder now lives in `app/core/vrp_formulation.py`
(`RoutingProblem`, `RouteRequest.n_vehicles`): the visiting order is cut into
per-vehicle routes by capacity (open the next vehicle when the load would be
exceeded and one is left; the last vehicle takes the rest), same greedy rule as
the teammate's `decode_particle`, with leg costs from shortest paths over the
directed congested graph. It reproduced the original prototype's numbers
exactly. QPSO and PSO are unchanged (40 particles, 800 iterations), raw cost,
capacity 100, demands 5-25, fleet sized for the stated utilization, 20
instances per row, one algorithm seed (`scripts/compare_multi_vehicle.py`).
Every run of both algorithms was feasible, so costs are pure travel time.
Improvement = (PSO - QPSO)/PSO, positive = QPSO better:

| customers (actual fleet utilization) | vs our PSO: QPSO win/loss, improvement, p | vs teammate PSO settings |
|---|---|---|
| 20 (73%) | 18/2, +10.6%, p=0.0002 | 19/1, +11.4%, p<0.0001 |
| 50 (81%) | 11/9, +3.7%, p=0.41 | 10/10, -0.7%, p=0.59 |
| 50 (87%) | 9/11, +0.3%, p=0.75 | 8/12, -4.2%, p=0.87 |
| 100 (83%) | **5/15, -8.0%**, p=0.99 | **0/20, -24.9%**, p=1.0 |

What this says:

- Compared with the single-vehicle raw result (+13-28%), the edge is +10-11%
  at 20 customers, and gone by 50: a statistical tie whose sign depends on the
  PSO settings and the fleet tightness.
- At 100 customers PSO wins clearly. The earlier run (numpy 2.4.6) showed a small
  QPSO edge at 50 customers (+2% to +8%, p = 0.06-0.13) where this run shows a
  tie, but the same collapse at 100 (-7% and -22%), so treat 50 customers as "no
  demonstrated edge" and 100 as a real loss. The teammate's independent engine
  also had PSO ahead at 50 customers.
- Not a budget problem, as far as one check shows: at 100 customers (10
  instances, our PSO, earlier run only) 800 iterations gave QPSO 1 win / 9
  losses (-11.1%) and 2,400 gave 1 / 9 (-12.0%). Both algorithms improved 7-9% with
  3x the iterations but the gap didn't close.
- Why is not established. Untested hypotheses: at 100 dimensions QPSO's jump
  size (proportional to |mbest - x|, roughly 0.25 per coordinate) reorders the
  decoded permutation far more than PSO's velocity-clamped steps, which favors
  PSO's smoother local search; the greedy split decoder may also amplify small
  reorderings. Neither was tested.
- Caveats: 20 instances per row, one algorithm seed, raw cost only (no local
  search), synthetic graphs, and the decoder does no optimization inside a route
  beyond the optional per-route 2-opt.

**Consequence for the pitch: do not claim QPSO scales to large multi-vehicle
instances.** What we can support today: single-vehicle tours up to 50 stops, and
multi-vehicle instances at about 20 customers. Supporting 50-100 customers means
either closing this gap (per-dimension jump scaling or another encoding at high
dimension, retuning beta at 100 customers, a per-route local search that both
algorithms get) or presenting QPSO honestly as competitive rather than dominant
at that scale and benchmarking against stronger baselines (GA, OR-Tools).
Finding 10 is that work.

## Finding 10 — scaling to 50-100 customers: a smaller jump, a warm start, and a stronger polish

Finding 9 left QPSO losing to classical PSO at 100 customers, with two untested
hypotheses. This tests them (`scripts/scale_experiments.py`, parallel, one CSV per
size in `backend/results/scaling/`). Setup as in Finding 9: random capacitated
instances, demands 5-25, capacity 100, fleet sized for at most 85% utilization,
**20 instances per size (seeds 500-519)**, 40 particles x 800 iterations, one
algorithm seed, pinned environment. "Polish" below is the new full polish
(`improve_routes`, point 4); "2-opt only" is the old per-route polish. Cells are
win / tie / loss with the mean improvement (positive = first is better) and a
one-sided exact sign test.

**1. Hypothesis 1 was right: QPSO's jump is too big at 100 dimensions.** A particle
is 100 random keys whose sort order is the tour. QPSO's jump is proportional to the
swarm's spread (about 0.25 per key at the start), which reorders most of a
100-stop tour on every step, so early on it behaves like random sampling; PSO's
velocity-limited steps refine instead. Shrinking the jump flips the result
(100 customers, first 10 instances, raw cost, QPSO vs classical PSO):

| beta start -> end | 1.0 -> 0.2 (old default) | 0.5 -> 0.1 | 0.3 -> 0.05 | 0.15 -> 0.02 | 0.05 -> 0.01 |
|---|---|---|---|---|---|
| win/loss, improvement | 2/8, -11.3% | **9/1, +11.0% (p=0.011)** | 8/2, +6.0% | 8/2, +4.9% | 5/5, -0.5% |

The best jump shrinks with size (20 customers: the old default is best, +10.5%,
and every smaller one is worse; 50: 1.0 and 0.5 tie). So the default is now
`beta = (1.0, 0.2) * min(1, 50 / stops)`. **Up to 50 stops this is bit-identical to
before** (20 of 20 ties at both 20 and 50 customers), so every earlier result stands.
At 100 customers, QPSO vs PSO raw goes from **5 wins / 15 losses (-8.0%)**, which
reproduces Finding 9, to **19 wins / 1 loss (+12.4%, p < 0.0001)**.

**2. But a random start is the bigger problem: at 50-100 customers the swarms lose
to a trivial heuristic, and to a GA by a lot.** Mean cost, raw (no local search):

| customers | nearest neighbour | PSO | QPSO | GA |
|---|---|---|---|---|
| 20 | 1,032 | 950 | 852 | 864 |
| 50 | 2,106 | 2,659 | 2,548 | **2,035** |
| 100 | 3,634 | 6,554 | 5,707 | **4,237** |

Random-key swarms need the tour to be globally coherent, which a 100-dimensional
random search does not find in 32,000 evaluations. QPSO cold is 25% (50) and 35%
(100) worse than the cold GA, in every one of 20 instances (0 wins). More budget
does not fix it (3x the iterations changed the warm-started results by under 1%).

**3. Warm start fixes most of it.** `app/core/warm_start.py` puts two particles in
the population from the start: the nearest-neighbour solution and the same after
2-opt. The rest stay random. The same seeds go to PSO, GA and QPSO, so the
comparison stays fair. QPSO raw cost falls **25% at 50 customers (2,548 -> 1,898) and
39% at 100 (5,707 -> 3,479)**. Both seeds decode back to exactly their own routes
(tested), so the seed is a real member of the population.

**4. A stronger polish: moving stops between vehicles.** The old polish only
reorders stops inside each vehicle's route. `improve_routes` also relocates runs of
1-3 stops from one vehicle to another and swaps stops between vehicles, accepting a
move only if it lowers travel time plus the overload penalty. Every cost change is
exact for our directed, per-direction congestion because none of these moves reverses
a stretch of road (tested: on random asymmetric instances no move ever made a plan
worse). On nearest neighbour + 2-opt it lowers cost by 18% / 12% / 10% at 20 / 50 /
100 customers, in at most 0.14 s.

**5. What is left between the algorithms once everything is warm-started.** Mean
cost after the full polish:

| customers | nearest neighbour + polish | PSO warm | QPSO warm | GA warm |
|---|---|---|---|---|
| 20 | 846 | 822 | **800** | 826 |
| 50 | 1,800 | **1,751** | 1,761 | 1,759 |
| 100 | 3,201 | 3,181 | 3,187 | **3,148** |

| QPSO warm vs ... | 20 customers | 50 customers | 100 customers |
|---|---|---|---|
| PSO warm, raw | 11/7/2, +1.9%, p=0.011 | 10/1/9, +0.7%, p=0.50 | 4/0/16, -0.7% (PSO better, p=0.006) |
| PSO warm, polished | **10/10/0, +2.8%, p=0.001** | 8/1/11, -0.6%, p=0.82 | 9/0/11, -0.2%, p=0.75 |
| GA warm, polished | 11/5/4, +3.2%, p=0.059 | 9/1/10, -0.4%, p=0.68 | 4/1/15, -1.2% (GA better, p=0.010) |
| nearest neighbour + polish | 15/3/2, +4.9%, p=0.001 | 14/1/5, +1.9%, p=0.032 | 8/9/3, +0.4%, p=0.11 |

**What this supports, and what it does not.**

- QPSO's edge over classical PSO is real and robust at about 20 customers, cold
  (raw +10.5%, 18 of 20) and warm-started and polished (+2.8%, 10 wins, 0 losses).
- At 50 customers QPSO, PSO and GA are indistinguishable once warm-started; all
  are about 2% better than nearest neighbour + polish.
- At 100 customers the pipeline does the work. QPSO is 0.4% better than nearest
  neighbour + polish (not significant), and 1.2% *worse* than the warm GA after the
  polish (1.3% worse raw, 2 wins of 20, p = 0.0002 for GA). The
  claim "QPSO scales better than other metaheuristics" is **not supported**.
- What did change is the app itself. Its default result (cold QPSO, old jump,
  2-opt-only polish before; warm QPSO, size-aware jump, full polish now) is
  **5.4% lower at 20 customers (15 wins, 4 losses, p = 0.01), 22.8% lower at 50
  (20 wins, 0 losses) and 40.4% lower at 100 (5,346 -> 3,187; 20 wins, 0 losses).**
- Turning warm start off keeps the algorithm comparisons of Findings 7-9 exactly
  as published, and is the right setting to show the algorithms competing.

**Also changed.** The genetic algorithm's crossover now uses a vectorized fill
instead of a slow membership test, with exactly the same children (checked against
the original on 300 random cases): a 100-customer GA run fell from about 41 s to
5 s, which is what makes a 100-stop benchmark in the UI usable.

**Caveats.** 20 instances per size, one algorithm seed, synthetic graphs,
one specific pair of seeds (nearest neighbour and its 2-opt). The `s/run` column in
the harness is inflated by running 10 processes at once. One real check on MG Road,
Bengaluru (871 intersections, 100 stops, 16-17 vehicles, one instance): QPSO cold
285.0 -> warm 176.2 raw, 155.9 after the polish, the same as nearest neighbour +
polish there; a single instance says nothing about averages (cold + polish happened
to reach 151.8 on it).

Reproduce (from `backend/`; `qpso_b1.0_0.2` is the old fixed schedule):

```
python scripts/scale_experiments.py --customers 100 --instances 20 --polish full --variants qpso_b1.0_0.2 qpso ga pso_warm qpso_warm ga_warm --csv results/scaling/scaling_100customers.csv
python scripts/scale_experiments.py --customers 100 --instances 10 --variants qpso_b1.0_0.2 qpso_b0.5_0.1 qpso_b0.3_0.05 qpso_b0.15_0.02 qpso_b0.05_0.01
python scripts/scale_experiments.py --list
```

## Finding 11 — a hybrid architecture for 100+ stops beats classical PSO, but the QPSO update is not what does the work

**The question.** Can a QPSO built as *adaptive random-key QPSO + elite archive + 2-opt
+ diversity restart + hybrid initialization* beat classical PSO at 100 stops, and does
it keep working on larger tours? Engine: `app/core/hybrid_swarm.py` (each component is a
switch; the search operator is swappable between QPSO and classical PSO, and with every
component off it reproduces plain QPSO and plain PSO bit for bit, tested). Experiments:
`scripts/hybrid_experiments.py`, numbers from `scripts/summarize_hybrid.py`, per-run CSVs
and the OR-Tools reference tours in `backend/results/hybrid/`.

**What already existed and what is new.**

| Component | Before | Now |
|---|---|---|
| Random-key QPSO: quantum update, personal best, permutation decoder | yes | unchanged |
| Adaptive beta | fixed schedule, scaled with size (Finding 10) | times a multiplier steered by the fraction of particles improving (the 1/5 success rule) |
| Hybrid initialization | nearest neighbour and its 2-opt (warm start) | plus 25% of the swarm from randomized nearest neighbour + 2-opt |
| Elite archive | none: one global best | the 8 best distinct tours; each particle's attractor is a random elite, biased to the best |
| 2-opt | final polish only; whole-swarm version hurt (Finding 3) | on the best 3 not-yet-polished swarm tours, every 10 iterations, written back |
| Diversity restart | random restarts, opt-in, negative on small problems (Finding 5) | after 40 stalled iterations or when the swarm collapses: the worst 25% restart from a double-bridge-kicked elite or a randomized nearest-neighbour tour, each followed by 2-opt |

The first version polished only the archive's elites and never beat its own seed:
the elites were seeded 2-opt optima, and swarm-found tours (about 4 times worse) never
reached the archive. Applying 2-opt to swarm tours and to restarted tours fixed that.

**Setup.** Single vehicle visiting N stops over a directed congested graph (100 to 400
nodes), 20 instances (seeds 300-319) at 50 and 100 stops and 10 at 150 and 200, 40
particles x 800 iterations, one algorithm seed. "Cost" is measured after the same final
2-opt for every method, the only like-for-like comparison (the hybrids' raw result
already contains the 2-opt they run inside the search). The reference is OR-Tools'
guided local search (10 / 30 / 45 / 60 s at 50 / 100 / 150 / 200 stops) with the cost
matrix handed over as data (`scripts/ortools_reference.py`), run in a separate
environment. It is a strong reference, not a proven optimum, and it is ahead of every
method here: the hybrid QPSO beat it on 1 of 20 instances at 100 stops and on none at
50, 150 or 200.

**1. Yes, it beats classical PSO, decisively.** 100 stops, mean cost after the polish:

| | bare PSO | bare QPSO | GA | nearest neighbour + 2-opt | hybrid PSO | **hybrid QPSO** | OR-Tools |
|---|---|---|---|---|---|---|---|
| cost | 1,234 | 1,273 | 1,290 | 1,114 | 1,014 | **1,013** | 981 |
| vs bare PSO | | -3.5% | -4.9% | +9.4% | +17.5% | **+17.5%, 20 wins, 0 losses** | |
| above OR-Tools | +25.8% | +29.7% | +31.6% | +13.6% | +3.3% | **+3.2%** | |

**2. But a hybrid PSO ties it: the quantum update is not the reason.** Hybrid QPSO vs
hybrid PSO, same components (adaptive beta exists only for QPSO), cost after the polish:

| stops | QPSO wins / PSO wins | mean difference (QPSO better is +) | p, QPSO better | p, PSO better |
|---|---|---|---|---|
| 50 | 6 / 14 | -0.5% | 0.98 | 0.058 |
| 100 | 10 / 10 | +0.1% | 0.59 | 0.59 |
| 150 | 6 / 4 | +1.3% | 0.38 | 0.83 |
| 200 | 6 / 3 (1 tie) | +0.5% | 0.25 | 0.91 |

No size shows a significant difference in either direction.

**3. What does the work (ablation at 100 stops, QPSO operator).** Cost after the polish,
20 instances; improvement is over bare PSO (1,234):

| add one component to bare QPSO | cost | improvement | | drop one from the full hybrid | cost | improvement |
|---|---|---|---|---|---|---|
| adaptive beta | 1,237 | -0.7% | | without adaptive beta | 1,010 | +17.7% |
| elite archive + attractor | 1,262 | -2.6% | | without elite attractor | 1,012 | +17.6% |
| hybrid initialization | 1,079 | +12.3% | | without hybrid initialization | 1,007 | +18.0% |
| 2-opt on swarm tours | 1,043 | +15.1% | | without 2-opt on swarm tours | 1,012 | +17.6% |
| diversity restart (kick + 2-opt) | **1,015** | **+17.4%** | | without diversity restart | **1,046** | +14.9% |

The restart alone gets nearly all of the way, and removing it costs the most: kick a
good tour, 2-opt it, keep it if better is iterated local search, with a swarm alongside.
Adaptive beta and the elite attractor contribute nothing measurable; hybrid
initialization helps a bare swarm but is not needed once restarts exist.

**4. Scaling to larger tours.** Mean cost after the polish, as % above the OR-Tools
reference (lower is better); one run takes this long on an idle machine:

| stops | bare PSO | bare QPSO | GA | nearest neighbour + 2-opt | hybrid PSO | hybrid QPSO | hybrid QPSO run time (bare QPSO) |
|---|---|---|---|---|---|---|---|
| 50 | +19.2% | +16.6% | +22.6% | +9.2% | +0.9% | +1.3% | 2.2 s (0.8 s) |
| 100 | +25.8% | +29.7% | +31.6% | +13.6% | +3.3% | +3.2% | 12.0 s (2.2 s) |
| 150 | +42.4% | +33.5% | +42.3% | +12.1% | +7.0% | +5.6% | 30.3 s (3.9 s) |
| 200 | +43.2% | +41.1% | not run | +12.1% | +7.0% | +6.4% | 44.3 s (4.9 s) |

The bare methods fall further behind as tours grow (to about 40% above at 200 stops);
the hybrids stay within 1-7% of OR-Tools from 50 to 200 stops, with the gap widening
as tours grow, and nearest neighbour + 2-opt sits at 9-14% above throughout. About 80%
of the hybrid's time is 2-opt in pure Python (profiled).

**5. The update rule on its own.** Bare QPSO (with Finding 10's size-aware jump) vs bare
PSO, QPSO win / tie / loss with mean improvement:

| stops | raw | after the same 2-opt |
|---|---|---|
| 50 | 18/0/2, +20.5%, p = 0.0002 | 12/0/8, +1.3%, p = 0.25 |
| 100 | 15/0/5, +8.4%, p = 0.021 | 9/0/11, -3.5%, PSO better in 11, not significant |
| 150 | 10/0/0, +14.3%, p = 0.001 | 9/0/1, +5.9%, p = 0.011 |
| 200 | 10/0/0, +16.2%, p = 0.001 | 5/0/5, +0.3%, p = 0.62 |

So the raw edge over classical PSO holds at every size, as in Finding 7, and 2-opt
removes it or leaves it inconsistent.

**6. On the multi-vehicle problem the hybrid adds nothing.** 100 customers, capacity 100,
fleet for at most 85% utilization, seeds 500-519, cost after the full polish (2-opt plus
moving stops between vans): warm PSO 3,181, warm QPSO 3,187, **hybrid QPSO 3,192**,
hybrid PSO 3,183, nearest neighbour + polish 3,201 (Finding 10's numbers, reproduced).
With about 16 vans a route has only 6 stops, so in-search 2-opt has almost nothing to
fix, and the gains come from moving stops between vans, which the final polish already
gives every method (it cannot run inside the search because a route set does not always
decode back from its concatenation).

**What this supports, and what it does not.**

- Supported: the architecture takes a 100-stop single-vehicle tour from 26% above the
  reference (bare PSO) to 3.2% above, and stays within 6.4% at 200 stops. It does not
  match OR-Tools: the gap grows from 1% at 50 stops to 6% at 200.
- Supported: with the size-aware jump, bare QPSO beats bare PSO on raw cost at every
  size from 50 to 200 stops.
- Not supported: that the quantum update is what makes the hybrid work. A hybrid PSO with
  the same components is indistinguishable from it.
- Not supported: any benefit for the multi-vehicle problem in its current formulation.

**Caveats.** 10-20 instances, one algorithm seed, synthetic graphs. The hybrids' 2-opt is
plain 2-opt (no Or-opt or 3-opt), and their budget is fixed at 800 iterations: on some
instances they are still improving at the end. The OR-Tools time limits are short (it
would only improve with more time).
Adaptive beta and the elite attractor were not tuned. The engine is a library and
benchmark tool; it is not yet selectable in the API or UI. A vectorized 2-opt was
tried and dropped: correct, but only 1.4-2.5x faster on the tours that matter.

Reproduce (from `backend/`; OR-Tools reference tours were made in a separate virtual
environment, so the project's pinned one is untouched):

```
python scripts/hybrid_experiments.py --problem tsp --stops 100 --instances 20 --variants pso qpso h_qpso h_pso ga pso_warm qpso_warm --csv results/hybrid/tsp100.csv --best-known results/hybrid/tsp100_best_known.csv
python scripts/hybrid_experiments.py --problem tsp --stops 100 --instances 20 --variants h_qpso a_init a_beta a_elite a_ls a_restart d_init d_beta d_elite d_ls d_restart --csv results/hybrid/tsp100_ablation.csv
python scripts/hybrid_experiments.py --problem cvrp --stops 100 --instances 20 --variants pso_warm qpso_warm h_qpso h_pso ga --reference pso_warm
python scripts/summarize_hybrid.py
```

## Finding 12 — an optimal Split decoder is worth about 1%, and is not what separates us from OR-Tools

**The question.** Multi-vehicle routing here cuts one visiting order (the giant tour) into vehicle routes with a
greedy rule. An external review called replacing it with the optimal Split (Prins) the most important remaining
experiment: every permutation would be scored at its best partition, and local-search results could be written
back into the search safely. Is the greedy decoder what holds the multi-vehicle search back?

**What was built.** `RouteRequest.decoder = "optimal"` (default `"greedy"`, so every earlier number stands).
For a fixed order the cheapest capacity-respecting partition is found in linear time with a sliding-window
minimum (Vidal 2016), and with a layered version when the fleet limit binds; when no partition fits the
fleet it falls back to the greedy rule so the soft-penalty behaviour is unchanged. Tests check it against
exhaustive search over every possible cut on 9-stop instances (including the fleet-limited case), that it is
never worse than greedy, that `cost()` always agrees with the routes it describes, and that concatenating any
route set (for example the output of `improve_routes`) and splitting optimally never costs more than the
routes did. That last property is the one greedy decoding lacks.

**Reference.** OR-Tools' capacitated routing with guided local search, 60 s per instance, same fleet and
capacity, cost matrix and demands handed over as data, run in a separate environment
(`scripts/ortools_reference.py`, `backend/results/hybrid/cvrp100_best_known.csv`): mean **2,937.9** on the 20
instances of Findings 10-11 (100 customers, seeds 500-519). It is a strong reference, not a proven optimum.

**1. Same method, greedy vs optimal decoder** (cost after the same final polish; optimal wins / ties / losses
per instance; sign test on the optimal being better):

| method | greedy | optimal | change | optimal wins/ties/losses | p | above OR-Tools, optimal / greedy |
|---|---|---|---|---|---|---|
| nearest neighbour + polish | 3,201 | 3,161 | +1.3% | 9/7/4 | 0.13 | +7.7% / +8.9% |
| warm PSO | 3,181 | 3,148 | +1.0% | 11/0/9 | 0.41 | +7.3% / +8.4% |
| warm QPSO | 3,187 | 3,156 | +1.0% | 11/2/7 | 0.24 | +7.5% / +8.5% |
| warm GA | 3,148 | 3,120 | +0.9% | 10/0/10 | 0.59 | +6.3% / +7.2% |
| hybrid QPSO | 3,192 | 3,146 | +1.4% | 13/3/4 | 0.025 | +7.2% / +8.7% |
| hybrid PSO | 3,183 | 3,148 | +1.1% | 11/3/6 | 0.17 | +7.2% / +8.3% |

Every method gains about 1%, but for five of the six the gain is not statistically clear on 20 instances.
The three swarm methods stay tied with each other under either decoder (warm QPSO vs warm PSO with the optimal
decoder: 7 wins, 12 losses, -0.2%), and the warm GA stays slightly ahead.

**2. It does not come from the finished routes.** Concatenating the finished, polished routes and re-cutting
them optimally lowers cost by **0.00%** for both nearest neighbour and warm PSO: the polished routes are already
optimal cuts of themselves.

**3. It looks like a different starting point for the local search.** What `improve_routes` reaches on the
same 20 instances from different starts (mean cost):

| start | cost | vs A |
|---|---|---|
| A nearest neighbour, greedy cut | 3,201 | |
| B nearest neighbour, optimal cut | 3,161 | +1.25% (better on only 9 of 20) |
| C' best of 10 randomized starts, greedy cut | 3,160 | +1.29% |
| D' best of 10 randomized starts, optimal cut | 3,179 | +0.71% |
| C mean of 10 randomized starts, greedy cut | 3,340 | -4.34% |

Taking the best of ten randomized starts gains as much as the decoder does, and the average random start is
much worse. The decoder's ~1% is the size of the local search's start-to-start variation.

**4. It is expensive in the loop.** Per evaluation at 100 customers: 0.8-2.2 ms against 0.03-0.08 ms for the
greedy cut (30-80x; times here and below are with 8 processes running in parallel). For most random orders the fleet limit binds and the layered version runs, and the
swarm's orders start out random. A 100-customer run takes 80-110 s instead of 7-15 s. The layered search was
not optimized (restricting each layer to the band of feasible route counts could plausibly give about 4x).

**What this supports, and what it does not.**

- The greedy decoder is not what holds the multi-vehicle search back. Whichever decoder is used, the
  pipelines end 6.3-7.7% above OR-Tools' 60 s solution (7.2-8.9% with greedy), so there is real headroom and it is
  elsewhere: OR-Tools searches with a much richer set of inter-route moves and guided local search.
- The decoder's real value is the write-back property, which lets inter-route local search run inside the
  swarm loop. Whether that is worth its cost is Finding 13's question.
- Not supported: that QPSO gains more from a better decoder than PSO does. All swarm methods gained alike.

**Caveats.** 20 instances, one algorithm seed, synthetic graphs. The reference is one OR-Tools configuration
for 60 s. The hybrid engines' in-loop local search is still per-route 2-opt.

Reproduce (from `backend/`; the CSVs are in `results/hybrid/`):

```
python scripts/hybrid_experiments.py --problem cvrp --stops 100 --instances 20 --decoder optimal --variants pso_warm qpso_warm ga_warm h_qpso h_pso --reference pso_warm --csv results/hybrid/cvrp100_optimal.csv
python scripts/decoder_analysis.py
```

## Finding 13 — a stronger search between routes beats the OR-Tools reference, and the swarms add nothing on top of it

**The question.** Finding 12 left our multi-vehicle pipelines 6-9% above OR-Tools and pointed at the likely reason:
OR-Tools searches with richer moves between routes than our polish (relocate, swap, 2-opt). If our search between routes
is as strong as OR-Tools', where does that leave us, and do QPSO, PSO or GA still add anything? (The external review
pictured the swarm as the "global diversification" engine and local search as the "intensification".)

**What was built.** `app/core/route_search.py`, a search over whole sets of routes:

- five moves, each scored exactly for our directed, congested travel times: relocate a run of 1-3 stops, swap two
  stops, **2-opt\*** (two routes exchange their tails), **SWAP\*** (two stops from different routes each go to their
  best position in the other's route, not necessarily where the other stop was) and 2-opt inside a route;
- a stop is only paired with its 12 nearest stops, and after a move only the routes it touched are re-examined, so
  repairing a small change costs milliseconds instead of a full scan;
- exactly `n_vehicles` route slots (a van can be emptied, an idle one can be used), cost = travel time + 1000 x overload;
- **iterated local search (ILS)**: remove a cluster of 4-12 nearby stops, reinsert each at its cheapest position,
  repair with the local search, keep the result if it is better, and restore the best one at the end.

29 tests (`tests/test_route_search.py`): the tracked cost always equals an independent evaluation; every stop is served
once and the fleet limit holds; relocate, swap, 2-opt\* and SWAP\* are each checked against exhaustive search on small
instances; a search never returns something worse (or overloaded) from a feasible start; ILS never gets worse and
repeats for a given seed.

**Reference.** The same as Finding 12: OR-Tools guided local search, 60 s per instance, mean **2,937.9** on the 20
instances of Findings 10-12 (100 customers, seeds 500-519). Every number below is on those instances unless it says
otherwise. "Above OR-Tools" is the mean of the per-instance gaps, so negative means our routes are cheaper.

**1. Which moves matter.** Local search only, starting from nearest-neighbour routes. Wins/ties/losses compare each
row with the older polish (`improve_routes`) per instance; the p-value is a sign test on the row being better. Seconds
are per instance, one process on an idle machine.

| moves | mean cost | above OR-Tools | seconds | wins/ties/losses vs older polish |
|---|---|---|---|---|
| older polish (`improve_routes`: 2-opt, relocate, swap, full sweeps) | 3,201 | +8.9% | 0.11 | |
| relocate | 3,261 | +11.1% | 0.02 | 6/0/14 |
| relocate + swap | 3,217 | +9.8% | 0.03 | 10/0/10 |
| relocate + swap + 2-opt (the older polish's moves) | 3,194 | +8.8% | 0.03 | 8/0/12 |
| ... + 2-opt\* | 3,128 | +6.6% | 0.03 | 11/0/9 |
| ... + SWAP\* (instead of 2-opt\*) | 3,156 | +7.6% | 0.04 | 11/0/9 |
| ... + both (all five) | **3,078** | **+4.9%** | 0.05 | **15/0/5, p = 0.021** |
| all five without relocate | 3,167 | +7.9% | 0.02 | 12/0/8 |
| all five without swap | 3,089 | +5.2% | 0.04 | 14/0/6, p = 0.058 |
| all five without 2-opt | 3,111 | +6.1% | 0.05 | 16/0/4, p = 0.006 |

- The older polish's three moves, run through neighbour lists and a work queue, reach the same cost (3,194 against
  3,201; 8 wins, 12 losses) in about a quarter of the time.
- 2-opt\* is worth 2.1% on top of them and SWAP\* 1.2%; together they are worth 3.6%. Only the combination is
  significantly better than the older polish (15 wins, 5 losses); each alone is 11/0/9.
- Taking any one move out of the five costs between 0.4% (swap, the most redundant) and 2.9% (relocate).
- Local search alone (0.05 s) cuts the gap to OR-Tools from +8.9% to +4.9%. OR-Tools' 60 s tour is still better on 19
  of the 20 instances at this point.

**2. Iterated local search.** From nearest neighbour, local search, then ILS with the default settings:

| | local search only | ILS 100 | ILS 200 | ILS 500 | ILS 1,000 | OR-Tools |
|---|---|---|---|---|---|---|
| mean cost | 3,078 | 2,898 | 2,886 | 2,871 | 2,861 | 2,938 |
| above OR-Tools | +4.9% | -1.3% | -1.7% | -2.3% | **-2.6%** | |
| instances cheaper than OR-Tools | 1 of 20 | 18 | 18 | 19 | **20** | |
| time (about 10 ms per iteration) | 0.05 s | 1 s | 2 s | 5 s | 10 s | 60 s |

At 1,000 iterations (about 10 s) it is cheaper than the 60 s OR-Tools reference on all 20 instances, by 1.2% to 5.5%; at
100 iterations (about a second) it already wins 18 of 20. The final routes of all 80 runs in this experiment were
recomputed from scratch and checked (each stop once, no overloaded van, fleet limit, and the search's own cost equal
to the recomputed one). On three instances the cost was also recomputed from the cost matrix exported for OR-Tools
(a one-off check, not in the repo's scripts), and all three ways agreed to the cent.

The default settings were not fitted to these instances. On ten others (seeds 600-609, ILS 200 iterations) a smaller
ruin (3-8 stops) or 8 neighbours were 0.7-0.8% worse (1 win, 9 losses each); a larger ruin (8-20 stops) was 0.4% better
but took 1.9x as long, 20 neighbours 0.1% better at 1.7x, and accepting solutions up to 0.1% or 0.3% worse changed
nothing (+0.1% and 0.0%). The defaults sit on a plateau (`scripts/route_search_ablation.py tuning`).

**3. Do the swarms add anything?** Same local search and ILS, same random stream, same instances. The pipelines differ
only in the routes they start from: nearest neighbour ("nn"), or the routes returned by a warm-started PSO, QPSO or GA
(40 particles x 800 iterations, greedy decoder).

| starting routes from | swarm phase | cost of the start | after local search | ILS 200 | ILS 1,000 | vs nn at ILS 1,000 (wins/ties/losses) | same total time as nn, ILS 1,000 |
|---|---|---|---|---|---|---|---|
| nn | 0 s | 3,634 | 3,078 | 2,886 | 2,861 | | |
| PSO | 2.6 s | 3,457 | 3,096 | 2,884 | 2,864 | 8/1/11, -0.1% | 7/1/12, -0.2% |
| QPSO | 2.8 s | 3,479 | 3,062 | 2,882 | 2,860 | 5/13/2, 0.0% | 4/10/6, -0.1% |
| GA | 1.1 s | 3,495 | 3,059 | 2,881 | 2,861 | 5/10/5, -0.1% | 5/7/8, -0.1% |

- The swarms' routes start 4-5% cheaper than nearest neighbour's, but local search takes that away: after it the four
  are within 1.2% of each other, and after 1,000 ILS iterations within 0.15%.
- At the same number of ILS iterations, 1 of the 12 comparisons against nn is below p = 0.05 (GA at 100 iterations:
  9 wins, 10 ties, 1 loss, +0.2%, p = 0.011), and it is gone by 500 iterations. That is the kind of result twelve
  comparisons produce by chance.
- The swarm phase costs time nn does not spend: about 240 (PSO), 270 (QPSO) and 110 (GA) ILS iterations' worth. Given
  that time back as extra ILS iterations, nn is equal or better in every comparison: QPSO at 100 iterations
  1 win, 19 losses (-0.9%); by 1,000 iterations the difference is 0.1% and not significant.
- QPSO against PSO, same start budget, ILS 100 / 200 / 500 / 1,000: 11/1/8, 9/1/10, 7/1/12, 10/2/8 wins/ties/losses, all
  differences at most 0.1%, no p below 0.3.

**Why the swarm adds nothing here.** On 12 of the 20 instances the QPSO routes end, after local search, at exactly the
same cost as nearest neighbour's (10 of 20 for GA; PSO never), and the ILS that follows takes the same path. Checked on
two of them, the swarm's routes contain exactly the same groups of stops per van as the nearest-neighbour routes; the
swarm only reordered stops inside vans, and the local search's own 2-opt does that anyway. What the swarm was asked to
find, a better way of dividing the customers among vans, is what the moves between routes do better and faster.
This is Finding 12 again from the other side.

**4. Speed and size.** One instance per size (seed 500; capacity 100, demands 5-25, fleet for 85% utilisation, about
6 stops per van), idle machine. Treat these numbers as rough: an earlier run of the same measurement gave 0.04-0.08 s
for the local search and 9-11 ms per iteration.

| customers | local search from nearest neighbour | one ILS iteration |
|---|---|---|
| 50 | 0.07 s | 8 ms |
| 100 | 0.03 s | 10 ms |
| 150 | 0.04 s | 12 ms |
| 200 | 0.13 s | 14 ms |

Each iteration only touches a cluster of stops and the routes around it, so the cost per iteration grows slowly with
size. Solution quality at 150 and 200 customers has not been measured (there is no OR-Tools reference there).

**5. One van is different.** The same search on a single-vehicle tour (the instances of Finding 11, seeds 300-319),
nearest neighbour then 1,000 ILS iterations:

| stops | local search only | ILS 1,000 | hybrid QPSO (Finding 11) | OR-Tools |
|---|---|---|---|---|
| 50 | 731.8 (+3.5%) | 719.4 (+1.7%) | 716.4 (+1.3%) | 707.2 |
| 100 | 1,047.1 (+6.8%) | 1,006.9 (+2.7%) | 1,013.0 (+3.2%) | 981.3 |

ILS is better than the hybrid QPSO on 12 of 20 instances at both sizes and better than OR-Tools on 4 and 3, so it is
about as good as the hybrid, but far slower: 70 s per instance at 50 stops and about 5 minutes at 100 (measured with 8 processes running, so
somewhat pessimistic), against 2.2 s and 12 s for the hybrid on an idle machine. With one van every move
touches the whole route and 2-opt inside a route is quadratic. The search is built for fleets; for one long tour use the
hybrid engine.

**What this supports, and what it does not.**

- Supported: on these instances (100 customers, synthetic graphs, 85% utilisation) nearest neighbour + this local search
  reaches 4.9% above the 60 s OR-Tools reference in 0.05 s, and with 1,000 ILS iterations (about 10 s) it is 2.6% below it,
  cheaper on all 20 instances. The moves between routes, 2-opt\* and SWAP\* above all, are what closes the gap that
  Finding 12 left open.
- Supported: used to produce starting routes for this search, QPSO, PSO and GA add nothing measurable at 100 customers,
  and QPSO and PSO are indistinguishable.
- Not supported: that this beats OR-Tools in general. It is one OR-Tools configuration (guided local search, one
  thread, 60 s, untuned) on one instance family. Nor that it is near optimal: the state of the art for this problem
  (HGS-CVRP) would very likely beat both; how far from optimal we are is measured in Finding 14.
- Not tested: a swarm with the route search inside its loop (particles improved by the search every iteration). Only
  "swarm first, search after" was tested, so this finding does not show that a swarm cannot help in that role.
- Not tested here: looser or tighter fleets (long routes make each iteration slower, see 5), real OSM graphs. Other sizes
  on road graphs: Finding 15.

**Caveats.** 20 instances, one algorithm seed per instance. The time-matched comparison uses times measured with 8
processes running and reads nearest neighbour at the next multiple of 100 iterations, which favours it by up to 99
iterations (about a second). The ILS settings were checked on 10 other instances, not tuned on these. The OR-Tools
reference is from Finding 12, with its caveats.

Reproduce (from `backend/`; the CSVs are in `results/hybrid/`):

```
python scripts/route_search_experiments.py --instances 20 --workers 8 --csv results/hybrid/cvrp100_route_search.csv
python scripts/route_search_experiments.py --from-csv results/hybrid/cvrp100_route_search.csv
python scripts/route_search_ablation.py operators --csv results/hybrid/cvrp100_route_search_operators.csv
python scripts/route_search_ablation.py tuning --csv results/hybrid/cvrp100_route_search_tuning.csv
python scripts/route_search_ablation.py timing
python scripts/route_search_ablation.py tours
```

## Finding 14 — against standard instances with proven optima, the new search is 1.5% above optimal after two minutes, and the old app default was 10% above

**The question.** Findings 11-13 compared us with other heuristics (OR-Tools' guided local search, our own older
pipelines) on synthetic instances, where nobody knows the optimum. So how far from optimal are we, and does the result
of Finding 13 survive a benchmark we did not build?

**Instances.** The CVRPLIB "X" set (Uchoa et al., 2017), the standard benchmark for capacitated vehicle routing: the 22
instances with 100-199 customers, X-n101-k25 to X-n200-k36, every one with a **proven optimal** cost. They were fetched
from CVRPLIB (`galgos.inf.puc-rio.br/cvrplib`) by `scripts/fetch_cvrplib.py` into `backend/data/cvrplib/` (85 KB, git-ignored
because it is third-party data). The script saves nothing unless a file parses, its solution is feasible, and the
solution's cost matches both the CVRPLIB listing and a recomputation from the coordinates. The instances differ from
our synthetic ones in ways that matter: plane distances (no roads, no traffic), central, eccentric and random depots,
random and clustered customers, several demand distributions, and 3 to 24 customers per van (our synthetic ones have
about 6).

**Scoring.** `app/data/cvrplib.py` follows the benchmark's convention: the distance between two points is the Euclidean
distance rounded to the nearest integer, used as given (no shortest-path shortcuts, which rounding can make wrong by a
unit), and a solution costs the sum of its legs. Checked on the real files: the published optimal solution of all 22
instances, recomputed with our distance function, costs exactly what its file says. Every answer any solver returned
here was re-scored from the coordinates and re-checked (each customer once, no van over capacity, fleet limit)
without using the solver's own numbers. The fleet allowed is ceil(1.25 x k) + 2 vans, where k, from the name, is the
fewest vans that can carry the demand; the script checks that the optimal solution itself fits in that fleet.

**What was run** (one run per instance, seed 1, 8 instances at a time on one machine): the new pipeline of Finding 13
(nearest neighbour, local search, then ILS read at cumulative 10 / 30 / 60 / 120 s); the app's default before Finding 13
(warm-started QPSO, 40 particles x 800 iterations, then the older polish `improve_routes`); OR-Tools guided local search
for 60 s with the cost matrix handed over as data, the same configuration as the reference in Findings 12-13
(`scripts/ortools_reference.py --problem cvrplib`). "Gap" is (cost - optimal) / optimal, averaged over the instances.

| method | mean gap | median | worst | within 2% of optimal | time per instance |
|---|---|---|---|---|---|
| nearest neighbour, greedy cut (the start) | 29.8% | 25.4% | 52.0% | 0 of 22 | |
| app default until Finding 13 (warm QPSO + older polish) | 10.2% | 9.9% | 22.3% | 0 of 22 | 15.7 s (worst 22 s) |
| OR-Tools guided local search | 5.5% | 4.8% | 13.0% | 0 of 22 | 60 s |
| route search, local search only | 8.3% | 7.0% | 22.1% | 0 of 22 | 0.7 s (worst 2.5 s) |
| ... + ILS, 10 s | 2.9% | 3.1% | 6.4% | 7 of 22 | 10 s |
| ... + ILS, 30 s | 2.0% | 1.7% | 6.3% | 14 of 22 | 30 s |
| ... + ILS, 60 s | 1.7% | 1.4% | 6.3% | 17 of 22 | 60 s |
| ... + ILS, 120 s | **1.5%** | 1.2% | 4.6% | **18 of 22** | 120 s |

At 120 s six instances are within 1% of optimal, all 22 within 5%, and X-n110-k13 was solved to optimality (0.00%
from 60 s on). OR-Tools is within 5% on 12 of 22. The time buys less and less: going from 10 to 30 s takes 0.9 points
off the mean gap, going from 60 to 120 s takes 0.26.

**Against OR-Tools, instance by instance** (wins/ties/losses of our cost against its 60 s cost; mean cost difference,
negative = cheaper; sign test on being cheaper):

| | wins/ties/losses | mean difference | p |
|---|---|---|---|
| local search only (0.7 s) | 7/0/15 | +2.7% | 0.97 |
| ILS 10 s | 19/0/3 | -2.4% | 0.0004 |
| ILS 30 s | 21/0/1 | -3.2% | < 0.0001 |
| ILS 120 s | 21/0/1 | -3.8% | < 0.0001 |

The app default was worse than OR-Tools on all 22 (+4.5%).

**What this shows.**

- **Finding 13 holds on a benchmark we did not build.** On the synthetic instances local search alone was 4.9% worse than
  OR-Tools and 1,000 ILS iterations 2.6% better; here the same two numbers are +2.7% and -2.4% (10 s) to -3.8% (120 s).
  That the pipeline beats OR-Tools is not a quirk of our instance generator.
- **We can now say how far from optimal.** About 3% at 10 s, 2% at 30 s and 1.5% at two minutes, on average over 22
  standard instances, against 5.5% for OR-Tools' 60 s solution. On the synthetic instances of Finding 13 the optimum is
  unknown, so "2.6% below OR-Tools" there could not be turned into a distance from optimal; the similar edge here, 2.4%
  below OR-Tools at 10 s, corresponds to about 3% above optimal (an inference for the synthetic instances, a measurement
  for these).
- **The app default was far from optimal.** 10.2% above on average, between 4.0% and 22.3% on the individual instances,
  and it took 15.7 s, longer than 10 s of the new search, which is at 2.9%. The local search alone (0.7 s) already beats
  it (8.3%).
- **What is left.** The instances that stay farthest from optimal at 120 s are X-n125-k30 (4.6%; it sat at 6.3-6.4% from
  10 s to 60 s), X-n153-k22 (3.9%), X-n167-k10 (2.7%) and X-n200-k36 (2.2%). The search keeps only improvements, so it
  cannot climb out of a deep local optimum; the usual remedies (accepting worse solutions with a cooling schedule as in
  SISR, or a population with crossover as in HGS) were not tried. Dedicated solvers are reported in the literature to
  average well under 1% on these instances; we did not run one, and this search is not in that class.
- **By route length**, at 120 s: the 6 instances with fewer than 6 customers per van average 1.9%, the 10 with 6-13
  average 1.3%, the 6 with more than 13 average 1.25%. Speed differs more than quality: about 25, 13 and 7 ILS iterations
  per second respectively (8 processes running), against about 100 per second on the synthetic instances. Routes with
  many stops are slower (Finding 13 said so); that shorter routes are also slower than on the synthetic set was not
  investigated.
- The ILS solutions use 0.55 vans more than the optimal ones on average.

**Not tested / not supported.** Real roads, directed and congested travel times (these instances are Euclidean); more than
200 customers; time windows. That this is a state-of-the-art CVRP solver: it is not. The 8 instances running at once
make the 10-120 s figures depend on the machine's load, so they reproduce to within a few tenths of a percent, not
exactly. One run per instance, no repeated seeds. OR-Tools was run as one configuration (guided local search, one thread,
60 s); tuned or given more time it would do better.

Reproduce (from `backend/`; the CSVs are in `results/cvrplib/`; the first two lines need the internet):

```
python scripts/fetch_cvrplib.py
python scripts/cvrplib_benchmark.py --csv results/cvrplib/x_100_200.csv
python scripts/ortools_reference.py export --problem cvrplib --dir C:/tmp/ortools_cvrplib
python scripts/ortools_reference.py solve --problem cvrplib --dir C:/tmp/ortools_cvrplib --seconds 60 --csv results/cvrplib/x_100_200_ortools.csv
python scripts/cvrplib_benchmark.py --from-csv results/cvrplib/x_100_200.csv
```

(`export` runs in the project environment; `solve` in any environment with `pip install ortools`.)

## Finding 15 — as an option in the app, the route search finds cheaper plans than the default at every size tested

**The question.** The route search (Finding 13) is now an option in the app, and the default is still QPSO with a warm
start and the polish. Finding 14 compared the search with the older default at 100-199 customers on Euclidean
instances. At the sizes the app is used at, 15 to 100 stops on a road network with directed, congested travel times,
which of the two finds cheaper plans?

**Setup** (`scripts/app_options_comparison.py`). Both run through the same `solve()` the API uses, on the same
problems: the app's default 80-node, 8 km synthetic network (with more nodes when there are more stops), random stops and
demands (5-25), fleet sized for about 85% utilisation with capacity 100, 20 instances per size (seeds 700-719), paired.
The default is QPSO (40 particles x 800 iterations) with warm start and polish. The route search is read at time limits of
1, 3 and 10 s. Cost is travel time plus 1,000 x overload; no solution of any method, on any of the 80 instances, overloaded
a van.

Mean cost; in brackets the mean of the per-instance differences from the default (negative = the route search is cheaper).
The last column counts instances where the search at 1 s was cheaper / equal / dearer:

| stops (vans) | default (its run time) | route search, 1 s | 3 s | 10 s | wins/ties/losses at 1 s |
|---|---|---|---|---|---|
| 15 (3) | 113.4 (1.7 s) | 109.4 (-3.4%) | 109.4 (-3.4%) | 109.4 (-3.4%) | 13/7/0 |
| 30 (6) | 190.5 (1.0 s) | 178.3 (-6.4%) | 178.3 (-6.4%) | 178.2 (-6.4%) | 20/0/0 |
| 60 (11) | 335.0 (2.2 s) | 301.4 (-9.7%) | 299.4 (-10.3%) | 298.7 (-10.5%) | 20/0/0 |
| 100 (18) | 531.5 (4.6 s) | 493.8 (-7.2%) | 483.8 (-9.1%) | 479.2 (-10.0%) | 20/0/0 |

- From 30 stops up the route search is cheaper on **every** instance (20 of 20 at each size and each time limit); the
  smallest single improvement is 2.9% at 30 stops, 0.2% at 60 and 1.3% at 100 (at 1 s). At 15 stops it is never worse and
  cheaper on 13 of 20; on the other 7 both find the same plan.
- Most of the gain comes within one second, which is about what the default itself takes (1-5 s, measured with 8
  processes running). More time helps mainly at 60 and 100 stops (100 stops: 7.2% cheaper at 1 s, 10.0% at 10 s). At 15 and 30
  stops the answer is the same at 1, 3 and 10 s: the search has converged, and stops early (a 10 s limit ended after 6.7 s
  on average at 15 stops and 7.5 s at 30).
- This compares complete pipelines. It does not say the swarm is worse than the search at what a swarm does (Finding 13:
  the swarm adds nothing once the search is strong), nor anything about QPSO with warm start switched off, the mode
  meant for watching the algorithms compete from scratch.

**What this supports, and what it does not.**

- Supported: on synthetic road graphs of up to 100 stops with several vans, the route search option gives a cheaper plan
  than the default, by about 3% at 15 stops and 6-10% from 30 stops up.
- Not tested: real OpenStreetMap cities or live traffic (these instances are synthetic), a single vehicle (where the search
  is slow; Finding 13), more than 100 stops in the app, giving the default more iterations than 40 x 800. 20 instances per
  size and one algorithm seed per instance.
- Which solver is the default is a product decision, not a benchmark result. It is unchanged (QPSO, the subject of the
  project); making the route search the default is a one-line change in `frontend/src/lib/params.ts` (and
  `backend/app/schemas/solve.py` for callers that name no algorithm).

Reproduce (from `backend/`; the CSV is in `results/app_options/`):

```
python scripts/app_options_comparison.py --csv results/app_options/route_search_vs_default.csv
python scripts/app_options_comparison.py --from-csv results/app_options/route_search_vs_default.csv
```

## Finding 16 — the cost weights do what they say, and show what each measure costs in the others

**The question.** The problem statement asks to minimize travel time, distance **and** traffic congestion. The app now lets
the user choose the blend (`cost_weights`; math in MATH_FORMULATION.md, section 2). Does a different blend actually produce a
different plan, and what does optimizing one measure cost in the other two?

**What was built.** Each road segment costs `time x minutes driven + distance x km + congestion x minutes lost to
congestion`, where the last is how much longer the segment takes than in free flow (0 on a free road). Legs between stops are
cheapest paths under that cost, so every algorithm (QPSO, PSO, GA, route search, exact Held-Karp) minimizes the chosen blend
with no change to the algorithm. The default, time alone, reproduces every earlier result. Results always report the real
minutes, kilometres and congestion delay, whatever was optimized (`core/cost_model.py`).

**Correctness checks** (`tests/test_cost_model.py`, 20 tests). On a hand-built network with a short jammed road and a longer
free one, each weighting picks the road it should. On random 7-stop problems the exact solver, which finds the true optimum
of each blend, produces a distance-optimal plan that drives no more kilometres than the time-optimal plan, a time-optimal plan
no slower than the others, and a congestion-optimal plan with no more delay, asserted exactly (this is a theorem for an exact
solver, not a tendency). Leg costs keep the triangle inequality; the default weights give exactly the old leg times.

**Experiment** (`scripts/cost_weights_tradeoff.py`). Four settings, the same problems solved for each, every finished plan
measured in real minutes, kilometres and delay. The problems are those of Finding 15: the app's synthetic road network with
random congestion (each road independently 0.8x to 2.5x slower than free flow), random stops and demands, fleet for about
85% utilisation, 20 instances at each of 30 and 60 stops. Two solvers through the API's own `solve()`: the app default (QPSO,
warm start, polish) and the route search (3 s). Mean of each quantity over the instances; in brackets the mean of the
per-instance change from the "fastest" plan (negative = less).

App default (QPSO + polish):

| optimized for | 30 stops: minutes | km | delay | 60 stops: minutes | km | delay |
|---|---|---|---|---|---|---|
| Fastest (time only) | 203.2 | 99.2 | 57.9 | 331.4 | 164.4 | 91.6 |
| Shortest (distance only) | 230.2 (+13.5%) | 92.4 (-6.9%) | 93.0 (+62.8%) | 378.5 (+14.3%) | 153.3 (-6.7%) | 151.5 (+67.0%) |
| Avoid jams (time 50%, congestion 50%) | 205.0 (+1.2%) | 103.3 (+4.4%) | 54.0 (-6.1%) | 336.4 (+1.5%) | 172.7 (+5.2%) | 84.7 (-7.6%) |
| Balanced (time 40%, distance 30%, congestion 30%) | 202.5 (-0.2%) | 99.4 (+0.2%) | 56.9 (-1.1%) | 330.1 (-0.4%) | 164.2 (-0.2%) | 90.6 (-0.9%) |

Route search:

| optimized for | 30 stops: minutes | km | delay | 60 stops: minutes | km | delay |
|---|---|---|---|---|---|---|
| Fastest (time only) | 188.4 | 91.6 | 54.4 | 301.8 | 149.2 | 84.1 |
| Shortest (distance only) | 214.1 (+13.5%) | 86.3 (-5.9%) | 86.0 (+59.2%) | 346.0 (+14.7%) | 140.1 (-6.1%) | 138.4 (+66.1%) |
| Avoid jams (time 50%, congestion 50%) | 189.9 (+0.8%) | 96.0 (+4.9%) | 49.9 (-8.4%) | 304.5 (+0.9%) | 156.0 (+4.7%) | 77.2 (-8.4%) |
| Balanced (time 40%, distance 30%, congestion 30%) | 188.9 (+0.2%) | 92.5 (+0.9%) | 53.5 (-1.6%) | 302.8 (+0.3%) | 150.4 (+0.8%) | 83.4 (-0.9%) |

**What this shows.**

- **The weights work.** In 20 of 20 instances at 30 stops and 20 of 20 at 60, the route search's "shortest" plan
  drives the fewest kilometres of the four (default solver: 16 of 20 and 16 of 20), and its "avoid jams" plan has the least
  congestion delay in 20 of 20 and 20 of 20 (default solver: 15 of 20 and 19 of 20; in the others a different blend
  happened to do slightly better, which a heuristic allows).
- **Shortest is expensive on a congested network.** Minimizing kilometres alone saves about 6-7% of the distance but costs
  13-15% more minutes and raises the congestion delay by 59-67%: the shortest roads are the jammed ones.
- **Avoiding jams is cheap.** Half weight on congestion cuts the delay by 6-8% (route search 8%) for about 1% more minutes
  and 4-5% more kilometres.
- **"Balanced" is nearly the same plan as "fastest".** Time already includes the delay, so blending in a little distance and
  congestion moves each measure by less than 2%. The weights matter most at the extremes.

**What this supports, and what it does not.**

- Supported: the blend is a real control; each measure improves when it is weighted, at a cost in the others that the results
  panel shows in real units.
- The numbers depend on the network and on the units: a kilometre and a minute are different things, and the presets are
  arbitrary blends, so read them as an illustration of the trade-off, not as recommended settings. On a network at free flow
  congestion has nothing to avoid (the UI says so).
- Not tested: real OpenStreetMap cities or live traffic (congestion here is random per road), more than 60 stops, other
  blends. Both solvers are heuristics, so the exact-optimum guarantee above holds for the unit test, not for these runs; 20
  instances per size, one algorithm seed per instance. No plan in this experiment overloaded a van.

Reproduce (from `backend/`; the CSV is in `results/cost_weights/`):

```
python scripts/cost_weights_tradeoff.py --csv results/cost_weights/tradeoff.csv
python scripts/cost_weights_tradeoff.py --from-csv results/cost_weights/tradeoff.csv
```

## Finding 17 — soft time windows: QPSO, PSO and GA arrive on time, and a window-aware starting solution is what makes them good at it

**The question.** The problem statement lists time windows among the constraints. The formulation and the solvers now handle
soft windows (MATH_FORMULATION.md, sections 2.3-2.4; `core/time_windows.py`): a stop may be served between an earliest and a
latest minute after the vans leave the depot; a van that arrives early waits; one that arrives late still serves the stop and is
charged `time_window_penalty` (10 by default) per minute late, on top of the driving cost and the capacity penalty. Does pricing
lateness change the plans, and do the algorithms cope?

**What supports windows.** QPSO, PSO, GA and nearest neighbour, through the same cost function. The optimal Split decoder, the exact
Held-Karp solver and the route search assume that a route's cost does not depend on when it starts, which windows break, so the
first steps aside (greedy cut), the second is skipped and the third is refused with a clear message. The polish (2-opt and moving
stops between vans) does not know about windows, so with windows it is kept only if the polished plan has a lower objective.

**Correctness checks** (`tests/test_time_windows.py`, 24 tests, plus 8 API tests). The schedule arithmetic is checked by hand
(waiting, lateness, service time). The fast cost used inside the searches equals the reporting path on random plans, including
with blended cost weights. On a 6-stop problem QPSO finds the brute-force optimum of the windowed objective, and the plan that
ignores the windows is worse under them.

**Experiment** (`scripts/time_windows_experiment.py`). The problems of Findings 15-16 (the app's synthetic road network with random
congestion, random stops and demands, fleet for about 85% utilisation), 20 instances at each of 15 and 30 stops, with the app's demo
windows (30-60 minutes wide, opening up to 80 minutes after the quickest a van could get there) and 5 minutes of service at each
stop. Every algorithm solves each problem twice through the API's own `solve()`: once **pricing lateness** and once **ignoring the
windows** (penalty 0), and each finished plan is measured against the windows.

The app's default (QPSO, warm start, polish), mean over the 20 instances:

| stops | plan | minutes late | stops late | driving (min) | waiting (min) |
|---|---|---|---|---|---|
| 15 | ignores the windows | 157.6 | 4.9 | 107.4 | 86.3 |
| 15 | prices lateness | 0.0 | 0.0 | 135.7 | 49.6 |
| 30 | ignores the windows | 290.2 | 11.2 | 179.7 | 187.9 |
| 30 | prices lateness | 0.0 | 0.2 | 244.2 | 88.8 |

Ignoring the windows leaves about 5 of 15 stops and 11 of 30 late, by hundreds of minutes in
total. Pricing lateness removes it, at the price of 26% more driving at 15 stops and 36% more at 30 (and a
lot less waiting: the plan stops arriving early at stops whose window has not opened). Every one of the 20 instances at each size is
better on the objective with lateness priced, for every algorithm except nearest neighbour, which cannot plan around windows
(it is better on 17 of 20 and 14 of 20, level on the rest).

**What made the algorithms good at windows.** The first run started QPSO, PSO and the GA from the usual warm-start seeds, nearest
neighbour and nearest neighbour after 2-opt, which know nothing about windows. At 30 stops QPSO's plans then had an objective
43% higher than the genetic algorithm's (GA better on 19 of 20). Adding one window-aware seed, a nearest
neighbour that goes next to the stop whose service could start soonest (`warm_start.window_aware_order`), to the starting
solutions of all three changed that. Objective = driving minutes + 10 x minutes late, mean; each cell is minutes late / driving
minutes / objective, with lateness priced:

| algorithm | 15 stops: late min / driving / objective, plain seeds | with window-aware seed | 30 stops: plain seeds | with window-aware seed |
|---|---|---|---|---|
| QPSO (app default) | 0.0 / 136.0 / **136.0** | 0.0 / 135.7 / **135.7** | 3.5 / 296.2 / **331.1** | 0.0 / 244.2 / **244.5** |
| classical PSO | 0.8 / 154.7 / **162.3** | 0.0 / 139.5 / **139.8** | 10.3 / 311.1 / **413.9** | 0.3 / 247.1 / **250.3** |
| genetic algorithm | 0.2 / 136.5 / **138.1** | 0.0 / 138.3 / **138.3** | 0.1 / 231.0 / **232.1** | 0.1 / 243.6 / **244.3** |
| nearest neighbour | 81.4 / 132.6 / **946.2** | 81.4 / 132.6 / **946.2** | 241.4 / 215.7 / **2629.8** | 241.4 / 215.7 / **2629.8** |

With the seed, at 30 stops QPSO is level with the genetic algorithm (QPSO lower on 12 of 20, higher on 8; the GA's
objective is 0.9% lower, not significant) and with classical PSO (10 wins, 2 ties, 8 losses). At 15 stops all three tie
(QPSO against the GA 8/3/9, against PSO 10/5/5). The credit therefore belongs to the seed, domain
knowledge about windows given to every algorithm, not to the quantum update. The seed slightly hurt the GA at 30 stops (232 to
244) while helping the swarms, so it is a good starting point rather than a free lunch.

**What this supports, and what it does not.**

- Supported: windows are modelled, priced and reported (per-stop arrival, waiting and lateness in the API and the UI); QPSO, PSO and
  GA plan around them and arrive on time; with a sensible starting solution QPSO is level with the other two.
- Not supported: that QPSO is better than the GA or PSO under windows. It is not, on this evidence.
- The demo windows are random and unrelated to geography, which makes them expensive to meet (26-36% more driving). Real windows
  often follow the map (a district opens at nine), which would cost less. 10 per minute is a choice of the trade-off, not a
  measured optimum; the penalty was not varied here.
- Not tested: more than 30 stops, real OpenStreetMap cities, hard windows, a different service time per stop, and a route search
  that understands windows. The plans "ignoring the windows" still start from the same seeds as the aware ones, which the search
  discards because they cost more driving. 20 instances per size, one algorithm seed per instance.

Reproduce (from `backend/`; the CSVs are in `results/time_windows/`):

```
python scripts/time_windows_experiment.py --csv results/time_windows/aware_vs_ignoring.csv
python scripts/time_windows_experiment.py --plain-seeds --csv results/time_windows/aware_vs_ignoring_plain_seeds.csv
python scripts/time_windows_experiment.py --from-csv results/time_windows/aware_vs_ignoring.csv
```

## Finding 18 — shortest path: Dijkstra is exact and fast, the swarm searches are near-optimal but slower, and QPSO is not better than PSO or the GA

**The question.** The problem statement's first objective is the quickest route between two places, with QPSO as the quantum-inspired
method. The app now has that mode (MATH_FORMULATION.md, section 8; `core/shortest_path.py`, `POST /api/shortest-path`, "Shortest path"
in the UI). Dijkstra's algorithm solves it exactly, so it is the reference; the question is how close QPSO, classical PSO and a genetic
algorithm get when they search for the same path, at what cost, and whether QPSO has an edge.

**How the searches work.** A particle holds one priority per intersection in a corridor around the straight line from A to B (factor
1.6, grown until A and B are connected). A path is decoded by walking from A to the unvisited neighbour with the highest priority,
backing up out of dead ends, so every particle decodes to a valid path that reaches B. The fitness is the path's cost under the chosen
weights (default: minutes). QPSO, PSO and the GA use the same encoding, decoder and cost, 30 particles x 200 iterations, and the same
starting particle: one whose priorities point towards B (a warm start, the counterpart of the vehicle-routing seeds). Dijkstra is
always run on the whole map, so a search's gap is measured against the true optimum.

**Correctness checks** (`tests/test_shortest_path.py`, 16 tests, plus 6 API tests). The decoder always reaches the target, including
through dead ends; Dijkstra agrees with networkx on random graphs and with blended weights; no search ever returns a path cheaper than
Dijkstra's (also asserted for every one of the 1,250 search runs below); convergence curves never rise; QPSO finds the exact path on all six
test pairs of a 40-node map.

**Experiment** (`scripts/shortest_path_experiment.py`). The app's synthetic road network with random congestion at 40, 80, 160 and 300
intersections (one map per size), 50 random pairs per size at least four road segments apart by fewest segments (the quickest routes
have 6.6 to 12.2 segments on average), cost = minutes, same pairs and seed for every method. "Optimal" means the search returned a path
whose cost equals Dijkstra's. Corridor sizes: 26, 45, 74 and 102 nodes on average. Cells are pairs solved optimally / mean gap above
the optimum; lower gap is better, and Dijkstra is 50 / 50 and 0% everywhere.

| intersections | QPSO (app default) | classical PSO | genetic algorithm | QPSO without the starting particle | QPSO, 60 x 500 |
|---|---|---|---|---|---|
| 40 | 45 / 50, 0.41% | 44 / 50, 0.30% | 39 / 50, 0.80% | 45 / 50, 0.31% | 48 / 50, 0.03% |
| 80 | 41 / 50, 0.72% | 38 / 50, 1.57% | 38 / 50, 0.96% | 32 / 50, 3.05% | 44 / 50, 0.50% |
| 160 | 27 / 50, 3.31% | 22 / 50, 4.64% | 23 / 50, 3.05% | 28 / 50, 7.72% | 27 / 50, 2.98% |
| 300 | 22 / 50, 4.01% | 21 / 50, 3.09% | 22 / 50, 2.58% | 22 / 50, 12.23% | 29 / 50, 2.56% |

Mean running time per pair, in milliseconds (Dijkstra 0.2, 0.3, 0.3, 0.5 at the four sizes):

| intersections | QPSO | classical PSO | genetic algorithm | QPSO 60 x 500 |
|---|---|---|---|---|
| 40 | 117 | 104 | 360 | 541 |
| 80 | 161 | 142 | 392 | 724 |
| 160 | 263 | 286 | 509 | 1,144 |
| 300 | 288 | 357 | 547 | 1,376 |

Worst single pair, default QPSO: 9.9%, 12.7%, 41.0% and 32.5% above the optimum at the four sizes. With blended cost weights (time 0.4,
distance 0.3, congestion 0.3) on the 80-node map the picture is the same as with minutes alone: optimal on 38 / 50 (QPSO, mean gap 1.26%),
35 / 50 (PSO, 1.95%), 36 / 50 (GA, 1.21%), 33 / 50 without the starting particle (2.82%) and 41 / 50 for 60 x 500 (0.70%).

**Reading it.**

- **Dijkstra is the better method here, by a wide margin.** It is exact on every pair and several hundred times faster (0.2 to 0.5 ms
  against 100 to 550 ms for the swarm searches at the default budget). The searches find the exact route on 78-90% of pairs at 40
  intersections, falling to 42-44% at 300, with the average gap growing from under 1% to 2.6-4%; they are never better than Dijkstra. That is expected for a
  problem with a known polynomial-time solution, and the app says so in its interface. The value of this mode is that QPSO, PSO and the
  GA run on a second kind of problem, with the same cost model and traffic, and are checked against an exact answer.
- **The optimum was almost always available to the searches.** The exact path lies fully inside the corridor on 248 of the 250 pairs
  (two at 160 intersections are not), so the gaps are search failures, not the corridor.
- **QPSO is not better than PSO or the GA.** Paired exact sign tests on the 50 pairs at each size: QPSO beats the GA at 40 intersections
  (better on 8 pairs, worse on none, p = 0.004), and that is the only significant result between the three. Against PSO it is never
  significant (best case 8 better / 4 worse at 80, p = 0.19), and at 300 intersections QPSO has the worse mean gap (4.01% against 3.09%
  and 2.58%) although the medians are level (1.11%, 1.08%, 1.07%) and the paired tests are not significant (p about 0.17 for QPSO
  worse than either). Do not claim an edge for QPSO on this problem.
- **The starting particle matters.** Without it QPSO is worse at 80 intersections (better with it on 14 pairs, worse on 3, p = 0.006)
  and at 300 (23 against 6, p = 0.001), with mean gaps of 3.05% and 12.23% against 0.72% and 4.01%; at 160 the direction is the
  same but not significant (17 against 9, p = 0.08), and at 40 it makes no difference (1 against 1). Domain knowledge in the starting
  solution is what keeps the swarm competitive as the map grows, the same lesson as the seeds in Finding 17.
- **More budget helps but does not make it exact.** Doubling the particles and 2.5 times the iterations (60 x 500) raises optimal pairs
  from 22 to 29 of 50 at 300 intersections (better on 20 of 28 pairs that differ, p = 0.018), at 4 to 5 times the running time; at 40,
  80 and 160 intersections the difference is not significant.

**What this supports, and what it does not.**

- Supported: the app finds the quickest route exactly (Dijkstra) and offers QPSO, PSO and a GA over the same problem, with real
  minutes, kilometres and congestion delay reported, and a convergence curve against the exact optimum.
- Not supported: that QPSO beats Dijkstra, PSO or the GA at shortest paths. It does not. It also does not become exact with more budget;
  its gap grows with map size.
- Caveats: one synthetic map per size (graph seed 5) with random congestion, not real OpenStreetMap streets; 50 pairs per size, one
  seed per pair; the corridor restriction (factor 1.6) is part of the method; the searches assume a static map for the length of one
  search; running times are wall-clock on one machine with 8 worker processes, so read them as orders of magnitude.

Reproduce (from `backend/`; the CSV is in `results/shortest_path/`):

```
python scripts/shortest_path_experiment.py --csv results/shortest_path/paths.csv
python scripts/shortest_path_experiment.py --from-csv results/shortest_path/paths.csv
```

## Finding 19 — closing a road: the plans go around it, the cost of a closure is about 1%, and the default solver is too noisy to show it reliably

**The question.** The app can close a road ("block road" on the map; MATH_FORMULATION.md, end of 2.1; `services/closures.py`,
`PUT /api/graph/{id}/closures`) and plans again, showing what the closure cost. Closing a road removes both of its arcs from the
network, so every solver sees it without changes. Two things need checking: that plans really avoid closed roads, and whether the
"cost of a closure" the app reports can be trusted, given that the solvers are randomized heuristics and closing a road can never
make the best possible plan faster.

**Correctness checks** (`tests/test_closures.py`, 14 tests). A closed road leaves the map view and reopening restores the same roads
with the same congestion; a road can be named in either direction and only listed roads stay closed; unknown roads are refused;
traffic changes leave closures in place; a plan and a shortest path drive around a closed road (checked on the polylines) and the
quickest route is the same again after reopening; closing every road at an intersection marks it cut off, a stop there gives a 422
naming it, and random stops are never drawn from cut-off places. The same file tests the single-stop capacity warning (a stop whose
demand is above one vehicle's capacity is named, exactly the capacity is fine, many are summarized).

**Experiment** (`scripts/road_closure_experiment.py`). The app's 80-node synthetic network with random congestion, 20 instances at each
of 15 and 30 stops (demands 5-25, fleet for 85% utilisation). For each: plan with the app default (QPSO, warm start, polish) and with
the route search (3 s); close one random road the plan drives on, leaving every stop reachable; plan again with the same settings,
seed, stops and demands; and plan the *open* network once more with a different algorithm seed, which measures the run-to-run noise
by itself. Change = closed plan's cost against the open plan's, in percent (cost = minutes + 1000 x overload).

| stops | solver | mean change | median | apparent savings | largest apparent saving | run-to-run noise, mean (max) |
|---|---|---|---|---|---|---|
| 15 | default | +2.64% | +1.21% | 1 of 20 | -1.4% | 2.95% (10.9%) |
| 15 | route search | +0.92% | +0.57% | 0 of 20 | none | 0.00% (0.0%) |
| 30 | default | +1.10% | +0.39% | 5 of 20 | -8.1% | 1.51% (4.9%) |
| 30 | route search | +1.03% | +0.37% | 1 of 20 | -0.3% | 0.25% (2.9%) |

An "apparent saving" is a closed plan cheaper than the open plan by more than 0.05%, which cannot be real. On the open networks the
route search was cheaper than the default on 12 of 20 instances at 15 stops (equal on 8; 2.6% on average) and on all 20 at 30 stops
(6.6%), the same direction as Finding 15.

**Reading it.**

- **Closing a random road the plan uses costs about 1% of the plan** (route search: +0.9% and +1.0% on average, medians about +0.4%
  to +0.6%, worst single cases +3.5% and +9.2%). It is small because each intersection has about four roads, so a detour is
  usually cheap; a closure in a thinner part of a real city, or several at once, costs more.
- **The default solver's noise is as large as that effect.** Planning the same open network with a different seed changes the default's
  cost by 1.5% to 3% on average, up to 11%, so its what-if numbers carry an error of that size: 6 of its 40 comparisons show a
  closure that "saves" time, one by 8.1%. The route search is far steadier (0.00% and 0.25% mean noise; at 15 stops it gave the
  identical cost on all 20 reruns, which says it reaches the same local optimum, not that the optimum is found), so its
  numbers are the ones to trust.
- **What the app does about it.** It compares against the plan with all roads open, and when a closure appears to save time it says
  so in the banner: a closure cannot really save time, the earlier plan was not optimal. The default stays QPSO (a product decision,
  unchanged); for a what-if the route search, chosen in the Algorithm menu, is the steadier instrument.

**What this supports, and what it does not.**

- Supported: closures are applied to the network itself, so every method avoids them; the response names cut-off stops; the banner's
  figure is the real difference between two plans, each one as good as the solver found.
- Not supported: reading the default solver's banner as an exact cost of the closure at a precision better than about 3%.
- Not tested: real OpenStreetMap streets (where one-way streets and bridges make some closures far costlier), several simultaneous
  closures, a closure that is not on the current plan (it changes nothing by construction), a route search that re-uses the old plan
  as its starting point. One random road per instance, 20 instances per size, one algorithm seed per run.

Reproduce (from `backend/`; the CSV is in `results/road_closures/`):

```
python scripts/road_closure_experiment.py --csv results/road_closures/closures.csv
python scripts/road_closure_experiment.py --from-csv results/road_closures/closures.csv
```

## Finding 20 — against the exact optimum on small problems, the default QPSO pipeline is 1.5-3.6% above it, and the route search is exactly optimal every time

**The question.** The problem statement asks for near-optimal routes. Findings 14-15 measured against the proven optima of 100-199-customer benchmark
instances and against OR-Tools, but the gap to the *true* optimum on small problems was last measured in Finding 1, with a 2-opt polish that had a bug
(Finding 8), so its 2.4% is superseded and must not be quoted. This re-measures it with the current code, on the app's own problem.

**The exact reference.** `core/baselines/exact_cvrp.py` computes the exact optimum of the objective every solver minimizes: driving cost (with the
request's cost weights) plus 1,000 per unit of overload, over at most `n_vehicles` routes. It runs Held-Karp over subsets, prices each subset as one
route (overload penalty included), then finds the best split into at most `n_vehicles` subsets. It takes 1.2 s at 14 stops with several vans and 4.5 s
at 16 stops with one. It is checked in `tests/test_exact_cvrp.py` (16 tests): it equals exhaustive search over every assignment of stops to vans and
every visiting order at 6 stops (five fleet and capacity settings, two of them with unavoidable overload) and at 8 stops, equals Held-Karp for one
van, respects blended cost weights, and its routes reproduce its own cost. In the 150 instances below no solver ever came out cheaper than it
(asserted in the script), which would have exposed an over-priced optimum.

**Experiment** (`scripts/exact_gap_experiment.py`). 30 random instances per size on the app's synthetic network (80 intersections, 8 km, random
congestion); every method sees the same instances, one algorithm seed per instance. **A** is the app's problem: 10, 12 and 14 stops, demands 5-25,
capacity 100, a fleet for 85% utilisation (2.2, 2.8 and 2.9 vans on average). **B** is one van and a plain tour, 12 and 16 stops. Swarms run 40 x 800
with warm start and polish as in the app, unless marked "no warm start"; the route search has 3 s, which these sizes do not need (it took 0.9-2.7 s on
average). Gap = 100 x (cost - optimum) / optimum; "before polish" is what the algorithm found alone, "finished" is what the app returns.

**A. The app's problem (several vans, capacities)**

| stops | method | optimum found | mean gap before polish | mean gap finished | median | worst |
|---|---|---|---|---|---|---|
| 10 | QPSO (app default) | 22 / 30 | 6.14% | 1.48% | 0.00% | 17.6% |
| 10 | classical PSO | 17 / 30 | 8.42% | 2.71% | 0.00% | 43.5% |
| 10 | genetic algorithm | 19 / 30 | 5.57% | 1.37% | 0.00% | 17.6% |
| 10 | QPSO, no warm start | 19 / 30 | 4.43% | 2.63% | 0.00% | 16.3% |
| 10 | nearest neighbour | 13 / 30 | 31.31% | 3.71% | 1.14% | 17.6% |
| 10 | route search (3 s) | 30 / 30 | - | 0.00% | 0.00% | 0.0% |
| 12 | QPSO (app default) | 12 / 30 | 4.83% | 2.44% | 0.61% | 12.3% |
| 12 | classical PSO | 11 / 30 | 6.23% | 2.73% | 0.89% | 12.3% |
| 12 | genetic algorithm | 7 / 30 | 6.18% | 3.69% | 1.17% | 14.6% |
| 12 | QPSO, no warm start | 16 / 30 | 3.44% | 1.86% | 0.00% | 9.0% |
| 12 | nearest neighbour | 4 / 30 | 22.58% | 4.70% | 3.09% | 17.4% |
| 12 | route search (3 s) | 30 / 30 | - | 0.00% | 0.00% | 0.0% |
| 14 | QPSO (app default) | 7 / 30 | 9.27% | 3.62% | 1.41% | 12.7% |
| 14 | classical PSO | 6 / 30 | 11.30% | 4.02% | 1.65% | 14.1% |
| 14 | genetic algorithm | 6 / 30 | 9.16% | 4.66% | 2.86% | 15.1% |
| 14 | QPSO, no warm start | 10 / 30 | 5.33% | 1.83% | 1.08% | 10.0% |
| 14 | nearest neighbour | 5 / 30 | 33.59% | 5.55% | 3.68% | 22.0% |
| 14 | route search (3 s) | 30 / 30 | - | 0.00% | 0.00% | 0.0% |

**B. One van, a plain tour**

| stops | method | optimum found | mean gap before polish | mean gap finished | median | worst |
|---|---|---|---|---|---|---|
| 12 | QPSO, no warm start | 17 / 30 | 4.70% | 1.86% | 0.00% | 10.7% |
| 12 | classical PSO | 9 / 30 | 11.52% | 2.88% | 2.18% | 8.6% |
| 12 | genetic algorithm | 17 / 30 | 8.18% | 1.75% | 0.00% | 10.8% |
| 12 | QPSO, warm start | 20 / 30 | 1.34% | 1.02% | 0.00% | 5.8% |
| 12 | route search (3 s) | 30 / 30 | - | 0.00% | 0.00% | 0.0% |
| 16 | QPSO, no warm start | 9 / 30 | 8.84% | 5.69% | 2.98% | 24.6% |
| 16 | classical PSO | 7 / 30 | 27.07% | 4.22% | 2.89% | 17.9% |
| 16 | genetic algorithm | 5 / 30 | 12.44% | 6.49% | 3.17% | 31.1% |
| 16 | QPSO, warm start | 11 / 30 | 2.33% | 2.20% | 0.46% | 15.2% |
| 16 | route search (3 s) | 30 / 30 | - | 0.00% | 0.00% | 0.0% |

**Reading it.**

- **The default pipeline (QPSO, warm start, polish) is typically within a couple of per cent, not always.** Its mean gap is 1.5%, 2.4% and 3.6%
  at 10, 12 and 14 stops; the median is 0.0%, 0.6% and 1.4%; it finds the exact optimum on 22, 12 and 7 of 30 instances, and its worst instance is 17.6%,
  12.3% and 12.7% above. The gap grows with size while the number of exact hits falls.
- **The polish does most of the work.** QPSO alone is 6.1%, 4.8% and 9.3% above the optimum; the polish brings that to 1.5%, 2.4% and 3.6%. Nearest
  neighbour plus the same polish ends 3.7%, 4.7% and 5.6% above, so the swarm adds about two points over it: better on 15 of 17 decisive instances
  at 10 stops (p = 0.001) and 18 of 20 at 12 (p < 0.001), but only 15 of 22 at 14 (p = 0.067).
- **The route search finds the exact optimum on all 150 instances**, in at most 3 s: several vans up to 14 stops, one van up to 16. The default QPSO is
  worse than it on 8, 18 and 23 of the 30 instances of A (better on none; p = 0.004, < 0.001, < 0.001), and QPSO without the warm start is worse
  on 13 and 21 of B's (better on none). On problems this
  small the route search is effectively an exact solver. This is a result about at most 14-16 stops; it says nothing on its own about larger
  problems, where Findings 13-15 measure it against OR-Tools and the CVRPLIB optima (1.5-2.9% above proven optimal).
- **QPSO's edge over classical PSO on raw output reproduces, and does not survive the polish.** Before the polish QPSO beats PSO on 19 of 21 decisive
  instances at 10 stops (p < 0.001) and 15 of 19 at 12 (p = 0.010), but 13 of 19 at 14 is not significant (p = 0.084). On one van (B, no warm start)
  it is 23 of 26 and 28 of 30 (both p < 0.001). After the polish, one comparison in ten is significant (B, 12 stops, against PSO, p = 0.032), about what chance
  gives. Against the genetic algorithm nothing is significant on A before or after the polish (smallest p = 0.059); on B it wins before the polish at
  12 stops (19 of 27, p = 0.026) and not at 16 (p = 0.10). The pattern is that of Findings 7 and 10.
- **The warm start is not a clear help on small multi-van problems.** Without it QPSO's mean gap after the polish was lower at 12 and 14 stops
  (1.9% against 2.4%; 1.8% against 3.6%) and higher at 10 (2.6% against 1.5%); none of the three paired differences is significant (p = 0.21 for warm
  better at 10, 0.25 and 0.34 for warm worse at 12 and 14). For a single tour it does help at 16 stops (18 better, 5 worse, p = 0.005; 2.2% against
  5.7%) and not significantly at 12. The warm start matters at scale (Finding 10); the app keeps it on, since here it is neither clearly better nor worse.

**What this supports, and what it does not.**

- Supported: where the optimum can be computed, the app's default pipeline is typically 1.5-3.6% above it, and the route search option matches it on
  every instance; the raw advantage of QPSO over classical PSO reproduces.
- Not supported: that the default is near-optimal on every instance (12-18% in the worst cases, and worse as size grows), that QPSO beats the genetic
  algorithm or PSO after the polish, or anything about sizes above 14 stops (several vans) and 16 (one van), where there is no exact reference here.
- Caveats: synthetic maps with random congestion, not real streets; 30 instances per size and one algorithm seed each; the objective includes the soft
  capacity penalty, and the fleet is sized for 85% utilisation, so a van may stay empty; Finding 1's 2.4% and its "avg optimality
  gap" table are superseded by the numbers above.

Reproduce (from `backend/`; the CSV is in `results/exact_gap/`):

```
python scripts/exact_gap_experiment.py --csv results/exact_gap/gaps.csv
python scripts/exact_gap_experiment.py --from-csv results/exact_gap/gaps.csv
python -m pytest tests/test_exact_cvrp.py
```

## Finding 1 — hyperparameter tuning (small instances, exact ground truth)

Swept `beta_start`, `beta_end`, particle count, and iteration count for QPSO
against classical PSO, on 8/10/12-stop instances (5 seeds each), validated on
a disjoint set of seeds (`scripts/tune_qpso.py`):

| | avg optimality gap (validation set) |
|---|---|
| QPSO (tuned: beta=(1.0, 0.2), 40 particles, 200 iters) | 2.40% |
| Classical PSO (40 particles, 200 iters) | 2.88% |

A real but modest edge — and on these small instances, 2-opt polish ties out
most of the difference before it even shows up (see Finding 2).

**Superseded by Finding 20.** These gaps were measured with the 2-opt polish that had the bug of Finding 8; Finding 20 re-measures the gap to the exact
optimum with the current code, on the app's own problem, and should be quoted instead.

## Finding 2 — the win only shows up at a longer iteration budget

At small iteration counts (≤400), QPSO vs. classical PSO was close to a coin
flip, and at some sizes classical PSO was ahead. Sweeping the iteration
budget on 20/30/50-stop instances (no exact ground truth needed here — we
compared QPSO's cost directly against classical PSO's cost):

| stops | iterations | QPSO wins | ties | PSO wins | avg (QPSO−PSO)/PSO |
|---|---|---|---|---|---|
| 30 | 200 | 7 | 1 | 7 | +1.85% (PSO ahead) |
| 30 | 400 | 7 | 1 | 7 | −2.71% |
| 30 | 800 | 12 | 1 | 2 | −1.88% |

Confirmed with a larger sample (30 instances per size, `n_particles=40`,
`beta=(1.0, 0.2)`, 800 iterations):

| stops | QPSO wins | ties | PSO wins | avg (QPSO−PSO)/PSO |
|---|---|---|---|---|
| 20 | 11 | 13 | 6 | −1.03% |
| 30 | 20 | 2 | 8 | −1.29% |
| 50 | 19 | 2 | 9 | −2.42% |

**Interpretation:** QPSO's broader per-step exploration (the quantum
delta-potential-well jump can be large relative to classical PSO's velocity
step) doesn't pay off on a short budget — it's still exploring while PSO has
already converged. Given enough iterations to exploit what it's found, QPSO
consistently comes out ahead on average, though not on every single instance
(PSO still wins outright on roughly a quarter to a third of runs — this is a
statistical edge, not a guarantee per-instance).

## Finding 3 — periodic memetic pbest refinement: tried, and it backfired

Hypothesis: since QPSO (unlike classical PSO) computes `mbest` from the mean
of all particles' personal bests, periodically 2-opt-polishing every
particle's `pbest` mid-search (not just the final answer) should improve
*two* channels for QPSO — the attractor **and** `mbest` — but only one for
PSO. Implemented as `memetic_interval` on both `QPSO` and `ClassicalPSO`
(`app/core/local_search.refine_positions_with_two_opt`), applied fairly to
both algorithms, and ablation-tested (`scripts/ablation_memetic.py`) with
the same 30-instances-per-size sample as Finding 2:

| stops | memetic OFF: win rate / avg gap | memetic ON (every 25 iters): win rate / avg gap |
|---|---|---|
| 20 | 36.7% / −1.03% | 16.7% / −0.24% |
| 30 | 66.7% / −1.29% | 26.7% / −0.23% |
| 50 | 63.3% / −2.42% | 23.3% / **+0.10%** (PSO ahead on average) |

**The hypothesis was wrong.** Win rate dropped sharply at every size instead
of improving, and ties exploded (e.g. 2→16 at 30 stops). Applying 2-opt to
the *entire population* every 25 iterations is strong and frequent enough to
pull both algorithms' personal bests into the same handful of 2-opt basins —
so the two metaheuristics' own distinct search dynamics stopped being what
determined the outcome; 2-opt did most of the work for both, homogenizing
the result instead of giving QPSO's dual-channel mechanism room to compound.
The "double leverage" reasoning wasn't unsound on its own terms, but the
frequency/scope (every 25 iters, all particles) let the local search
dominate rather than assist the metaheuristic search.

**Decision:** reverted to `memetic_interval=None` (off) by default on both
classes — code and tests are kept (`refine_positions_with_two_opt`,
`test_memetic_refinement.py`) as an opt-in knob, since it isn't broken, it
just doesn't help the win-rate goal as implemented. A gentler variant
(polish only `gbest`, not the whole population; a longer interval) is a
plausible next experiment if we return to this — not yet tried.

**Update after Finding 8.** The memetic mechanism wrote each 2-opt-polished
route back over the particle's personal best, and the old 2-opt could make
that route worse, so the ablation was re-run with the corrected 2-opt (same
30 instances per size, same polished metric; here avg gap = (QPSO-PSO)/PSO,
negative = QPSO better):

| stops | memetic OFF: win/tie/loss, avg gap | memetic ON (every 25 iters): win/tie/loss, avg gap |
|---|---|---|
| 20 | 18/0/12, -2.95% | 7/18/5, -0.26% |
| 30 | 18/0/12, -1.86% | 13/5/12, -0.42% |
| 50 | 14/0/16, +0.75% | 13/0/17, +0.35% |

The verdict stands, so it was not a bug artifact: memetic refinement still
doesn't help, and ties climb to 18 of 30 at 20 stops as both algorithms fall
into the same 2-opt basins.

## Finding 4 — weighted mbest: also didn't help, and points at *why*

Hypothesis: rank-weight `mbest` (QPSO's swarm-wide attractor, which PSO has
no equivalent of) so better particles pull it harder — a change nothing
about PSO could copy, so any gain would be unambiguously QPSO-specific.
Implemented as `weighted_mbest=True` on `QPSO` only (`app/core/qpso.py`),
ablation-tested (`scripts/ablation_weighted_mbest.py`) on the same 30
instances/size sample:

| stops | plain mbest: win rate / avg gap | weighted mbest: win rate / avg gap |
|---|---|---|
| 20 | 36.7% / −1.03% | 36.7% / −0.62% (unchanged win rate, weaker margin) |
| 30 | 66.7% / −1.29% | **43.3%** / **+0.55%** (PSO ahead on average) |
| 50 | 63.3% / −2.42% | 56.7% / −2.62% (roughly flat) |

No size improved; 30 stops got clearly worse. **Likely mechanism:** Finding
2 concluded QPSO's edge comes from *broader exploration sustained over a
long horizon* (800 iterations) — it needs time to keep searching before it
pays off. Weighting `mbest` toward the already-best particles pulls the
whole swarm toward exploitation *earlier*, which cuts against the exact
thing that was working. In hindsight this and Finding 3 (memetic
refinement) share a root cause: both push the swarm toward convergence/
exploitation faster, and QPSO's advantage over PSO specifically lives in
the exploration phase, not the exploitation phase. `weighted_mbest` is left
in as a tested, off-by-default opt-in knob, same as `memetic_interval`.

**Implication for what to try next:** techniques that *extend or protect*
exploration (opposition-based initialization for a better starting spread,
stagnation-triggered diversity injection to stop premature convergence)
are now the better-motivated direction than anything that adds more
exploitation pressure, given both exploitation-leaning ideas tried so far
have hurt rather than helped.

## Finding 5 — stagnation-triggered diversity injection: also negative

Hypothesis: since Findings 3-4 both showed that *accelerating* convergence
hurts QPSO, actively *fighting* premature convergence should help — when
gbest hasn't improved for `stagnation_limit` iterations, reinitialize the
worst `reinjection_fraction` of particles (position and personal best) to
fresh random points. Implemented as `stagnation_limit`/`reinjection_fraction`
on `QPSO` (`app/core/qpso.py`), ablation-tested at two settings
(`scripts/ablation_stagnation.py`) on the same 30-instance/size sample:

| stops | off | limit=60, frac=0.25 | limit=100, frac=0.15 |
|---|---|---|---|
| 20 | 36.7% / −1.10% | 26.7% / −0.87% | 33.3% / −0.93% |
| 30 | 66.7% / −1.26% | 43.3% / **+1.80%** | 60.0% / −1.12% |
| 50 | 60.0% / −2.22% | 60.0% / −2.76% | 60.0% / −2.80% |

Mixed-to-negative: clearly worse at 20 and 30 stops (especially the more
aggressive `limit=60` setting — 30 stops flips to PSO ahead on average),
roughly a wash at 50 stops. **Likely mechanism:** the trigger only watches
whether the single best value improved, not the swarm's actual diversity —
early in a run, long stretches without a new gbest are normal even while
the population is still healthily spread out, so the injection often fires
when nothing was actually wrong, and disrupts `mbest` (which averages in
the freshly-randomized particles) for no benefit. A diversity-*measured*
trigger (e.g. position variance, as the "length of potential well guided by
diversity" literature does) rather than a best-fitness-plateau proxy would
be the more principled version of this idea, not yet tried. Left in as a
tested, off-by-default opt-in knob.

## Finding 6 — fitness-adaptive per-particle beta: also negative

Hypothesis: give each particle its own beta based on its current fitness
rank (worse particle -> higher beta/more exploration, better particle ->
lower beta/more exploitation), instead of one shared beta for the whole
swarm -- centered so the swarm-average beta still matches the validated
schedule. Unlike `weighted_mbest`, this doesn't push the whole swarm toward
exploitation together. Implemented as `adaptive_beta` on `QPSO`
(`app/core/qpso.py`), ablation-tested (`scripts/ablation_adaptive_beta.py`)
on the same 30-instance/size sample:

| stops | uniform beta | adaptive beta |
|---|---|---|
| 20 | 36.7% / −1.10% | 33.3% / −0.67% |
| 30 | 66.7% / −1.26% | **33.3%** / **+0.98%** (PSO ahead on average) |
| 50 | 60.0% / −2.22% | 46.7% / −1.87% |

Worse at every size, badly at 30 stops. **Likely mechanism, and this
completes a pattern across all four attempts:** `weighted_mbest` and
`adaptive_beta` both *condition the algorithm's behavior on each particle's
current rank* -- but with random-key permutation decoding, a permutation's
fitness rank at any single iteration is a noisy, unstable signal (small
position changes can reorder the decoded route completely). Treating that
snapshot as trustworthy enough to steer search (extra exploitation for
"good" particles, extra exploration for "bad" ones) bets on a signal that
isn't stable enough to bet on. `memetic_interval` and `stagnation_limit`
fail for a related reason: they condition an intervention on a noisy
per-iteration event (a plateau, a fixed interval) rather than trusting the
fixed, validated global schedule. Left in as a tested, off-by-default
opt-in knob, same as the other three.

## The pattern across Findings 3-6

*Caveat added after Finding 8: these four ablations measured the polished
metric, whose 2-opt had a bug. Finding 3 was re-run with the fix and its
verdict stands. Findings 4-6 were NOT re-run, so their verdicts, and the
pattern below, are unverified on the corrected polished metric and on the
raw metric.*

Four different, individually well-motivated techniques (memetic pbest
polish, weighted mbest, stagnation-based reinjection, adaptive per-particle
beta) all made QPSO's win rate over classical PSO *worse* than just running
the Day-1-tuned QPSO unmodified -- at every instance size tested, in every
case. This is no longer "one idea didn't pan out"; it's a consistent
result across four independent mechanisms, which is itself the finding:
**the plain, tuned quantum update rule is already a well-balanced search
for this problem, and hand-added machinery on top of it — whatever its
literature pedigree — has so far only ever knocked it off that balance.**
The current best configuration remains the Finding 1-2 baseline with
nothing from Findings 3-6 enabled: `beta=(1.0, 0.2)`, 40 particles, 800
iterations, no memetic refinement, no weighted mbest, no stagnation
injection, no adaptive beta.

**Recommendation (updated after Findings 7-9):** further QPSO tuning is no
longer the priority. On the raw metric QPSO already wins 83-100% of
instances (Finding 7), so there is little headroom left to chase. The open
risk is different: whether that advantage survives the multi-vehicle,
capacity-constrained formulation the problem statement actually asks for
(Finding 9). Two untried ideas remain on the research list (heavy-tailed
jump distribution, opposition-based initialization); they are only worth
revisiting if Finding 9's scalability gap needs closing.

## What changed in the code

- `app/core/qpso.py` defaults: `n_particles` 30→40, `n_iterations` 150→800,
  `beta_end` 0.4→0.2 (validated by the sweep above)
- `app/core/baselines/classical_pso.py` defaults bumped to match (`40`
  particles / `800` iterations), so the out-of-the-box comparison uses an
  equal budget for both
- `app/core/benchmark.py` / `BenchmarkConfig` defaults updated to match
- `app/core/local_search.py` (new): 2-opt polish, applied to every non-exact
  algorithm's result in `benchmark.py`. Corrected in Finding 8 to be exact
  for asymmetric leg costs.
- `app/core/benchmark.py` (Finding 7): raw cost is now the headline, with the
  polished cost as a labeled second column (`raw_gap_pct` / `polished_gap_pct`,
  `raw_result` kept alongside the polished `result`); new `run_qpso_vs_pso`
  paired comparison over many instances and seeds (win/tie/loss, mean and
  worst-case improvement, exact sign test, seed-to-seed std, iterations for
  QPSO to match PSO's final cost, per-run CSV export)
- `scripts/compare_qpso_vs_pso.py` (new): CLI for the above, with PSO
  parameter presets (`ours`, `teammate`, `clerc`)
- `app/core/vrp_formulation.py` (Finding 9): multi-vehicle capacitated routing.
  `RouteRequest.n_vehicles`; `RoutingProblem` splits a visiting order into
  per-vehicle routes by capacity (`split`), scores routes (`evaluate_routes`),
  and keeps an allocation-free `cost` fast path that is bit-identical to the old
  single-vehicle cost when `n_vehicles == 1`. Routes are a flat depot-delimited
  list (`[0, a, b, 0, c, 0]`; `split_at_depot` inverts it). Unreachable stops
  raise `UnreachableStopError` up front. `polish_result` now 2-opts each vehicle's
  route separately; the nearest-neighbor baseline is capacity-aware; the exact
  solvers and the memetic knob are single-vehicle only and refuse multi-vehicle
  requests. `scripts/compare_multi_vehicle.py` reproduces Finding 9.
- Day 2 stack (not benchmark-related): `app/core/traffic.py` (random / rush-hour /
  clear congestion), `app/data/osm_loader.py` (OSMnx city loader with disk
  cache), `app/services/`, `app/schemas/`, `app/api/` (the REST API) and the
  `frontend/` map UI.
- `tests/test_qpso_vs_classical_pso.py`: regression guard now asserts on the
  RAW cost (QPSO wins >= 3 of 4 fixed instances at 20 and 30 stops, mean
  improvement > 5%). It deliberately does not assert on the polished cost,
  where the gap is small and not consistently significant.
- `app/core/local_search.py` (Finding 3): added `encode_order` +
  `refine_positions_with_two_opt`, and `memetic_interval` params on
  `QPSO`/`ClassicalPSO` — implemented, tested, **left off by default**
- `app/core/qpso.py` (Finding 4): added `weighted_mbest` param —
  implemented, tested, **left off by default**
- `app/core/qpso.py` (Finding 5): added `stagnation_limit` /
  `reinjection_fraction` params — implemented, tested, **left off by default**
- `app/core/qpso.py` (Finding 6): added `adaptive_beta` param —
  implemented, tested, **left off by default**

## Honest caveats for the demo pitch

- **Say which metric a number is on.** "QPSO finds ~14-28% cheaper routes than
  classical PSO" is true of the raw algorithms. It is not true of the
  2-opt hybrid, where the gap is +0.5% to +3.6% and mostly not statistically
  significant. Quote both, labeled.
- **"Scales up" is not supported.** In the single-vehicle formulation the raw
  edge holds at 20-50 stops but QPSO needs a growing share of the iteration
  budget to match PSO (12% -> 25% -> 54%), and its run-to-run spread is worse
  at 50 stops. With several vehicles the edge holds at ~20 customers, ties at 50,
  and reverses at 100 (Finding 9). Do not claim QPSO's advantage grows with
  problem size.
- Even the raw win is a statistical average, not per-instance dominance
  (single-seed runs lose 2-5 of 30 instances; averaging 3 seeds removes
  nearly all of them). Don't claim "QPSO always beats PSO".
- 800 iterations costs real time (~0.3-1s per solve at these sizes, all
  vectorized NumPy). That's fine for a "click optimize, wait a second" UI,
  but Day 2's `/optimize` API should treat this as an async/latency
  consideration, not assume sub-100ms responses.
- Everything here is synthetic k-nearest-neighbor graphs. Day 3's run on a
  real OSM city graph should re-check the results — real road networks have
  different distance/connectivity structure.
