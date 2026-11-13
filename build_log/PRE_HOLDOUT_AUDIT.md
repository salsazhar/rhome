# Pre-holdout audit

**Date:** 23 August 2026 · **Before opening the holdout at L3.8**

The holdout opens once. Before spending it, every known finding is listed here
with its status, so the run is made on a model whose limitations are understood
rather than discovered afterwards.

## State

| | |
|---|---|
| Tests | **842 passing** |
| Specification clauses | **90 registered, 90 covered, 0 uncovered** |
| Layer 1 audit | 53/53 |
| Layer 2 audit | **47/47** (one stale check found and fixed, below) |
| Guardrail 1 — import boundary and sealed data | clean |
| Guardrail 3 — parameter registry | 105 registered, **0 unread** |
| The athlete's real export | sealed, checksums intact, unread |
| The synthetic holdout | **unopened** |

## One thing found by this audit

The Layer 2 audit's S11 check failed at 1.653% against a 1% requirement. Not a
regression: `DATA.md` §19.7 was scoped at L3.3 to an *established* estimate, and
this check built six observations. It had passed only because the learning rate
was fixed; the gain schedule made the young case visible, which is what it is
for.

Fixed, and made stronger — the check now uses twenty prior observations
(0.598%) **and** a companion check pins the young case (3.278%), so both halves
of the scoped requirement are covered.

## Known limitations, carried into the holdout deliberately

These are documented, specified where a fix exists, and **not** fixed before the
run. The holdout measures the engine as it is.

| | Status |
|---|---|
| **Illness read as training fatigue** — ρ 0.802 during illness against 0.992 nearby, while volume falls 41% | Confirmed at L3.7 with a visible mechanism. Fix specified as **L5.2**, deferred |
| **Fatigue accumulation is linear** — the engine expresses 67% of the true contrast in ranking tests | Known and documented. Fix specified as **L5.3**, deferred to after Checkpoint 3 |
| **Capacity warm-up** — under-predicts by ~3.4% over an exercise's first ten sessions | Halved by the L3.3 gain schedule, not removed. Confidence now reports it |
| **Missing wearables fabricate freshness**, not fatigue — a fortnight blind reads ~8% cheerful | Recorded at L3.7. Interacts with L5.2; to be decided together |
| **One calibration band missed** — failure-heavy single session at 7.51% against 5–7% | Recorded at L3.5. Not systematic, so λ is not re-derived and the band is not widened |
| **Engine ties a five-set moving average** on the settled ablation | Recorded at L3.3 as the number personalisation must beat |
| **Fatigue confidence reads `high` on 498 of 520 days** | Defensible on clean synthetic data; untested against a real record |
| **Nuzzo curves for bench and leg press are Grade C approximations** | Open since L0.4; awaiting the exercise-specific tables |

None of these is a defect that would make a holdout result uninterpretable.
Each is a property of the model being tested, and each is written down before
the test rather than after it.

## Why the holdout can be spent now

The synthetic holdout is **not** a one-shot resource in the way the athlete's
real data is. `simulate(seed)` produces a different athlete, so a fresh holdout
can be generated to validate L5.2 and L5.3 later. What must not happen is
re-opening *this* holdout after changing the model in response to it — and
`rhome_eval.window` records every opening precisely so that a second one cannot
be quiet.

The athlete's real data remains genuinely one-shot, and remains sealed.
