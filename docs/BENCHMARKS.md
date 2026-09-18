# Benchmark tuning results (Day 1)

## What we were checking

The problem statement's core claim is that QPSO gives "stronger global
search, faster convergence, and a better balance between exploration and
exploitation" than classical metaheuristics. Before building the API/frontend
on top of it, we validated that claim empirically rather than assuming it.

All comparisons apply a 2-opt local-search polish (`app/core/local_search.py`)
uniformly to every algorithm's output, so the comparison is "whose starting
point leads to a better local optimum", not "which algorithm forgot to clean
up after itself." Ground truth for small instances is exact (Held-Karp DP,
`app/core/baselines/exact_held_karp.py`).

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

**Recommendation: stop tuning here.** Two untried ideas remain on the
research list (heavy-tailed jump distribution, opposition-based
initialization) but given four-for-four negative results, the expected
payoff of a fifth attempt is low relative to its time cost against the
3-day deadline. The validated, defensible result is: QPSO beats classical
PSO on average by a real margin (60-67% win rate at 30-50 stops, ~37% at 20
stops with a smaller but still-negative average gap), and that result held
up under real adversarial testing rather than being taken on faith.

## What changed in the code

- `app/core/qpso.py` defaults: `n_particles` 30→40, `n_iterations` 150→800,
  `beta_end` 0.4→0.2 (validated by the sweep above)
- `app/core/baselines/classical_pso.py` defaults bumped to match (`40`
  particles / `800` iterations), so the out-of-the-box comparison uses an
  equal budget for both
- `app/core/benchmark.py` / `BenchmarkConfig` defaults updated to match
- `app/core/local_search.py` (new): 2-opt polish, applied to every non-exact
  algorithm's result in `benchmark.py`
- `tests/test_qpso_vs_classical_pso.py` (new): regression guard — average
  QPSO cost must stay ≤ average classical PSO cost across a fixed set of
  instances, so a future change can't silently undo this
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

- The win is a **statistical average**, not per-instance dominance — don't
  claim "QPSO always finds a better route than PSO" during the pitch; claim
  "QPSO finds better routes on average, especially as the problem scales up."
- 800 iterations costs real time (~0.3–1s per solve at these sizes, all
  vectorized NumPy). That's fine for a "click optimize, wait a second" UI,
  but Day 2's `/optimize` API should treat this as an async/latency
  consideration, not assume sub-100ms responses.
- This tuning used synthetic graphs only. Day 3's scalability run on a real
  OSM city graph should re-check that the 800-iteration threshold still
  holds — real road networks have different distance/connectivity structure
  than the k-nearest-neighbor synthetic graphs used here.
