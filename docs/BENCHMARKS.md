# Benchmarks

The problem statement asks for the quantum-inspired method to be benchmarked against conventional metaheuristics and exact methods. This document
reports every experiment we ran: what was compared, on what, and what came out, including the results that do not favour QPSO.
Each experiment is a script in `backend/scripts/` and its raw output is a CSV in `backend/results/`.

## How to read the numbers

- **Raw** is what an algorithm finds by itself. **Polished** is the same plan after a shared local search (2-opt inside each route, then moving stops
  between vans). Raw is the like-for-like comparison of the algorithms; polished is what the app returns.
- Comparisons are paired, instance by instance: wins / ties / losses, the mean improvement, and an exact one-sided sign test (ties left out). We do not
  quote a difference as real unless the test supports it.
- Unless a section says otherwise the instances are synthetic road networks (80 intersections, 8 km) with random congestion, a depot, random stops with demands of
  5 to 25, vans of capacity 100, and a fleet sized for about 85% utilization. Cost is driving minutes plus 1,000 per unit of overload.
- QPSO, PSO and GA use 40 particles (or individuals) and 800 iterations (the shortest-path searches use 30 and 200). Runs use the pinned environment in `backend/requirements.txt` (numpy 1.26.4, networkx 3.3).
- "Route search" is a classical local search between routes with iterated restarts; it is an option in the app, and QPSO stays the default solver.

## Summary

| Question | Short answer | Finding |
|---|---|---|
| Is QPSO better than classical PSO? | On raw output, yes: 13.6 to 28.1% cheaper routes at 20 to 50 stops, significant in all 9 settings. After the same polish the gap is 0.5 to 3.6% and mostly not significant. | 7 |
| How fast does it converge? | It reaches PSO's final quality in about 12%, 25% and 54% of the iterations at 20, 30 and 50 stops. | 7 |
| Does that hold with several vans? | At about 20 customers (+10.6% raw). It ties at 50; at 100 it loses until the jump size is scaled with problem size (then +12.4%). | 9, 10 |
| Does QPSO beat a genetic algorithm? | No. After warm start and polish, QPSO, PSO and GA end within about 1 to 3% of each other. | 10, 11, 17, 18, 20 |
| How close to optimal on small problems? | The default pipeline is 1.5 to 3.6% above the exact optimum (10 to 14 stops). The route search is exactly optimal on all 150 instances. | 20 |
| How close on standard benchmarks with proven optima? | Route search: 2.9% above optimal after 10 s, 1.5% after 2 min, on 22 instances of 100 to 199 customers. OR-Tools (60 s): 5.5%. Default QPSO pipeline: 10.2%. | 14 |
| Route search vs the default in the app? | Cheaper on every instance from 30 stops, by 6 to 10%. | 15 |
| Do the time / distance / congestion weights work? | Yes, and they expose real trade-offs. | 16 |
| Time windows, shortest path, closed roads? | Modelled and tested; QPSO is level with PSO and GA, and Dijkstra is exact for shortest paths. | 17, 18, 19 |

## Part 1: QPSO against classical PSO

### Finding 7: raw against polished, three PSO settings

