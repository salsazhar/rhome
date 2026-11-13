# Checkpoint 2 — Layer 2 complete

**Date:** 23 August 2026
**Status:** ✅ Passed as a completeness gate — proceed to Layer 3
**Performance:** not yet demonstrated. See *The ablation this gate should have run* below.
**Dataset:** v0.1.0, seed 20260822 · development window only, days 0–519

---

## What was reviewed

| Item | Where |
|---|---|
| Visual pack: state, confidence, one trace, performance | [`build_log/checkpoint2/`](checkpoint2/) |
| `daily_state.csv`, `performance_observations.csv`, `trace_example.csv`, `projection.csv` | same directory |
| Layer 2 audit, 46 checks | [`LAYER2_AUDIT.md`](LAYER2_AUDIT.md) |
| Stage entries L2.1 – L2.8 | [`INDEX.md`](INDEX.md) |

**Nothing in this pack reads the simulator's hidden files.** It shows what the
engine produces from what an athlete would actually give it. Comparison against
latent truth is Layer 3's work and is deliberately not previewed here.

## State at the gate

- **749 tests passing**, 77 of 77 specification clauses covered
- **46 of 46 audit checks passing**, measured from a fresh engine run
- **All five guardrails live**, each demonstrated rejecting a planted violation
- **520 days processed**: 358 sessions, 7 448 sets, 2 087 projections sealed
  before their sessions, 2 083 scored, 9 347 explanation traces
- The athlete's own export is **sealed and unread**, verified by checksum

## What the pack shows

**`01_state_over_time.png`** — ninety days at full resolution, the whole window
as weekly means, and the recovery multiplier. The detail panel shows the
sawtooth the model is for: fatigue rising within a session and decaying between
them, at different rates per muscle group. The weekly panel shows training
blocks and the deloads between them without being asked to.

**`02_confidence.png`** — confidence with the three display bands, and what
holds it down each day. The opening 41 days are bound by baseline maturity, as
the specification requires; afterwards the binding reason tracks real events.

**`03_one_day_explained.png`** — calf fatigue on day 508 decomposed into 121
contributors whose shares sum to 1.000000. Two sets from that day account for
82%; sets from 78 and 174 hours earlier and two days of background walking make
up most of the rest. Twenty-five of the thirty parameters behind the number are
Grade C, which is the disclosure working rather than a problem.

**`04_performance.png`** — capacity for the four main lifts, the residual
distribution, and the residual bias over time.

## What this gate found

### The pooled residual conceals a drift

The engine's one-step-ahead residual over the whole window is **+0.0119**,
which reads as approximately unbiased and passes every threshold it is tested
against. Split by period it is not:

| Days | n | Mean log residual |
|---|---:|---:|
| 0–99 | 353 | **+0.0508** |
| 100–199 | 416 | +0.0347 |
| 200–299 | 420 | +0.0036 |
| 300–399 | 407 | −0.0065 |
| 400–499 | 404 | −0.0130 |
| 500–519 | 83 | −0.0144 |

The engine under-predicts by five per cent in the first hundred days and
over-predicts by one and a half per cent in the last. A single number that
looks unbiased turns out to be two opposite biases meeting in the middle.

The opening bias has an explanation: capacity initialises from the median of an
exercise's first three observations and then has to climb, so early projections
sit below what the athlete does. That is a warm-up cost and it is expected to
be temporary. The later negative drift is **not** explained, and it is the more
concerning of the two because it is the steady state.

Two candidates, and they are distinguishable:

1. The Huber clip bounds each set's influence, so the estimate lags any
   sustained change. Where the athlete's logged loads plateau, a lagging
   estimate would sit slightly *above* what they can now do.
2. The fatigue-suppression term λ is mis-scaled, so the projection subtracts
   too little fatigue as training density rises.

`L3.3` is where this is settled. It is recorded here rather than fixed because
diagnosing it needs the latent comparison Layer 3 exists to do, and guessing
now would mean tuning a parameter against the development window.

**This does not block the gate.** The drift is under 1.5% and every stage-level
threshold holds. It is recorded because a checkpoint that reports the pooled
mean and moves on is a checkpoint that has not looked.

### The ablation this gate should have run

`PRODUCT.md` §15 specifies an ablation ladder, and I reported the engine's
residual without one. Asked directly whether this checkpoint shows strong
performance, the honest answer needed the comparison, so here it is — the same
2 083 scored sets, matched to a sample where every predictor is defined
(n = 2 002).

| Predictor | sd | MAE |
|---|---:|---:|
| Engine — capacity × fatigue | 0.0575 | 0.0455 |
| Engine capacity, fatigue term removed | 0.0587 | 0.0493 |
| Baseline — last time on this exercise | 0.0634 | 0.0491 |
| **Baseline — median of the last 3 sets** | **0.0554** | **0.0434** |

**A three-line baseline with no fatigue model, no wearable input and no dose
channels beats the engine by 4.8% on mean absolute error**, and the paired
difference is outside its own confidence interval. The entire four-channel
fatigue apparatus earns 1.6% on residual spread over bare capacity.

