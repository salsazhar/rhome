# Cross-cutting decisions

Decisions that affect more than one stage, recorded here rather than buried in a
single stage entry. Each names the stage it was taken in.

---

## D1 — Named random substreams rather than one sequential generator

**Taken in:** L0.1

A single generator couples every component: adding one draw anywhere shifts all
subsequent numbers, so an unrelated change silently produces a different
dataset. Each component instead derives its own stream by name from the root
seed, and those streams are independent and order-insensitive.

**Consequence for later stages:** every component must take an explicitly passed
`Generator`. Never call `np.random.*` directly — a test rejects it.

---

## D2 — The hidden-data boundary is checked on string literals, not only imports

**Taken in:** L0.1

The engine will read CSV by path, so an import check alone would not catch it
loading ground truth.

**Consequence for later stages:** any new hidden filename introduced in L1.8
must be added to `_HIDDEN_MARKERS` in `rhome_core/architecture.py`, or the
engine could reference it undetected.

---

## D3 — Guardrails are tested against planted violations, not only against a clean tree

**Taken in:** L0.1

A check that has never rejected anything is not known to work. Every guardrail
carries tests that deliberately violate it and require detection.

**Consequence for later stages:** guardrails 2 and 3, when built, must follow
the same pattern — plant a leak, prove it is caught.

---

## D4 — Model parameters are owned by the package that uses them

**Taken in:** L0.2

The registry *machinery* is core infrastructure, but the values are not. The
coefficients in `MODEL.tex` are the inference engine's priors; if the simulator
read them from a shared module it would be an inverse crime routed through
`rhome_core` rather than through an import, and Guardrail 1 would not catch it.

`rhome_core` therefore registers only values genuinely belonging to both sides:
contribution role defaults, the Nuzzo domain, muscle mass weights, the waking
window.

**Consequence for later stages:** L1.1 creates `rhome_sim/parameters.py` and
L2.1 creates `rhome_engine/parameters.py`, each its own namespace. The
document-verification test generalises to iterate over all three registries.

---

## D5 — Specification values are verified against the cited section, not the document

**Taken in:** L0.2

The first implementation of Guardrail 3 searched whole documents, and a planted
drift of 0.50 → 0.55 passed because 0.55 occurs elsewhere in `MODEL.tex`. A
guardrail that cannot fail is worse than none, because it provides assurance
over exactly the errors it is meant to catch.

Verification is now scoped to the cited section, including nested subsections
and the heading itself.

**Consequence for later stages:** every registered parameter must cite a
section precise enough to contain its value. A vague section reference will now
fail loudly rather than pass vacuously.

---

## D6 — Load invariance has a bounded cost at the point of coefficient derivation

**Taken in:** L0.3

The dose channels deliberately cannot see absolute load. That is correct for
fatigue modelling, but it removes the one variable that would distinguish a
bodyweight back extension from a loaded deadlift when *deriving* coefficients
for a user-created exercise, since both are hinges.

The cost is bounded: it affects user-created lightly loaded supported movements
only, and the curated library is unaffected.

**Consequence for later stages:** a `torso_supported` descriptor is the deferred
remedy. Revisit if L3 residuals show systematic error on supported movements,
or once the library is large enough that adding the field is not overfitting.

---

## D7 — Review artefacts render the source data, never restate it

**Taken in:** L0.3

The exercise-library review page is generated from the same CSV the engine
loads. A hand-maintained page would eventually disagree with the data and be
believed anyway, because it is the thing a human actually reads.

**Consequence for later stages:** every checkpoint visual pack is generated
from the artefacts it describes. No checkpoint material is written by hand.

---

## D8 — Simulator invention is not registered as specification

**Taken in:** L1.1

The parameter registry exists to keep code and documents in agreement. Values
the documents never state do not belong in it: registering Athlete A's leg-press
starting capacity against `DATA.md` §10 would imply the specification commits to
a number it never mentions, and would weaken the registry's meaning for the
values that genuinely are specified.

Documented values are registered and verified. Simulator design constants live
in clearly labelled module tables.

**Consequence for later stages:** when adding a simulator constant, ask whether
a document states it. If not, it is the simulator's invention and stays out of
the registry.

---

## D9 — The athlete's real data is a sealed holdout

**Taken in:** L1.2 (planning)