Single-van tours, 30 random instances per size, three classical-PSO parameter sets (ours, an independent implementation's, and the standard Clerc constriction values)
so the result does not depend on a weak baseline. Cells: raw QPSO wins out of 30 (raw mean improvement); polished mean improvement (p).

| PSO settings | 20 stops | 30 stops | 50 stops |
|---|---|---|---|
| ours | 28 (+17.2%); +0.5% (0.18) | 26 (+27.6%); +1.1% (0.29) | 25 (+18.7%); +1.9% (0.18) |
| independent implementation | 30 (+18.7%); +2.5% (0.18) | 30 (+28.1%); +2.9% (0.57) | 21 (+13.6%); +2.5% (0.18) |
| Clerc | 29 (+19.1%); +3.6% (0.02) | 26 (+25.5%); +2.9% (0.29) | 28 (+17.4%); +3.2% (0.008) |

Crossed design (30 instances x 3 algorithm seeds, averaged per instance):

| stops | raw wins | raw improvement | QPSO matches PSO's final cost after |
|---|---|---|---|
| 20 | 30 of 30 | +16.4% | median 96 iterations (12% of the budget) |
| 30 | 30 of 30 | +26.2% | median 201 (25%) |
| 50 | 29 of 30 | +18.8% | median 431 (54%) |

- The raw result is strong and robust: p of 0.02 or lower in every one of the nine settings, and an independent multi-vehicle implementation showed the same direction.
- It is a statistical edge, not dominance: single runs lose 2 to 5 of 30 instances, and at 50 stops QPSO's run-to-run spread is larger than PSO's.
- The polish helps PSO more than QPSO (mean cost falls 22.6 / 39.8 / 56.0% for PSO against 5.7 / 17.1 / 46.8% for QPSO), so polished costs end within 1 to 3%.

### Finding 8: a bug in the first 2-opt polish, and its fix

A test asserting that 2-opt never makes a route worse exposed a flaw: the textbook swap delta assumes equal leg times in both directions, but our roads are directed and
each direction has its own congestion. On random asymmetric costs the old code returned a worse tour in 77 of 2,000 cases. It now uses forward and reverse prefix sums
and is exact (0 of 2,000). Raw results were unaffected; every polished figure in this document was produced with the corrected code.

### Early tuning experiments (Findings 1 to 6)

- **Finding 1 and 2, tuning.** A sweep of the jump schedule, swarm size and iteration count on small instances with exact ground truth chose 40 particles, 800 iterations and
  a jump schedule of 1.0 to 0.2. At 200 to 400 iterations QPSO and PSO were close to even; QPSO's advantage appears with the longer budget, because its wider steps need time to pay off.
  These runs predate the polish fix in Finding 8, so their tables are not reproduced; Finding 20 re-measures the gap to the exact optimum with the current code.
- **Findings 3 to 6, four additions that did not help.** Periodically polishing every particle's personal best, weighting the swarm mean by rank, re-seeding stagnant
  particles, and giving each particle its own rank-based jump size all lowered QPSO's win rate against PSO (at 30 stops, from 66.7% to 43.3%, 43.3% and 33.3% for the last three;
  polishing personal bests raised ties as both algorithms fell into the same 2-opt basins). The plain tuned update stayed the best configuration. All four are kept as tested,
  off-by-default options. Finding 3 was re-run after the polish fix and the verdict held; Findings 4 to 6 were not re-run.

## Part 2: several vans, and making 50 to 100 customers work

### Finding 9: capacity-constrained routing with several vans

The visiting order is cut into van routes by capacity, and QPSO and PSO were compared on raw cost (20 instances per row):

| customers (fleet utilization) | QPSO vs our PSO: win / loss, improvement, p |
|---|---|
| 20 (73%) | 18 / 2, +10.6%, p = 0.0002 |
| 50 (81%) | 11 / 9, +3.7%, p = 0.41 |
| 50 (87%) | 9 / 11, +0.3%, p = 0.75 |
| 100 (83%) | 5 / 15, -8.0%, p = 0.99 |

The edge holds at about 20 customers, is a tie at 50 and reverses at 100.

### Finding 10: scaling to 50 to 100 customers

- **The jump was too big at 100 dimensions.** With the jump scaled by min(1, 50 / stops), QPSO against PSO at 100 customers goes from 5 wins / 15 losses (-8.0%) to
  19 wins / 1 loss (+12.4%, p < 0.0001). Up to 50 stops the result is bit-identical to before.
- **A random start is the bigger problem.** Mean raw cost:

  | customers | nearest neighbour | PSO | QPSO | GA |
  |---|---|---|---|---|
  | 20 | 1,032 | 950 | 852 | 864 |
  | 50 | 2,106 | 2,659 | 2,548 | 2,035 |
  | 100 | 3,634 | 6,554 | 5,707 | 4,237 |

- **A warm start fixes most of it**: two starting particles are the nearest-neighbour plan and the same plan after 2-opt. QPSO's raw cost falls 25% at 50 customers
  and 39% at 100. A polish that also moves stops between vans cuts cost a further 18 / 12 / 10% at 20 / 50 / 100 customers.
