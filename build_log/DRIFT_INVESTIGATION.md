# Residual drift — investigation

**Date:** 23 August 2026 · **Between Checkpoint 2 and L3.1** · Development window only

Checkpoint 2 recorded a residual drift from +0.0508 to −0.0144 across the
window, and an ablation showing the engine losing to a median-of-the-last-three
baseline. I deferred the diagnosis to L3.3 on the grounds that separating the
candidate causes needed latent truth. **That was wrong**, and the athlete was
right to push. Both hypotheses make predictions about observable quantities.

Two fixes were attempted and both reverted. The repository is unchanged; what
follows is what was learned.

## Diagnosis

| Hypothesis | Observable test | Result |
|---|---|---|
| Fatigue-suppression λ mis-scaled | corr(residual, suppression applied) | **+0.050** — nothing, and non-monotone across quartiles |
| Session volume, against the engine's linear accumulation | corr(residual, eligible sets in session) | **−0.060** — nothing; volume is flat across the window |
| Fatigue carried into the set | corr by quartile | non-monotone: +0.017, +0.008, +0.010, +0.014 |
| **Observations of that exercise so far** | mean residual by count | **monotone**: +0.060, +0.051, +0.024, +0.001, −0.006, −0.009, −0.013, −0.013 |

The drift is a function of how many times the engine has seen an exercise. It
is not calendar time, not volume, not fatigue, and not λ. Volume and fatigue
are both *flat* across the window while the residual moves monotonically, which
rules them out directly.

## What the engine is actually worth

Re-running the Checkpoint 2 ablation, excluding the capacity warm-up:

| Sample | Engine MAE | Median-3 MAE | Paired Δ | Verdict |
|---|---:|---:|---:|---|
| All observations | 0.0455 | 0.0434 | +0.00206 ± 0.00152 | baseline |
| After 10 per exercise | 0.0433 | 0.0431 | +0.00015 ± 0.00153 | tie |
| After 20 per exercise | 0.0400 | 0.0424 | −0.00243 ± 0.00149 | **engine** |
| After 30 per exercise | 0.0388 | 0.0420 | −0.00323 ± 0.00163 | **engine, +7.6%** |
| After 40 per exercise | 0.0390 | 0.0421 | −0.00303 ± 0.00181 | engine, holds |

**The engine needs roughly twenty observations of an exercise before it beats
recency, and then beats it by 7.6% and stays there.** The settled residual is
mean −0.0081, sd 0.0489.

This is a better result than Checkpoint 2 reported and a more useful one,
because it comes with a condition attached. The pooled figure was not measuring
a weak model; it was averaging a weak model and a good one.

## Attempt 1 — a Holt trend term (reverted)

If the estimator lagged sustained change, a level-and-slope form would fix it
while preserving bounded influence: the clip bounds what one observation can
do, and a slope handles what a run of consistently signed observations means.
The two requirements are genuinely separable and the design was sound.

It made things worse at every setting tried.

| β | sd | MAE | Residual by 100-day block |
|---|---:|---:|---|
| trend off | **0.0578** | **0.0460** | +0.051 +0.035 +0.004 −0.007 −0.013 −0.014 |
| 0.02 | 0.0591 | 0.0467 | +0.049 +0.029 −0.005 −0.016 −0.022 −0.023 |
| 0.05 | 0.0594 | 0.0472 | +0.048 +0.023 −0.014 −0.021 −0.025 −0.025 |
| 0.10 | 0.0587 | 0.0469 | +0.045 +0.015 −0.021 −0.023 −0.023 −0.022 |

The trend slides the bias line down without narrowing the spread: it trades
early under-prediction for late over-prediction and widens the total range. A
trend term cannot fix a transient, which is what this is.

**One real bug was found along the way.** The first implementation applied
Holt's damping as `φ × Δt`, a linear factor. Damping is a geometric sum, so for
any gap longer than a day `φ = 0.90` *amplified* the slope rather than damping
it. Correcting it to the continuous form improved matters and still left the
trend worse than no trend.

**The original diagnostic was also partly circular.** Correlating the residual
with capacity growth measured *up to and including* the observation being
scored counts that observation's own update, since a positive residual raises
capacity. Recomputed over a strictly prior window the correlation falls from
+0.445 to +0.311 — still real, but a third smaller than first reported.

## Attempt 2 — raising the observation-density saturation (reverted)

If the engine is not competitive below twenty observations, confidence should
say so; the density term saturates at eight. Raising it to twenty-five made
capacity confidence read `limited` for 23 of 27 exercises at the end of the
window.

The two numbers measure different things. `C_obs` counts observations **in the
last 28 days** — a recency term. The ablation measured **lifetime**
observations of an exercise — a maturity term. Demanding twenty-five sets of an
exercise per month is not the same claim and is not a reasonable one.

## What should happen instead

**A capacity-maturity component**, analogous to the baseline-maturity term the
wearable side already has: confidence in an exercise's capacity should rise
with lifetime observations of it, saturating near the twenty-five the ablation
measured, separately from the 28-day recency term.

That is a new component in a section that defines two, so it is a specification
change and belongs at **L3.6**, made deliberately with the evaluation harness in
place. It is recorded here rather than improvised, because two speculative
changes in one sitting is how a model gets hand-fitted to a development window.

## A prediction for the cold run

