# Benchmark results

## Read this first — current headline (Findings 7-13)

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
tested with the swarm inside the loop, against standard instances with known optima, or on real road graphs.

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
  (HGS-CVRP) would very likely beat both, and standard instances with known optima (none are used here) are the way
  to measure how far away we are.
- Not tested: a swarm with the route search inside its loop (particles improved by the search every iteration). Only
  "swarm first, search after" was tested, so this finding does not show that a swarm cannot help in that role.
- Not tested: other sizes, looser or tighter fleets (long routes make each iteration slower, see 5), real OSM graphs.

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