- **What is left between the methods** once everything is warm-started and polished (mean cost):

  | customers | nearest neighbour + polish | PSO | QPSO | GA |
  |---|---|---|---|---|
  | 20 | 846 | 822 | 800 | 826 |
  | 50 | 1,800 | 1,751 | 1,761 | 1,759 |
  | 100 | 3,201 | 3,181 | 3,187 | 3,148 |

  QPSO's edge over PSO is real at about 20 customers (+2.8%, 10 wins, 0 losses). At 50 the three are indistinguishable. At 100 the pipeline does the work: QPSO is 1.2% worse
  than the warm GA after the polish (p = 0.010). We therefore do not claim that QPSO scales better than other metaheuristics.
- The app's default result improved 5.4% at 20 customers, 22.8% at 50 and 40.4% at 100 compared with the first version (cold start, old jump, simpler polish).

### Finding 11: a hybrid engine for 100 or more stops

A hybrid (adaptive jump, elite archive, 2-opt on swarm tours, restarts from kicked elites, mixed initialization) on single-van tours, mean cost after the same final 2-opt at 100 stops
(20 instances), against OR-Tools' guided local search (a strong reference, not a proven optimum):

| bare PSO | bare QPSO | GA | nearest neighbour + 2-opt | hybrid PSO | hybrid QPSO | OR-Tools |
|---|---|---|---|---|---|---|
| 1,234 | 1,273 | 1,290 | 1,114 | 1,014 | 1,013 | 981 |

- The hybrid QPSO is 17.5% cheaper than bare PSO (20 wins, 0 losses) and 3.2% above OR-Tools; it stays within 1 to 7% of OR-Tools from 50 to 200 stops.
- A hybrid PSO built from the same parts does exactly as well (no size shows a significant difference). The credit belongs to the architecture, mostly the restart step
  (kick a good tour, 2-opt it, keep it if better), not to the quantum update.
- Bare QPSO with the size-aware jump beats bare PSO on raw cost at every size from 50 to 200 stops (for example +20.5%, p = 0.0002 at 50), and 2-opt removes the difference.
- On the multi-van problem the hybrid adds nothing over warm start plus polish (3,192 against 3,187).

### Finding 12: an optimal Split decoder

Replacing the greedy cut of a visiting order into van routes with the optimal partition (Vidal, 2016) is worth about 1% for every method, including plain nearest neighbour, which is the size of the
local search's start-to-start variation. Every pipeline still ends 6.3 to 7.7% above OR-Tools' 60 s solution, so the decoder is not what holds the multi-van search back. It is 30 to 80 times slower per evaluation.
The greedy decoder stays the default.

## Part 3: the route search, and distance from the optimum

### Finding 13: a stronger search between routes

`core/route_search.py` searches over whole sets of routes with five exact-cost moves (relocate, swap, 2-opt inside a route, 2-opt* and SWAP*) using neighbour lists, plus iterated local search.
On the 20 instances of 100 customers used above (OR-Tools 60 s reference: mean 2,937.9):

| | local search only | ILS 100 | ILS 200 | ILS 500 | ILS 1,000 |
|---|---|---|---|---|---|
| mean cost | 3,078 | 2,898 | 2,886 | 2,871 | 2,861 |
| against OR-Tools | +4.9% | -1.3% | -1.7% | -2.3% | -2.6% |
| instances cheaper than OR-Tools | 1 of 20 | 18 | 18 | 19 | 20 |
| time | 0.05 s | 1 s | 2 s | 5 s | 10 s |

- 2-opt* and SWAP* are what close the gap, worth 3.6% together. Starting the search from the routes of a warm QPSO, PSO or GA adds nothing measurable: after local search the four
  starts are within 1.2% of each other, and given the swarm's running time as extra iterations, nearest neighbour is equal or better.
- The search is built for fleets. On a single long tour it is far slower than the hybrid engine (about 5 minutes against 12 s at 100 stops).
- Not tested: a swarm with the search inside its loop; only "swarm first, search after".

### Finding 14: standard instances with proven optima

