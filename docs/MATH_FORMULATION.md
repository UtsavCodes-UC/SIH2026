# Mathematical formulation

What the software solves, how it scores a plan, and how each algorithm searches. Every formula here is the one the code
uses; the file that implements it is named next to it. Results and their caveats are in [BENCHMARKS.md](BENCHMARKS.md).

Equations are written as plain text so they read the same everywhere.

## 0. In one paragraph

A fleet of identical vans starts at one depot, must visit every delivery stop exactly once, and returns to the depot. Each
van can carry at most Q units. Driving times come from a road network whose travel times change with traffic. We look for the
set of routes that minimizes the **total driving time of all vans**, or, if asked, a weighted blend of driving time, distance
and congestion delay. With one van this is the travelling-salesman problem;
with several it is the capacitated vehicle routing problem (CVRP). Both are NP-hard, so the code searches heuristically
(QPSO, PSO, GA, a route search) and, for very small single-van cases, exactly (Held-Karp).

## 1. What is and is not quantum-inspired

| Piece | Quantum-inspired? |
|---|---|
| **QPSO** (section 4) | **Yes.** A particle is modelled as a quantum particle in a delta-potential well instead of a body with velocity. It is a *classical algorithm* that borrows that model; it runs on ordinary hardware, no quantum computer is involved. |
| Classical PSO, genetic algorithm, nearest neighbour, Held-Karp | No (baselines and ground truth for comparison) |
| 2-opt polish and the **route search** (section 5) | No. Classical local search. The route search is an add-on option that uses no swarm, and QPSO does not use it. |

## 2. The problem

### 2.1 Road network and traffic

The network is a directed graph G = (N, A). N are intersections, A are road segments (one arc per driving direction). Each arc
a = (u, v) has

```
length_a        km
tau_a           free-flow travel time, minutes  =  length_a / free-flow speed
gamma_a > 0     congestion factor: 1.0 = free flow, 2.5 = 2.5x slower
w_a = tau_a * gamma_a      current travel time of the arc                  (graph_model.py)

delay_a = tau_a * max(0, gamma_a - 1)        minutes lost to congestion on the arc; 0 on a free-flowing road
c_a = alpha * w_a + beta * length_a + kappa * delay_a      the cost of the arc               (cost_model.py)
      alpha, beta, kappa >= 0, not all zero: the weights on time, distance and congestion
      default alpha = 1, beta = kappa = 0, i.e. plain travel time
```

Free-flow speed is the OpenStreetMap `maxspeed` tag when present, otherwise a typical urban speed for the road class
(`osm_loader.py`); synthetic networks use 40 km/h. Because each direction has its own gamma, travel times are
**asymmetric**: going from u to v can take longer than coming back.

**Dynamic weight update.** The congestion factors are rewritten while the app runs; the next solve sees the new weights.
Sources (`traffic.py`, `live_traffic.py`):

```
free flow      gamma_a = 1
random         gamma_a ~ Uniform(low, high), independently per arc          (default 0.8 .. 2.5)
rush hour      gamma_a = max(0.5, (1 + (peak-1) * exp(-(d_a/sigma)^2)) * (1 + eps_a))
               d_a = distance of the arc midpoint from the network centre,
               sigma = 0.45 * (distance of the farthest node), eps_a ~ Uniform(-noise, noise)
live traffic   for a measured road segment:  slowdown = min(6, max(1, free_flow_speed / current_speed))
               (6 for a closure); several readings on one road are averaged with their confidence as weights;
               unmeasured roads take the distance-weighted mean of nearby measured roads
               (weight 1/(d+0.05)^2, same road class counting 1.0 against 0.4), or their class median
recorded       a saved set of gamma_a values replayed later
```

### 2.2 Leg times

Only travel between the depot and the stops matters. For a problem with depot 0 and stops S = {1, ..., n} we compute, once,

```
t(u, v) = cost of the cheapest path from u to v in G under the arc costs c_a      (Dijkstra from each node)
```

for every u, v in {0} u S. With the default weights that is the quickest travel time; with others a leg follows the cheapest
road under the blend, which can be a slightly longer road that avoids a jam. All three terms of c_a are non-negative, so
Dijkstra applies. t is asymmetric (t(u,v) may differ from t(v,u)) and obeys the triangle inequality. With it, any
candidate plan is scored without touching the graph again (`RoutingProblem`, `vrp_formulation.py`). The map shows the actual
roads: each leg is drawn along its quickest path (`views.py`).

### 2.3 Instance data