The athlete's real history is approximately 99 sessions. At two sessions a week
that is about 33 weeks, so a main lift trained twice weekly reaches roughly 66
observations — comfortably above the threshold — while an accessory trained
once a week reaches about 33, and anything performed occasionally sits in the
warm-up regime throughout.

**L3.12 should therefore expect the engine to beat recency on the main lifts
and not on the long tail.** Stating it now makes the cold run a test of a
prediction rather than a narration of whatever happens.


## How long the warm-up actually lasts, and what it affects

The counter is per **exercise**, not per session, and an exercise earns one
scored observation per session it appears in. So the warm-up lasts as long as
that exercise takes to recur twenty times.

| Exercise | Reaches 20 observations |
|---|---|
| calf_raise | day 74 — 11 weeks |
| bench_press | day 140 — 20 weeks |
| cable_row | day 185 — 26 weeks |
| cable_crunch | day 194 — 28 weeks |

Median across the 27-exercise library: **day 151, about 22 weeks.** A narrower
exercise selection warms up proportionally faster, since the same sessions
concentrate on fewer movements.

**Direction.** During warm-up observed performance exceeds the projection by
**+5.6%**: the engine under-predicts, believing the athlete weaker than they
are. After twenty observations this is −0.12%. Conservative, which is the
better direction to be wrong in, but early projections read low.

**Scope.** `transform_set` never reads capacity — the dose channels depend only
on repetitions, reserve, exercise and novelty. Local fatigue, neuromuscular
strain, systemic load and the recovery context are therefore at full quality
from the first session. **Only performance prediction warms up.** The
fatigue-and-recovery half of the product works immediately; the "what should I
lift today" half needs history.

## The better candidate fix, for L3.3

The learning rate is fixed at α = 0.06 from the fourth observation onward. With
four observations in hand that is close to absurd: the estimate moves 6% toward
each new reading when it should be moving most of the way, because there is
almost nothing behind it to defend.

A **gain schedule** — α_t = max(α, 1/n) or the equivalent recursive
least-squares form — makes early observations move the estimate hard and later
ones barely at all. It targets the diagnosed cause directly, where the Holt
trend was aimed at a cause that turned out not to be there, and it costs
nothing in robustness: by the time one anomalous session could do damage, n is
large and the gain is back to α.

This is not implemented here. It is the first thing L3.3 should try, and it
should be judged by the ablation ladder rather than by whether the residual
looks tidier.


---

## Attempt 3 — a flat bias correction (rejected on evidence)

The athlete proposed the obvious thing: if every early estimate is 5% low, add
5% until it is not needed. A known systematic bias should not be left in place,
and bias correction of a known estimator bias is ordinary practice.

**The bias is not a constant.** Across the 27 exercises it ranges from +0.04%
to +11.57%, and it correlates **+0.542** with how fast that exercise's true
capacity is actually growing.

| | Mean warm-up bias |
|---|---:|
| Slowest-growing half of exercises | +3.54% |
| Fastest-growing half | +6.96% |

The +5% average exists because this athlete grew on every exercise. The bias is
not a property of the estimator alone; it is the interaction of estimator lag
with the athlete's own rate of change. A flat correction would under-correct
fast growers and, worse, **manufacture a −5% bias where none existed** for an
athlete who is maintaining, detrained, or in a deficit — capacity flat or
falling, no lag to correct.

Those are the users hardest to serve, and a correction fitted to one growing
novice would harm them specifically.

## Attempt 4 — the gain schedule (promising, not adopted)

The correct form of the athlete's idea: derive the correction from the data
instead of assuming it. `α_t = max(α, 1/n)` is the running-mean gain — early
observations move the estimate hard, later ones barely at all — and it adapts
automatically. Where capacity is rising it tracks the rise; where flat, it
converges to flat and introduces nothing.

**It improved every aggregate measure.**

| | Before | With gain schedule |
|---|---:|---:|
| Residual MAE | 0.0460 | **0.0425** |
| Residual sd | 0.0578 | **0.0538** |
| Warm-up bias, first 10 observations | +0.0531 | +0.0341 |
| "Above expectation", first 10 | 88.5% | 75.9% |
| Growth-rate dependence of the bias | +0.542 | +0.420 |
| Pooled ablation vs median-of-3 | **baseline wins** | **tie** |

**And it broke three designed behaviours.**

- **Scenario S11 fails.** One conspicuously bad session moves capacity 3.3%
  against a 1% requirement. Early on that is arguably right — with four
  observations there is little evidence to defend — but it means the schedule
  trades warm-up *bias* for warm-up *fragility*, and a new user is exactly who
  suffers from both.
- **Anchor weighting stops working.** `max(rate, 1/n)` overrides the rate
  differences entirely while n is small, so a deliberate anchor test and an
  ordinary set become indistinguishable.
- **Intensity-confidence weighting stops working**, for the same reason.

A formulation that scales the rate rather than replacing it would keep the
distinctions, but choosing it means weighing 7.6% better error against a
threefold loss of early robustness — and that is a judgement the accuracy
metrics alone cannot make.

**Conclusion: this belongs to L3.3 evaluated jointly with L3.7.** The gain
schedule is the right shape of fix and is now the leading candidate, with a
measured benefit and three named costs. What it needs is the robustness suite
sitting beside the accuracy suite, so the trade is made against evidence rather
than against whichever number was looked at last.