The 22 CVRPLIB "X" instances with 100 to 199 customers (Uchoa et al., 2017), each with a proven optimal cost, scored with the benchmark's own convention and every answer
re-checked from the coordinates. Mean gap to the optimum:

| method | mean gap | worst | within 2% of optimal | time |
|---|---|---|---|---|
| nearest neighbour (the start) | 29.8% | 52.0% | 0 of 22 | |
| earlier app default (warm QPSO + older polish) | 10.2% | 22.3% | 0 of 22 | 15.7 s |
| OR-Tools guided local search | 5.5% | 13.0% | 0 of 22 | 60 s |
| route search, local search only | 8.3% | 22.1% | 0 of 22 | 0.7 s |
| route search + ILS, 10 s | 2.9% | 6.4% | 7 of 22 | 10 s |
| route search + ILS, 30 s | 2.0% | 6.3% | 14 of 22 | 30 s |
| route search + ILS, 60 s | 1.7% | 6.3% | 17 of 22 | 60 s |
| route search + ILS, 120 s | 1.5% | 4.6% | 18 of 22 | 120 s |

- Against OR-Tools' 60 s solution, the search at 10 s is cheaper on 19 of 22 instances (-2.4%, p = 0.0004) and at 120 s on 21 of 22 (-3.8%). The result of Finding 13 holds on a benchmark we did not build.
- This is not a state-of-the-art solver: dedicated solvers average well under 1% on these instances, it stalls on a few (4 to 6% above), and the instances are Euclidean, with no roads or traffic.
- One run per instance, eight instances at a time on one machine, so times reproduce to within a few tenths of a percent.

### Finding 15: route search against the default, at app sizes

Both run through the API's own solver on synthetic road networks, 20 instances per size. Mean cost (difference from the default, negative means the route search is cheaper):

| stops (vans) | default | route search 1 s | route search 10 s | wins / ties / losses at 1 s |
|---|---|---|---|---|
| 15 (3) | 113.4 | 109.4 (-3.4%) | 109.4 (-3.4%) | 13 / 7 / 0 |
| 30 (6) | 190.5 | 178.3 (-6.4%) | 178.2 (-6.4%) | 20 / 0 / 0 |
| 60 (11) | 335.0 | 301.4 (-9.7%) | 298.7 (-10.5%) | 20 / 0 / 0 |
| 100 (18) | 531.5 | 493.8 (-7.2%) | 479.2 (-10.0%) | 20 / 0 / 0 |

Which solver is the default is a product choice: it stays QPSO, the subject of the project, and the route search is one dropdown away.

### Finding 20: against the exact optimum on small problems

`core/baselines/exact_cvrp.py` computes the true optimum of the objective every solver minimizes (subset dynamic programming with the split into vans), and is tested against exhaustive search.
30 instances per size; gap is 100 x (cost - optimum) / optimum after the app's polish.

| stops | method | optimum found | mean gap | worst |
|---|---|---|---|---|
| 10 | QPSO (app default) | 22 of 30 | 1.48% | 17.6% |
| 10 | classical PSO | 17 of 30 | 2.71% | 43.5% |
| 10 | genetic algorithm | 19 of 30 | 1.37% | 17.6% |
| 10 | nearest neighbour | 13 of 30 | 3.71% | 17.6% |
| 10 | route search (3 s) | 30 of 30 | 0.00% | 0.0% |
| 12 | QPSO (app default) | 12 of 30 | 2.44% | 12.3% |
| 12 | classical PSO | 11 of 30 | 2.73% | 12.3% |
| 12 | genetic algorithm | 7 of 30 | 3.69% | 14.6% |
| 12 | nearest neighbour | 4 of 30 | 4.70% | 17.4% |
| 12 | route search (3 s) | 30 of 30 | 0.00% | 0.0% |
| 14 | QPSO (app default) | 7 of 30 | 3.62% | 12.7% |
| 14 | classical PSO | 6 of 30 | 4.02% | 14.1% |
| 14 | genetic algorithm | 6 of 30 | 4.66% | 15.1% |
| 14 | nearest neighbour | 5 of 30 | 5.55% | 22.0% |
| 14 | route search (3 s) | 30 of 30 | 0.00% | 0.0% |