```
depot 0, stops S = {1..n}, demand q_i >= 0 for each stop
m identical vans, capacity Q
optional, per stop: a time window [e_i, l_i], 0 <= e_i <= l_i (minutes after the vans leave the depot)
optional: a service time s (minutes at every stop), a lateness price P_w (default 10 per minute)
```

In the app the demands default to a random integer in 5..25, Q to 100, and m to the smallest fleet that carries the
demand at 85% utilization: m = ceil( sum(q_i) / (0.85 * Q) ) (`problem_builder.py`).

### 2.4 Solutions and objective

A solution is m routes R_1, ..., R_m (some may be empty) that partition S; route R_k = (r_1, ..., r_L) is driven
0 -> r_1 -> ... -> r_L -> 0.

```
T(R)  = t(0, r_1) + sum_{j=1}^{L-1} t(r_j, r_{j+1}) + t(r_L, 0)          T(empty route) = 0
q(R)  = sum of q_i over the stops of R

minimize   C(R_1..R_m) = sum_k T(R_k)  +  P * sum_k max(0, q(R_k) - Q)
```

The second term is a **soft capacity constraint**: any load above Q is penalized by P = 1000 minutes per unit of overload
(`penalty_weight`). This ranks an overloaded plan far below every feasible one but lets the search pass *through*
infeasible plans on its way between feasible ones. Feasibility is always reported separately (the API returns `feasible` and
`capacity_violation`, and the UI shows "all respected" or the overload); with the app's auto-sized fleet a feasible plan
normally exists. If the total demand exceeds the fleet's capacity none does, and the API says so (`problem_warnings`).

By default the objective is the **sum of driving times** (alpha = 1); with the other weights T(R) above is the route's total
arc cost, a blend of minutes, kilometres and congestion delay (the "Travel time / Distance / Congestion" sliders in the UI).
Whatever the weights, a finished plan is reported in real units: minutes driven, kilometres and minutes of congestion delay,
each added up along the roads actually driven (`path_metrics`), next to the weighted cost that was minimized (BENCHMARKS.md,
Finding 16). Only the ratios of the weights matter. The time at which the last van gets home ("job finishes in") is shown in
the UI but not optimized; loading and unloading time is not modelled.

**Soft time windows** (`core/time_windows.py`). Every van leaves the depot at time 0. Along a route (r_1, ..., r_L), with
tt(u,v) the REAL driving minutes from u to v (the minutes along the road that the cost weights choose, not the blended cost):

```
a_1 = tt(0, r_1)                          arrival at the first stop
b_j = max(a_j, e_{r_j})                   service starts when the window opens: a van that arrives early waits
a_{j+1} = b_j + s + tt(r_j, r_{j+1})      s = service time at every stop
late_j = max(0, a_j - l_{r_j})            a van that arrives after the window closes still serves the stop, and is late
```

A stop with no window has e = 0 and l = infinity, so it is never early or late. Waiting costs nothing by itself but delays every
later stop, which is how it reaches the objective. The return leg to the depot has no window. With windows the objective is

```
minimize   C = sum_k T(R_k)  +  P * sum_k max(0, q(R_k) - Q)  +  P_w * sum_{stops} late_j
```

The windows are soft: a plan that misses one is not infeasible, it is charged, and the UI and API report each stop's arrival,
waiting and lateness next to the totals. Because the clock makes a route's cost depend on when it starts, three components
that rely on the cost being a sum of independent legs do not handle windows: the linear-time optimal Split (it falls back to the
greedy cut), Held-Karp (skipped in benchmarks, refused if asked) and the route search (refused with a message). The polish keeps
its result only if the objective above is lower afterwards. See BENCHMARKS.md, Finding 17 for what this does to the plans.

The same problem as an integer program (the standard three-index CVRP formulation; the code does *not* solve it this way, it
searches over routes, which builds the constraints into the representation):

```
x_ijk in {0,1}: van k drives directly from i to j          i, j in {0} u S

min   sum_k sum_{i != j} t(i,j) x_ijk
s.t.  sum_k sum_{j != i} x_ijk = 1                            every stop is left exactly once
      sum_{i != h} x_ihk = sum_{j != h} x_hjk                 a van that enters a stop leaves it
      sum_{j in S} x_0jk <= 1                                 van k leaves the depot at most once
      sum_{i in S} q_i sum_{j != i} x_ijk <= Q                capacity (soft in the code, via P)
      subtour elimination                                     no cycle avoids the depot
```