The athlete has roughly 99 recorded sessions with matching Oura history. This is
the only genuinely independent test the project will get, and there is exactly
one of it.

It is therefore frozen before L2 begins and read by nothing — no tooling, no
inspection, no "quick look at the format" — until L3.9. Data seen during
development is data tuned against, regardless of intent, and the resulting
claim that the engine works on real data would be worth far less than it
appears.

**Consequence for later stages:** the engine's ingestion layer is designed
against the documented schema, not against the real export. If the real export
turns out to need a format shim, that shim is written at L3.9 and its authoring
is recorded, because writing it requires looking at the file.

---

## D10 — Disable bytecode caching in any sweep that edits and re-imports

**Taken in:** L1.3

Python invalidates cached bytecode by source mtime at one-second granularity. A
parameter sweep that rewrites a module and re-imports it within the same second
silently runs the previous version. This has now produced two false readings: a
guardrail demonstration in L0.2 that appeared not to revert, and a coefficient
sweep in L1.3 that returned identical results for four different values.

**Consequence for later stages:** export `PYTHONDONTWRITEBYTECODE=1` for any
calibration sweep or edit-and-rerun loop. Test runs under pytest are unaffected.

---

## D11 — Optimisers need domain bounds, or they distort what the objective ignores

**Taken in:** L1.4

Tuning the session templates by hand across five interacting constraints
oscillated without progress, so a hill-climber was used instead. It satisfied
every metric by prescribing six sets of calf raises, five of hip adduction and
a single set of rows — numerically optimal, and a programme no coach would
write.

Bounding set counts by exercise type (compounds 2–5, isolation 2–4) produced a
solution that satisfies the metrics and reads as real training.

**Consequence for later stages:** any fitting or calibration step must state
its plausibility constraints explicitly. Whatever the objective does not
constrain, the optimiser is free to destroy.

---

## D12 — Ablate before tuning

**Taken in:** L1.4

Upper/lower parity resisted several rounds of targeted fixes. Ablating each
stochastic element in turn — substitutions off, misses off, both off — showed
in one table that misses were the entire cause and substitutions were
irrelevant. The preceding fixes had been aimed at the wrong mechanism.

**Consequence for later stages:** when a metric resists repeated fixes, stop
fixing and ablate. Identify the mechanism before changing it.

---

## D13 — Whatever influences the simulation must be recorded by the component that applies it

**Taken in:** L1.6

The PR-window recovery bonus was applied in the runner, after the recovery
model had already recorded the day's propensity. The physiology evolved with
one value while the hidden ground-truth table carried another.

The behaviour was correct; only the record was wrong, which is the harder case
to notice. Since the hidden tables are what L3 scores the engine against, a
latent value disagreeing with the state it generated would have made every
evaluation of recovery quality subtly wrong — and looked like engine error
rather than data error.

**Consequence for later stages:** never adjust a latent quantity downstream of
its own record. Pass the adjustment into the component that computes it.

---

## D14 — The build log is self-checking

**Taken in:** L0.4

Checkpoint 0 was recorded as passed while L0.4 had never been built. The
checkpoint reviewed the artefacts it expected to see and never asked whether
its own layer's stages were complete. Layer 1 did not notice, because the
simulator correctly uses its own relative-intensity curve; the omission
surfaced only when L2.1 first needed the engine-side one.

A checkpoint that can pass over an unbuilt stage is not a gate.

`tests/test_build_log_integrity.py` now parses the index and fails if a
checkpoint is marked passed while any preceding stage is incomplete, if a
completed stage has no build-log entry, or if an entry has no index row.

**Consequence for later stages:** the index is now load-bearing rather than
decorative. Marking a stage complete without writing its entry fails the suite.

---

## D15 — A guardrail must be shown to cover everything it claims

**Taken in:** L2.6

Guardrail 3 verified 13 core parameters and had never seen the 86 engine
parameters registered since L2.1. It was scoped correctly and pointed at one of
two registries, and it reported green for five stages.

This is the second time this guardrail has been found decorative. At L0.2 it
searched whole documents and passed on a coincidental match. Both failures
share a shape: the check was correct on the cases it examined, and silent about
the cases it never reached.

The registry tests now iterate `(*CORE_PARAMETERS, *ENGINE_PARAMETERS)`. That
fixes this instance, not the class.