A single van (12 and 16 stops) gives the same picture; QPSO with a warm start reaches 1.0% and 2.2% mean gap, the route search 0.00%.

- The default pipeline is typically within a couple of per cent but not always, and the gap grows with size. The polish does most of the work: QPSO alone is 6.1, 4.8 and 9.3% above the optimum.
- The route search found the exact optimum on all 150 instances (several vans to 14 stops, one van to 16), in at most 3 s. On problems this small it is effectively an exact solver.
- QPSO's raw advantage over classical PSO reproduces (significant at 10 and 12 stops) and disappears after the polish; against the genetic algorithm nothing is significant.
- Not shown: anything above 14 stops (several vans) or 16 (one van), where there is no exact reference here.

## Part 4: the model features

### Finding 16: cost weights

Each road costs `time x minutes + distance x km + congestion x minutes lost to jams`, so every algorithm minimizes the chosen blend unchanged. Tests check on a hand-built network, and with the
exact solver on random problems, that each weighting picks the plan it should. Mean over 20 instances (app default solver; the route search shows the same pattern):

| optimized for | 30 stops: minutes / km / delay | 60 stops: minutes / km / delay |
|---|---|---|
| Fastest (time only) | 203.2 / 99.2 / 57.9 | 331.4 / 164.4 / 91.6 |
| Shortest (distance only) | 230.2 (+13.5%) / 92.4 (-6.9%) / 93.0 (+62.8%) | 378.5 (+14.3%) / 153.3 (-6.7%) / 151.5 (+67.0%) |
| Avoid jams (time 50%, congestion 50%) | 205.0 (+1.2%) / 103.3 (+4.4%) / 54.0 (-6.1%) | 336.4 (+1.5%) / 172.7 (+5.2%) / 84.7 (-7.6%) |
| Balanced (40 / 30 / 30) | 202.5 (-0.2%) / 99.4 (+0.2%) / 56.9 (-1.1%) | 330.1 (-0.4%) / 164.2 (-0.2%) / 90.6 (-0.9%) |

Fewest kilometres saves 6 to 7% of the distance but costs 13 to 15% more time and raises congestion delay by 59 to 67%, because the shortest roads are the jammed ones. Avoiding jams is cheap:
6 to 8% less delay for about 1% more time. The numbers depend on the network and the units, so they illustrate the trade-off and are not recommended settings.

### Finding 17: soft time windows

A stop may be served between an earliest and a latest minute; early vans wait, late arrivals are charged per minute. QPSO, PSO, GA and nearest neighbour handle windows; the route search and exact solvers do not.
Mean over 20 instances, app default:

| stops | plan | minutes late | stops late | driving (min) | waiting (min) |
|---|---|---|---|---|---|
| 15 | ignores the windows | 157.6 | 4.9 | 107.4 | 86.3 |
| 15 | prices lateness | 0.0 | 0.0 | 135.7 | 49.6 |
| 30 | ignores the windows | 290.2 | 11.2 | 179.7 | 187.9 |
| 30 | prices lateness | 0.0 | 0.2 | 244.2 | 88.8 |

Ignoring windows leaves about a third of the stops late; pricing lateness removes that for 26 to 36% more driving on these random windows. The algorithms only did well once all three received a window-aware starting
solution (a nearest neighbour that goes to the stop whose service can start soonest). With it QPSO is level with the genetic algorithm (12 wins, 8 losses at 30 stops, not significant) and with PSO. We do not claim QPSO is better here.

### Finding 18: shortest path

Dijkstra's algorithm is exact, so it is the reference; QPSO, PSO and a genetic algorithm search for the same path with a priority-per-intersection encoding. 50 random pairs per map size.
Cells: pairs solved optimally / mean gap above the optimum.

| intersections | QPSO | classical PSO | genetic algorithm |
|---|---|---|---|
| 40 | 45 of 50, 0.41% | 44 of 50, 0.30% | 39 of 50, 0.80% |
| 80 | 41 of 50, 0.72% | 38 of 50, 1.57% | 38 of 50, 0.96% |
| 160 | 27 of 50, 3.31% | 22 of 50, 4.64% | 23 of 50, 3.05% |
| 300 | 22 of 50, 4.01% | 21 of 50, 3.09% | 22 of 50, 2.58% |