(With windows the integer program needs the arrival times above as extra continuous variables, linked to x by big-M
constraints; the recursion above is what the code evaluates.)

**Special cases.** m = 1 is the asymmetric travelling-salesman problem with a start and end at the depot. It is solved exactly
by **Held-Karp** dynamic programming over subsets in O(2^n n^2) time, used as ground truth up to 16 stops
(`exact_held_karp.py`). For m > 1 no exact baseline is computed.

**Not modelled:** hard time windows (they are soft), a different service time per stop or per-van start times, a heterogeneous
fleet, several depots, stochastic demand, turn penalties. Congestion is frozen during one solve; a new solve is run after traffic
changes.

## 3. Representation: from a permutation to routes

The metaheuristics search over **permutations** of the stops, the "giant tour" pi = (p_1, ..., p_n). Every stop appears
exactly once by construction, so the visit-each-stop constraint never has to be checked. A decoder cuts pi into routes.

**Greedy split** (default, `RoutingProblem.split` / `cost`). Walk pi and keep the running load of the current van. Before
adding stop p, if the load is above zero, load + q_p > Q, and fewer than m - 1 vans have been closed, send the current van
home and start the next one. The last van takes what remains (any excess over Q is the penalized overload). Scoring a
permutation is one pass, O(n).

**Optimal split** (`decoder="optimal"`, available in the library, not exposed in the UI). The cheapest way to cut pi into
consecutive capacity-respecting routes, by dynamic programming (Prins 2004), in linear time with a sliding-window
minimum (Vidal 2016):

```
F(0) = 0
F(j) = min over i <= j with q(p_i..p_j) <= Q of  F(i-1) + t(0,p_i) + sum_{h=i}^{j-1} t(p_h,p_{h+1}) + t(p_j,0)
     = fwd(j) + t(p_j,0) + min_i [ F(i-1) + t(0,p_i) - fwd(i) ],        fwd(j) = sum_{h<j} t(p_h,p_{h+1})
```

The feasible i for a given j form a window whose left end only moves right, so the minimum is kept in a monotone queue. With a
fleet limit it becomes a layered version; if no partition fits the fleet it falls back to the greedy cut. Its measured value is
in BENCHMARKS.md, Finding 12 (about 1%).

**Random keys** (Bean 1994). QPSO and PSO move in continuous space, a particle being a vector x in [0,1]^n. It is decoded by
sorting:

```
pi = argsort(x)         the stop with the smallest key comes first
```

so a continuous update rule solves a discrete ordering problem with no special operators. `encode_order` is the inverse
(key of the stop at rank r is (r + 0.5)/n), used to place a known good route into the swarm.

## 4. QPSO, the core algorithm (`qpso.py`)

Classical PSO gives each particle a position and a velocity. QPSO (Sun, Feng and Xu 2004) drops the velocity: the particle is
modelled by a wave function in a delta-potential well centred on an **attractor**, and each step *samples* a new position from
it. That sampling is the "quantum" part.

Notation: P particles; particle i has position x_i in [0,1]^n, personal best p_i (the best position it has visited) and
fitness f(x) = C(decode(x)). g is the global best. Each iteration t = 0..T-1:

```
mbest_d   = (1/P) * sum_i p_{i,d}                                   mean of all personal bests, per dimension d
phi       ~ Uniform(0,1)                                            drawn per particle and dimension
a_{i,d}   = phi * p_{i,d} + (1 - phi) * g_d                         the attractor: a random point between pbest and gbest
u         ~ Uniform(0,1) (clipped to [1e-9, 1-1e-9]),  s = +1 or -1 with equal probability
x_{i,d}  <-  clip( a_{i,d} + s * beta_t * |mbest_d - x_{i,d}| * ln(1/u),  0, 1 )
```

The new position is scored, p_i is replaced if it is better, and g is updated. The **contraction-expansion coefficient**
beta is annealed linearly, large early (wide jumps, exploration) and small late (fine moves, exploitation):

```
beta_t = beta_0 - (beta_0 - beta_1) * t / (T - 1)
beta_0 = 1.0 * min(1, 50/n),   beta_1 = 0.2 * min(1, 50/n)          defaults
```

Sun et al. show the swarm contracts onto the attractor when beta is below about 1.78; the schedule stays below that. The factor
min(1, 50/n) is our addition (BENCHMARKS.md, Finding 10): the jump is proportional to the swarm's spread, so with many stops the
unscaled default reorders the decoded tour more than it refines it and QPSO loses to classical PSO; the scaling does not
change anything up to 50 stops. Defaults: P = 40 particles, T = 800 iterations. Cost per iteration is O(P n log n) (one sort
per particle to decode) plus P evaluations of O(n).