**Consequence for later stages:** every guardrail test must assert its own
scope — how many things it checked, not only that the things it checked passed.
A guardrail that cannot say what it covered is a guardrail that cannot be
trusted to cover anything.

---

## D16 — Sixteen model groups survive the larger library

**Taken in:** L2.6 → L3.9

The athlete-authored library uses twelve muscle labels the model taxonomy does
not have. Three are our own display labels in a different spelling. The rest
resolve as:

| Library label | Model group | Note |
|---|---|---|
| `core`, `deep_core` | `abs` | 868 uses, stabiliser in nearly all |
| `traps` | `upper_back` | display already maps "Trapezius" here |
| `serratus` | `upper_back` | scapular control |
| `rotator_cuff` | `posterior_delts` | 466 uses, 13 as primary |
| `hip_flexors` | `quads` | rectus femoris is both |
| `neck` | `upper_back` | 16 exercises, all primary |
| `tibialis` | `calves` | 8 exercises, all primary |
| `foot_ankle_stabilisers` | `calves` | stabiliser only |

The alternative was adding groups. It was rejected for the reason that settled
the single `abs` group: the sixteen exist because evidence is reported at that
resolution, and a seventeenth would be pure Grade C — a dimension the research
specification can say nothing about, added because a label existed.

The finer labels are not lost. They live in the display layer, which is what
the two-level taxonomy was built for.

**The cost, stated plainly:** neck work reads as upper-back fatigue and
tibialis work as calf fatigue. Both are low-volume and low-systemic, so the
error is small, but it is an error and not a modelling choice that could be
defended on physiology.

**Consequence for later stages:** L3.9 implements the mapping and must make the
display lookup insensitive to slug-versus-label spelling, which resolves three
of the twelve without any mapping at all.

---

## D17 — Guardrail 3 is checked in both directions

**Taken in:** L2.7

Building the trace's parameter block by scanning source found five parameters
whose registered value was verified against the documents, matched, and was
never read by the arithmetic. `stimulus_secondary_coeff` is the clearest: the
registry said 0.50, `MODEL.tex` said 0.50, the test compared the two and
passed, and `Exercise` used a dataclass field default of 0.50 that nothing
checked.

This is the third distinct failure of this guardrail — a whole-document search
at L0.2, one of two registries at L2.6, and now values nothing reads. The
pattern across all three is the same: the check was sound on what it examined
and silent about what it never reached.

Verification now runs both ways. `parameter_reads()` collects every registered
name the source actually reads, and every registered parameter must appear.

A related case is worth naming separately: `stimulus_stabiliser_coeff = 0.00`
was implemented by *omitting* stabilisers from the stimulus vector. The
behaviour was right and the value was unfalsifiable — nothing could ever
disagree with it. Zero-valued parameters are now applied rather than encoded
structurally.

**Consequence for later stages:** a parameter is only registered if it is read.
Expressing a value through the shape of the code instead of through the
registry puts it beyond every check this project has.

---

## D18 — Unrated working sets are imputed, not discarded

**Taken in:** Layer 2 audit

A working set logged with neither RPE nor RIR cannot be transformed, and the
engine discarded it. The Layer 2 audit found the consequence: on a day that
lost three of fifteen working sets, confidence read *higher* than either
neighbour, because a set with no dose has no weight in dose quality and the day
looked like a shorter session that was well recorded.

Two errors compounded. The fatigue was real and the model forgot it, which
biases every state toward optimism — the more harmful direction here. And the
confidence system, whose entire purpose is to report evidence sufficiency,
reported more confidence for less evidence.

The distinction against the missed-session rule is the substance of this
decision. Not training is informative about fatigue and confidence must hold
(`DATA.md` §19.5). Training without recording is the opposite: the work
happened and the model does not know. The two are near-identical in the data
and require opposite answers, which is why the first was specified and the
second was missed.

v0 imputes the reserve from the athlete's own recent history for that exercise,
then their general habit, then a prior of 2. The set carries `low` intensity
confidence so it drags dose quality down, and it is **never** eligible for
performance estimation.

**Consequence for later stages:** imputing a dose and inventing a performance
observation are separate acts and only the first is defensible. Any later
imputation must state which side of that line it falls on. Residuals were
unchanged by this fix (+0.0124 → +0.0119), which is the evidence the boundary
held.