Dijkstra solves every pair in 0.2 to 0.5 ms against 100 to 550 ms for the searches, and the searches are never better than it. QPSO is not better than PSO or the genetic algorithm (its one significant result is over the GA at 40
intersections). A starting particle that points at the target is what keeps the searches competitive as maps grow. The value of this mode is that the same framework, cost model and traffic serve a second kind of problem and are checked against an exact answer.

### Finding 19: closing a road

A closed road is removed from the network, so every solver plans around it. Closing a random road that a plan uses costs about 1% of the plan (route search: +0.9% at 15 stops, +1.0% at 30; medians about +0.4 to +0.6%), because
each intersection has several roads. The default solver's run-to-run noise (1.5 to 3%, up to 11%) is as large as that effect: 6 of its 40 comparisons showed a closure that "saves" time, which cannot be true. The route search is far steadier (0.00% and 0.25% noise). The
app therefore compares against the plan with every road open, says so in the banner when a closure appears to save time, and the route search is the better choice for what-ifs. Tests cover that plans avoid closed roads and that cut-off stops are named.

## Limits of these results

- Most instances are synthetic road networks with random congestion; the exceptions are the CVRPLIB benchmark (Euclidean, no traffic) and the recorded MG Road traffic used in the demo. Real cities with one-way streets and bridges may behave differently.
- 20 to 30 instances per experiment and one algorithm seed per instance, so small differences are inside the noise; the tests above say which ones are not.
- OR-Tools was run as one untuned configuration (guided local search, one thread, 60 s) and is a strong reference, not a proven optimum. Dedicated solvers such as HGS-CVRP would very likely beat both it and ours.
- Running times were measured on one machine, often with eight processes running, so read them as orders of magnitude.
- Beyond 14 stops (several vans) there is no exact reference here; beyond 200 customers nothing was measured; hard time windows, mixed fleets and several simultaneous closures were not tested.

## Reproducing

From `backend/`, with the pinned environment. OR-Tools reference runs use a separate environment with `pip install ortools`; CVRPLIB data is fetched by `scripts/fetch_cvrplib.py`.

```bash
# Findings 7 and 9: QPSO against PSO
python scripts/compare_qpso_vs_pso.py --stops 20 30 50 --pso-preset ours --csv-dir results/pinned_env
python scripts/compare_multi_vehicle.py

# Finding 10: scaling and jump size
python scripts/scale_experiments.py --customers 100 --instances 20 --polish full --variants qpso_b1.0_0.2 qpso ga pso_warm qpso_warm ga_warm --csv results/scaling/scaling_100customers.csv

# Findings 11 and 12: hybrid engine, decoder
python scripts/hybrid_experiments.py --problem tsp --stops 100 --instances 20 --variants pso qpso h_qpso h_pso ga pso_warm qpso_warm --csv results/hybrid/tsp100.csv
python scripts/decoder_analysis.py

# Findings 13 to 15: route search, CVRPLIB, app comparison
python scripts/route_search_experiments.py --instances 20 --workers 8 --csv results/hybrid/cvrp100_route_search.csv
python scripts/fetch_cvrplib.py && python scripts/cvrplib_benchmark.py --csv results/cvrplib/x_100_200.csv
python scripts/app_options_comparison.py --csv results/app_options/route_search_vs_default.csv

# Findings 16 to 20: model features and the exact optimum
python scripts/cost_weights_tradeoff.py --csv results/cost_weights/tradeoff.csv
python scripts/time_windows_experiment.py --csv results/time_windows/aware_vs_ignoring.csv
python scripts/shortest_path_experiment.py --csv results/shortest_path/paths.csv
python scripts/road_closure_experiment.py --csv results/road_closures/closures.csv
python scripts/exact_gap_experiment.py --csv results/exact_gap/gaps.csv
python -m pytest tests -q          # 431 tests, including checks of the exact solver and every model feature
```

The scripts for Findings 13 to 20 also accept `--from-csv <file>` to print their tables from a saved run without recomputing.
