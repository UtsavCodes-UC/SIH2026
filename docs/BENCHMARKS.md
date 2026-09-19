# Benchmark results

## Read this first — current headline (Findings 7-9)

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