---

## D19 — A plausible explanation is not a check

**Taken in:** L3.1

Every latent-state correlation reported at L2.5, in the Layer 2 audit and at
Checkpoint 2 was computed on a mis-aligned pairing: the engine's day-N state is
the close of day N, the simulator's is on waking, sixteen hours and one session
earlier. Local fatigue read +0.450 where it is +0.949; systemic +0.388 where it
is +0.973.

The number survived a stage report, a 46-check audit and a checkpoint gate. It
survived because I attached a reason to it: that a modest correlation was
expected, since the inverse-crime audit shows the engine's single exponential
cannot represent the simulator's two-component recovery, and that a correlation
near 1 would indicate an inverse crime rather than success.

Every clause of that is true about the model. It was explaining an artefact.

What eventually caught it was a metric that could not be explained away.
Directional accuracy came out at 43% — below chance — and no misspecification
makes a model worse than guessing. The check that worked was the one with no
available excuse.

**Consequence for later stages:** when a measured value is lower than hoped and
a reason is available, the reason is a hypothesis, not a resolution. Report a
second metric whose failure mode differs, and prefer metrics with a hard floor
— chance, zero, sum-to-one — because a value that crosses an impossible
boundary cannot be rationalised.


---

## D20 — No score is reported without a trivial predictor beside it

**Taken in:** L3.1 re-audit

Twice now, a headline number has been reported with no reference point and
meant something different from what it appeared to mean.

At Checkpoint 2 the engine's residual read as unbiased and passed every
threshold; a median-of-the-last-three baseline beat it. At L3.1 the corrected
latent correlations read +0.949 to +0.973; a single accumulator counting
working sets — no exercise, no repetitions, no effort, no muscles, no recovery
context — scores +0.911 to +0.945 on the same series.

Both times the number was accurate. Both times it was uninformative, because
nothing said what an absence of modelling would have achieved.

The mechanism is the same in both cases: predictor and target are driven by the
same training log, so agreement is largely free. It will recur wherever that is
true, which is everywhere in this project.

So the baselines live in the harness rather than being produced when someone
asks. `rhome_eval.baselines` covers performance, `rhome_eval.state_baselines`
covers latent state, and tests fail if an aggregate advantage is quietly
reported as though it were the whole result.

**Consequence for later stages:** every metric in `DATA.md` §19 needs its
trivial competitor identified before the metric is reported, not after. Where
one cannot be constructed, that is worth saying too — a score with no possible
baseline is usually a score measuring something other than skill.

---

## D21 — The calibration bands do not gate L5.3, and the choice is made before the number is known

**Taken in:** L3 audit, by the athlete

`DATA.md` §19.4 fixes six bands the engine's suppression must fall inside. The
Layer 3 audit measured both sides of them for the first time:

| case | engine | simulator | band |
|---|---:|---:|---|
| fresh, after a deload week | 1.36% | 1.07% | 0–1.5% ✅ |
| one ordinary hard session | 5.87% | 6.00% | 4–6% ✅ |
| one failure-heavy session | 7.51% ⚠️ | 9.26% ❌ | 5–7% |
| ordinary training week | 7.34% | 8.18% ❌ | 6–8% |
| within a failure-heavy block | 9.37% | 13.16% ❌ | 8–10% |
| peak of an overload block | 14.97% | **25.67%** ❌ | 13–16% |

The engine is in band five times of six. The **simulator** — the thing the
engine is supposed to be reconstructing — is in band twice. The bands were
derived from the engine's own λ coefficients, so "five of six" is substantially
the engine agreeing with a target built from the engine.

**The problem this creates for L5.3.** LIM-2 records that the engine
accumulates fatigue linearly and should not. Fixing it moves the engine *toward*
the simulator, and therefore *out of* these bands. A correct improvement will
present as a failed acceptance criterion.

**The decision.** The bands do not gate L5.3. L5.3 is gated on its own four
criteria, already written in `BUILD_PLAN.md`: the L3.4 contrast ratios move
toward 1.0, one-step-ahead MAE does not worsen on the settled ablation, the
trace's shares still sum to one, and S11 robustness is unaffected. Suppression
leaving a §19.4 band during L5.3 is an expected consequence, not a regression,
and does not by itself fail the stage.