**Initialization.** Random keys, U(0,1)^n. With **warm start** (the app's default) two particles start as encodings of the
nearest-neighbour plan and of that plan after 2-opt (`warm_start.py`); the rest stay random for diversity. With time windows
a third seed is added: a nearest neighbour by time, which goes next to the stop whose service could start soonest (Finding 17
shows this is what made the algorithms good at windows). From about 50
stops a random start is beaten by plain nearest neighbour (Finding 10), so the swarm is asked to improve a good plan
rather than find one.

**Polish.** The best plan is then improved by the classical local search of section 5.1 (2-opt inside routes, then moving stops
between vans). Reports show both the raw QPSO result and the polished one, because the polish removes most of the difference
between algorithms (BENCHMARKS.md, Findings 7 and 9).

### 4.1 Baselines for comparison

```
Classical PSO   v <- w*v + c1*r1*(pbest - x) + c2*r2*(gbest - x);   |v| <= 0.5;   x <- clip(x + v, 0, 1)
                w annealed 0.9 -> 0.4, c1 = c2 = 2.0, same random keys and decoder as QPSO      (classical_pso.py)
Genetic algorithm   permutation genome; tournament selection (size 3); order crossover (OX);
                swap mutation with probability 0.15; the single best individual survives        (genetic_algorithm.py)
Nearest neighbour   from the current position go to the closest remaining stop that still fits the van's
                remaining capacity; when nothing fits, return to the depot and start the next van (dijkstra_baseline.py)
Held-Karp       exact, one van, up to 16 stops
```

All of them optimize the same C through the same decoder, so their scores are like-for-like.

## 5. Classical local search

### 5.1 2-opt inside a route, and the older polish (`local_search.py`)

2-opt reverses a segment of a route when that shortens it. With asymmetric t a reversal also changes the direction of every
leg inside the segment, so the textbook delta is wrong (it accepted "improvements" that lengthened the tour, Finding 8). The
exact change for reversing positions i..j of a route (..., a, [b ... c], d, ...) is

```
delta = t(a,c) + Rev(i..j) + t(b,d) - t(a,b) - Fwd(i..j) - t(c,d)
Fwd = sum of t(route_k, route_{k+1}) over the segment,   Rev = sum of t(route_{k+1}, route_k)
```

both taken from prefix sums in O(1); a move is made when delta < 0. `improve_routes` adds two between-van moves: moving a run
of 1-3 consecutive stops into another van, and exchanging one stop of each of two vans, whenever the penalized objective C
falls. This is the polish the app applies by default.

### 5.2 Route search: moves between vans and iterated local search (`route_search.py`)

An optional solver ("Route search" in the UI) that starts from the nearest-neighbour plan and improves whole route sets. It
uses no swarm. Notation: a stop x sits in route A between u (before) and v (after), the depot counting as a neighbour; excess(L)
= max(0, L - Q). Each move's change in C is computed **exactly** for the asymmetric t, because none of them reverses a stretch
of road except the intra-route 2-opt, which uses section 5.1's formula.

```
relocate a run s_1..s_r (r = 1..3) of route A to sit between a and b (in another route, or the same one):
    delta = [t(a,s_1) + t(s_r,b) - t(a,b)]  -  [t(u,s_1) + t(s_r,v) - t(u,v)]  +  P * (change in overload of the two routes)
swap  stop x of route A with stop y of route B, each taking the other's place:
    delta = t(u_x,y) + t(y,v_x) - t(u_x,x) - t(x,v_x)  +  t(u_y,x) + t(x,v_y) - t(u_y,y) - t(y,v_y)  +  P * (change in overload)
2-opt*  cut A after a_i and B after b_j and exchange the tails:  A' = A[..a_i] + B[b_{j+1}..],  B' = B[..b_j] + A[a_{i+1}..]
    delta = t(a_i,b_{j+1}) + t(b_j,a_{i+1}) - t(a_i,a_{i+1}) - t(b_j,b_{j+1})  +  P * (change in overload)
SWAP*   exchange x of A and y of B, but each is re-inserted at ITS best position in the other route, not necessarily where the
        other stop was (Vidal 2022); contains "swap" as a special case
```

2-opt* is due to Potvin and Rousseau (1995). Relocation and swap are the classical moves; the two new ones together are worth
several percent (BENCHMARKS.md, Finding 13). For speed a stop is only paired with its **12 nearest stops** (by t(x,z) + t(z,x)),
and after a change only the stops of the routes it touched are examined again. The search holds exactly m route slots, so a van
can be emptied and an unused van used; the objective is the same C as everywhere else.

**Iterated local search (ILS).** The local search alone stops at a local optimum. Each ILS iteration escapes it:

```
1. ruin       pick a random stop c; remove c and (r - 1) stops sampled from the 2r stops nearest to c, r ~ Uniform{4..12}
              (ruin-and-recreate, Schrimpf et al. 2000)
2. recreate   put the removed stops back one at a time, in random order, each at its cheapest position
              (an unused van counts as a place)
3. repair     run the local search on the stops of the routes that changed
4. accept     keep the result only if C is strictly lower; otherwise undo
```

The best plan is kept throughout. In the app it stops at the time limit, or after 300 + 10 n iterations without a new best
(a small problem settles long before the limit). An iteration costs about 10 ms at 50-200 customers with about 6 stops per
van (Finding 13); it is much slower with one long route, where every move touches the whole route.

## 6. How results are measured

The comparisons in BENCHMARKS.md follow one method (`benchmark.py` and the scripts):

- **Same problem, same decoder, same cost C** for every algorithm; several random instances per size, compared **pairwise** per
  instance.
- **Raw vs polished.** "Raw" is what an algorithm found on its own; "+ polish" adds the local search of 5.1. Raw is the
  like-for-like comparison of the algorithms; polished is what a production engine would deliver.
- **Significance:** the exact one-sided sign test. With W wins and L losses (ties dropped) the p-value is
  P(at least W wins in W + L fair coin flips) = sum_{k=W}^{W+L} C(W+L,k) / 2^(W+L). It ignores the size of a win, which keeps it
  conservative.
- **Gap to a reference:** gap = 100 * (cost - reference) / reference, where the reference is the exact Held-Karp optimum (up
  to 16 stops, one van), OR-Tools' guided local search, or the proven optimum of a standard CVRPLIB instance (Finding 14).
  Positive means worse than the reference.
- **Standard instances** (CVRPLIB "X" set) are scored with the benchmark's own rule: Euclidean distances rounded to the nearest
  integer, no shortest-path shortcuts (`app/data/cvrplib.py`).

## 7. Complexity and where the code is

| Quantity | Cost | Code |
|---|---|---|
| Leg-time table t(u,v) | one Dijkstra from each of the n + 1 nodes | `graph_model.all_pairs_shortest_time` |
| Score one permutation (greedy split), with or without time windows | O(n) | `RoutingProblem.cost` |
| Optimal split | O(n) without a fleet limit | `RoutingProblem._optimal_split` |
| QPSO iteration | O(P n log n) | `qpso.py` |
| 2-opt pass | O(n^2), exact delta in O(1) | `local_search.two_opt` |
| Held-Karp | O(2^n n^2), n <= 16 | `exact_held_karp.py` |
| Route search / ILS | neighbour lists + a work queue; about 10 ms per ILS iteration (measured) | `route_search.py` |

## 8. References

- Sun, Feng, Xu (2004). Particle swarm optimization with particles having quantum behavior. IEEE Congress on Evolutionary
  Computation.
- Kennedy, Eberhart (1995). Particle swarm optimization. IEEE International Conference on Neural Networks.
- Bean (1994). Genetic algorithms and random keys for sequencing and optimization. ORSA Journal on Computing 6(2).
- Prins (2004). A simple and effective evolutionary algorithm for the vehicle routing problem. Computers & Operations Research 31(12).
- Vidal (2016). Split algorithm in O(n) for the capacitated vehicle routing problem. Computers & Operations Research 69.
- Potvin, Rousseau (1995). An exchange heuristic for routeing problems with time windows. Journal of the Operational Research Society 46.
- Vidal (2022). Hybrid genetic search for the CVRP: open-source implementation and SWAP* neighborhood. Computers & Operations Research 140.
- Schrimpf, Schneider, Stamm-Wilbrandt, Dueck (2000). Record breaking optimization results using the ruin and recreate principle.
  Journal of Computational Physics 159.
- Held, Karp (1962). A dynamic programming approach to sequencing problems. Journal of the SIAM 10(1).
- Uchoa, Pecin, Pessoa, Poggi, Subramanian, Vidal (2017). New benchmark instances for the capacitated vehicle routing problem.
  European Journal of Operational Research 257(3).