That is the result, and it is not what a completed inference engine is supposed
to produce.

**But the reason is specific, and it is the drift.** Split by period, the
engine wins everywhere after the opening block:

| Days | Engine sd | Median-3 sd |
|---|---:|---:|
| 0–129 | 0.0619 | 0.0611 |
| 130–259 | 0.0530 | 0.0552 |
| 260–389 | 0.0487 | 0.0527 |
| 390–519 | 0.0477 | 0.0522 |

Winning in every late period while losing overall is only possible if something
is moving between the periods — and that something is the engine's own slow
bias. Removing each predictor's drift and comparing what is left:

| | sd | MAE | Variance from slow bias |
|---|---:|---:|---:|
| Engine | 0.0525 | 0.0414 | 0.000550 |
| Median-3 | 0.0550 | 0.0429 | 0.000040 |

**Once its drift is removed the engine wins by 3.4%.** Its slow bias
contributes fourteen times more variance than the baseline's, and that alone
converts a genuine advantage into a loss.

So the fatigue model *is* doing real work — it discriminates better than a
recency baseline, by more as capacity settles. A systematic bias the model has
not captured is spending the entire gain and more.

This upgrades the residual drift from an open question to **the single thing
standing between this engine and demonstrable value**, and it makes L3.3 the
stage that decides whether the project's central premise holds.

It is still not fixed here, for the reason given above: telling the Huber lag
apart from a mis-scaled λ needs the latent comparison, and `rhome_eval` does
not exist yet. Guessing between them and adjusting a coefficient would be
tuning a parameter to make a number look better, which is the failure this
whole build has been arranged to avoid.

### The recovery multiplier spends an eighth of its time clipped

ρ sits exactly on a clip bound on **62 of 520 days — 11.9%**: 28 at the floor of
0.80, 34 at the ceiling of 1.15, with runs of up to seven consecutive days.

This is not a defect. The inverse-crime audit records that true recovery
propensity spans [0.68, 1.28] while the engine clips to [0.80, 1.15], so
clipping at the extremes is the engine correctly declining to extrapolate. But
one day in eight is more than "at the extremes", and on a clipped day the
multiplier carries no information about *how* favourable the context is.

`L3.2` should measure what this costs. If the clipped days are the ones that
matter — hard blocks, poor sleep runs — the bounds may be too tight.

## Decisions taken during Layer 2

Four are worth restating at the gate; all are in `DECISIONS.md`.

**D15 and D17 — Guardrail 3 was found ineffective twice more.** It covered one
of two parameter registries, and it verified values that no computation read.
Neither had caused a wrong number, and both would have hidden one. Verification
now runs in both directions across all 98 parameters.

**D16 — sixteen model muscle groups survive the larger library.** The twelve
labels in the athlete's 1 074-exercise library that fall outside the taxonomy
fold into existing groups rather than adding dimensions the research
specification cannot speak to. The cost — neck work reading as upper-back
fatigue — is stated rather than smoothed over.

**D18 — unrated working sets are imputed, not discarded.** Found by the Layer 2
audit: a day that lost three of fifteen working sets to missing effort ratings
reported *higher* confidence than its neighbours. The fatigue was real and the
model forgot it, and the system whose job is to report evidence sufficiency
reported more confidence for less evidence.

## Corrected after the fact — L3.1

**Every latent-state correlation this gate reported was computed on a
mis-aligned pairing.** The engine's day-N state is captured at the close of day
N; the simulator records its latent state *on waking*, before that day's
training. Comparing them index for index compares states sixteen hours and one
session apart.

| Channel | Reported here | Actual |
|---|---:|---:|
| Local fatigue | +0.450 | **+0.949** |
| Neuromuscular | — | **+0.956** |
| Systemic | +0.388 | **+0.973** |
| Directional accuracy | 43% | **95%** |

Per model muscle group the correlations run +0.956 to +0.981.

The tell was directional accuracy at 43% — *below* chance, which no
misspecification produces and which nothing at this gate was measuring. It took
building the evaluation harness to surface it.

Worth recording plainly: the wrong numbers came with a confident explanation
attached. I wrote that the modest correlations were "modest by design", citing
the inverse-crime audit's finding that the engine's single exponential cannot
represent the simulator's two-component recovery. That is a true statement about
the model and it was being used to explain an artefact. A plausible reason for a
wrong number is worse than no reason, because it stops the number being
questioned.

## Open items carried into Layer 3

1. **Residual drift, now the priority.** It is not a cosmetic bias: it is
   spending the engine's entire measured advantage over a trivial baseline.
   `L3.3`, which must run the full ablation ladder as a gate rather than as a
   report.
2. **ρ clipping at 11.9% of days.** `L3.2`.
3. **Confidence reads `high` on 498 of 520 days.** Defensible on clean
   synthetic data with near-complete wearables, but an index that is almost
   always high is close to not being an index. `L3.12` is the real test.
4. **Capacity error averages 8.5%** across all 27 exercises against a 10%
   threshold, pulled up by the isolation movements. Not in danger, not
   comfortable.