**Why this is written now rather than then.** §19.4 does not say the bands may
be adjusted. It says the opposite:

> If the engine's suppression is systematically outside these bands, the λ
> coefficients are re-derived and `MODEL.tex` is versioned — the bands are not
> quietly widened to fit.

Adjusting them is therefore a *departure* from the specification, not an
application of it, and it needs an argument. Made after seeing a 22% figure
against a 13–16% band it is indistinguishable from fudging, however sound the
reasoning. Made in advance, with the number unknown, it is a pre-registration.
That difference is the entire value of this decision and the only reason it is
being recorded at a moment when nothing has changed.

**The three options, named in advance.** When L5.3 moves the engine out of
band, exactly one of these is chosen, with its reason stated in the L5.3 entry
*before* the new suppression figures are read:

1. **Re-derive λ and version `MODEL.tex`** — §19.4's own remedy. Correct if the
   bands are believed and the engine has genuinely mis-shot them.
2. **Revise the bands, and version `DATA.md`** — correct if the bands are held
   to have been calibrated to a linear engine and to have inherited its
   limitation. This is the option the athlete considers most likely, and it is
   permitted here *because it is being permitted in advance*.
3. **Question the simulator.** Recorded because nobody has raised it and it is
   not obviously wrong.

**The third option, stated properly.** The simulator's non-linearity constants
— state-dependent amplification, the volume-by-failure interaction — are D8
simulator invention. They are not in the parameter registry, carry no evidence
grade, cite no section, and have never been checked against anything. 25.67%
suppression at an overload peak has no more warrant behind it than 15% does.
LIM-2 treats the simulator as the truth the engine falls short of; that is an
assumption, and this is the first decision to say so out loud.

`PRODUCT.md` §15.2 already contains the reason it cannot be settled here:
simulator and engine "were written from the same literature by the same hands"
and "share their author's blind spots". Neither figure has been compared to a
human. This is a Grade C question at every level, and L3.12 — the real cold run
— is the first evidence that could bear on it.

**Consequence for later stages:** whoever builds L5.3 reads this decision
first, states which of the three options they are taking and why, and only then
runs the calibration. LIM-8's single missed band is re-read at the same time and
under the same choice, not separately. And no §19.4 figure is quoted anywhere
again without the simulator's column beside it — the engine's number alone was
never the comparison the section asks for.

**Choice taken before the repair calibration, 24 August 2026:** option 2. The
athlete approved revising and versioning the bands in `DATA.md`. The present
bands were derived from the linear engine's own $\lambda$ coefficients and the
simulator already falls outside four of six; preserving them would reward the
limitation L5.3 exists to remove. No post-repair calibration figure had been
read when this choice was recorded. The replacement bands must be reported
with the simulator column and labelled Grade C rather than presented as human
physiology.

---

## D22 — The real data becomes a development set, and the exam becomes prospective

**Taken in:** after L3.12

The seal on `data/real/` protected exactly one thing: the engine's first contact
with data it could not have been tuned against. That contact happened, the
result is recorded in `L3.12_real_cold_run.md`, and the engine failed the severe
criterion. The seal's purpose is discharged.

Holding it shut now protects nothing. It only stops the athlete examining their
own training, and stops the diagnosis that failure demands. So the data is
opened, exported to readable form, and reclassified.

**What this costs, stated rather than glossed.** `BUILD_PLAN.md` L3.12 is
explicit: *"any subsequent fix must be reported as having consumed the real
holdout."* Every number measured on this data from here is a development number.
No fix validated against it may be reported as validated on held-out data,
however tempting the phrasing, and the L3.12 result is the last clean
measurement this export will ever yield.

**What replaces it, and why this is not a loss.** `CLAUDE.md` already commits to
the answer: *"Real-data validation is prospective. The recurring exam is
everything logged after a model version was frozen, which cannot have been
fitted to."* A frozen version plus forward logging produces a fresh holdout
every week, and at roughly five sessions a week the athlete generates more
settled observations in three months than this entire historical export
contains. The one-shot resource was always a bridge to that regime, not a
substitute for it.

**Consequence for later stages.** Every model version now needs a freeze date
and a commit, recorded before it sees new data. Every evaluation states which
sessions postdate the freeze. A version evaluated only on sessions that predate
its own freeze has been evaluated on its training set, and must say so.

**What survives unchanged.** The originals are not touched.
`data/real_manifest.json` still checksums them and `data/real_openings.json`
still records every opening — provenance matters *more* after this transition,
not less, because being able to prove which bytes produced the L3.12 result is
what keeps that result meaningful once everything after it is development work.
The export in `data/real_export/` is derived, regenerable, and never
authoritative.

---

## D23 — Accuracy cannot buy fragility

**Taken in:** L3.13, by the athlete before estimator repair

The real development log exposed an incomplete comparison. v0's capacity
estimator loses badly on accuracy while limiting one settled four-set session
to roughly 2.4% movement. `last observation` wins the accuracy ladder by
adopting the most recent session in full. A rate/clip pair fitted to the log
closes most of the accuracy gap but permits one four-set session to move
capacity 52.2%.

A weighted accuracy--stability score would only hide the product judgement in
an arbitrary exchange rate. The gate is therefore lexicographic. A candidate
first has to be no less stable than frozen v0 on the pre-registered S11 battery:
median immediate displacement at most 2.1%, worst at most 3.3%, and worst
ninety-day residue below 0.5%. Only passing candidates may be ranked by matched
one-step-ahead MAE, with the D20 baselines beside them.

These limits are not evidence that 2.1% is physiologically special. They make
`PRODUCT.md`'s phrase "barely moves capacity" operational by freezing the
stability the product already had before accuracy tuning began. They also keep
the decision independent of the candidate: no repair result existed when the
athlete approved them.

**Consequence for later stages:** the estimator needs two time scales or an
equivalent session-level mechanism. Per-set rate and clip may become responsive
only if cumulative session influence remains inside the frozen gate. A model
that improves MAE and fails S11 is ineligible, not a trade-off winner.

---

## D23 — A trivial competitor is given every structure the engine is not claiming credit for

**Taken in:** L3.17

D20 required *a* trivial competitor. It did not require a competent one, and
that gap held a headline number up for two stages.

The per-muscle latent claim was reported as **+0.966 for the engine against
+0.520 for a decaying set counter** — a 0.446 advantage, and the single most
quoted result in the project. The counter in that comparison was one global
accumulator with no muscle attribution at all, compared against each muscle in
turn. `state_baselines.py` said so in its own docstring and drew the conclusion
that a counter "cannot attribute".

It cannot *infer* an attribution. It does not have to. The exercise-to-muscle
map is authored data sitting in `exercise_library_v1_2.csv`, and handing it to
a counter costs nothing. Given `c^F` and nothing else — no repetitions, no
effort, no proximity to failure, no novelty, no wearables, no recovery
multiplier, no within-session anything — a decaying counter scores:

| | longitudinal | cross-sectional | per-day cross-sectional |
|---|---:|---:|---:|
| engine | +0.965 | +0.941 | +0.928 |
| c_F-weighted counter | **+0.955** | **+0.934** | **+0.929** |
| primary-muscle counter | +0.902 | +0.857 | +0.843 |

So the engine's per-muscle advantage is **+0.010**, not +0.446, and on the
per-day cross-sectional measure the counter is marginally ahead. The +0.520
was measuring the absence of a lookup table, not the presence of a model.

**The rule.** A trivial competitor is given every structure the engine is not
claiming credit for. The engine claims to infer fatigue physiology from a
training log; it does not claim to have authored the muscle map, the exercise
library or the taxonomy. Those go to the competitor. What the engine must earn
is whatever remains — here, whatever the map plus one exponential cannot
already do.

**How to tell which structure is which.** Ask what the stage's build-log entry
claims as its achievement. Anything the project *wrote down* rather than
*worked out* belongs to the baseline. If the answer is unclear, give it to the
baseline: an advantage that survives an over-generous competitor is real, and
one that only survives a weak competitor was never measurable.

**Consequence for later stages.** Every per-muscle, per-exercise or per-context
figure needs a competitor sharing that same structure before it is reported.
`rhome_eval.state_baselines.MUSCLE_BASELINES` supplies it for latent state.
Ranking and calibration had no competitor of any kind until this stage; both
now carry one.

This does not retract the engine. It retracts the *comparison*. What the engine
buys over a competent competitor is now an open question with a measured
answer, and the answer is small enough to reshape what is worth building next.
