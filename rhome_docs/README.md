# Rhome Project Documentation

**Documentation version:** 0.4  
**Date:** 22 August 2026

This directory is the source-of-truth documentation for the Rhome v0 model-build phase.

## Read order

1. `PRODUCT.md` — product purpose, scope, user-facing concepts and architecture.
2. `RESEARCH.md` — scientific evidence, parameter provenance, citations and claim boundaries.
3. `MODEL.tex` — mathematical specification for the v0 inference engine.
4. `DATA.md` — two-year Athlete A synthetic-data generator, schemas, scenarios and evaluation protocol.

## Document versions

| Document | Version |
|---|---|
| `PRODUCT.md` | 0.4 |
| `RESEARCH.md` | 0.4 |
| `MODEL.tex` | 0.4 |
| `DATA.md` | 0.6.0 (document); dataset version 0.1.0 generated |

`DATA.md` carries two version numbers. The document version tracks the specification; the dataset version tracks a generated artefact and follows the scheme in `DATA.md` §21.

## Implementation rule

Code should not silently diverge from these documents. If a model parameter or data-generation rule changes materially, update the relevant document and increment its version.

The simulator and inference engine must remain separate. Simulator-only latent states and scenario labels are never application inputs.

## Changelog

### 0.5 — 23 August 2026

Two additions, both arising from questions about how a model built on synthetic data becomes a model that works on a real person.

**The autonomic expectation is now conditioned on recent training** (`MODEL.tex` §Conditioning the autonomic expectation, `RESEARCH.md` §12.2).

- A rolling personal baseline answers "is this reading unusual for you?" It cannot answer "is this unusual *given what you did yesterday?*" — so the previous model treated a depressed RMSSD after a heavy squat session and a depressed RMSSD on a rest day as identical evidence. They are not.
- The recovery multiplier now uses the **residual** after subtracting what recent systemic load predicts, with modest Grade C coefficients.
- **The expectation is not a forecast and Rhome does not predict wearable data.** Its accuracy is not the object: it exists to partition a reading into the part training explains and the part it does not. Autonomic variance is dominated by influences outside training, and a model scored on predicting HRV would be scored chiefly on predicting things unrelated to training — creating pressure to model life events in pursuit of a number no athlete wants.
- Persistent unexplained deviation now reduces confidence through a new component, rather than silently moving the recovery multiplier as though the surprise were understood.
- The athlete-facing form is explanation, never forecast: "below baseline, expected after Thursday's session" rather than "tomorrow will be 58 ms".

**`PRODUCT.md` §15 records the validation logic**, previously spread across three documents and one head.

- The synthetic dataset is a test harness with an answer key, not training data. Nothing in the engine is learned from it.
- What synthetic data can establish (identifiability, absence of leakage, behavioural correctness, robustness) and what it cannot — including that the simulator and engine share their author's blind spots, so anything real that neither contains is invisible to synthetic evaluation.
- Which observables are scoreable on a real person: load and effort are produced by the training system and are predicted; wearables are produced largely by life and are consumed only.
- An ablation ladder committed to **before** real data is opened, so a disappointing result cannot be rationalised afterwards. Any component that does not beat its ablation is removed rather than defended.

### 0.4 — 22 August 2026

`DATA.md` only. Two distribution sections were specified before the generator existed, and generating the data showed both to be inconsistent with the specification's own assumptions. Both are now set from measurement across eight seeds.

**§9.2 — effort now specifies two distributions, not one**

- Effort is recorded as **whole-number repetitions in reserve**, matching the athlete's logger. Granularity turned out to matter: the RPE 9.5–10 band spans 0 to 0.5 RIR, so half-point logging puts two reportable values in it against one for whole numbers. Under half-points the estimation-error tail piled onto RPE 10 hard enough to make "maximal" the most common entry in the log, which no real training record resembles.
- The section now gives **true effort** and **logged effort** separately, because they differ materially. An athlete training almost entirely at 1–2 RIR produces a log spanning 0–4, since their estimate of proximity to failure is only accurate to about one repetition.
- The original single set of bands could only have been met on logged values if the athlete trained every working set at almost identical proximity to failure — contradicting §8, which prescribes heavy triples alongside isolation near failure. The original figures survive as the true-effort column.
- Added the consequence the engine needs: **the smearing is irreversible at the level of a single set**, so no engine can recover true effort from the log. That is a floor on how well relative intensity can ever be estimated.

**§9.1 — repetition bands widened at the low end**

- 1–3 repetitions moves from 5–8% to 10–15%. Only ~6% of sets are *prescribed* there; the rest are later sets of 4–6 prescriptions falling short under within-session fatigue. A four-set prescription records 6, 5, 4, 3 and the last set lands a band lower.
- Repetition count carries no observation error, so these figures describe the training itself. The previous range implicitly assumed no drop-off across sets, or a load light enough to prevent it. Both would misrepresent how the athlete trains.

**§5.3 — RIR is the primary logged field**, with RPE derived, reversing the previous convention.

### 0.3 — 22 August 2026

Exercise-library architecture, settled before L0.2 builds against the schema. The question behind this pass was whether a library of 23 exercises could later become hundreds plus user-created ones without rework. Adding exercises turns out to be free; the muscle taxonomy and the exercise schema are not, so they are fixed now.

**Muscle taxonomy — two levels**

- **16 model groups**, the previous 15 plus `abs`, which was missing entirely along with any direct core work in the exercise pool.
- A finer **display taxonomy** (Upper/Mid/Lower Chest, Trapezius, Obliques, Grip, Hip Abductors…) maps many-to-one onto them. Athletes log at the granularity they think in; the model claims only what the evidence supports.
- The reasoning is a claim boundary, not a simplification: the evidence this model rests on is reported per muscle group, and nothing in it licenses treating upper-chest fatigue as a state distinct from lower-chest fatigue.
- `abs` is one group. Splitting it from `obliques` is recorded as the most likely future refinement, to be driven by engine residuals rather than anatomical intuition.

**Exercise kinds**

- New `exercise_kind` field covering all seven measurement forms a logger must accept. `weighted_reps`, `reps_only` and `assisted_reps` are fully supported; time- and distance-based kinds are recorded but excluded from the dose model, exactly as warm-up sets already are, because the relative-intensity mapping is *defined* on repetitions. Recording the field now avoids a schema migration later.

**Curated and derived coefficients**

- The exercise database is explicitly two-layered: a commodity **base layer** (name, pattern, equipment, muscle tags) and Rhome's own **scoring layer** (contribution weights, compoundness, systemic cost, bodyweight fraction).
- User-created exercises tag primary / secondary / tertiary muscles, which map onto the model's existing direct / indirect / stabiliser roles. Compoundness and systemic cost — properties of the movement, not its muscles — are derived from equipment, pattern and tags.
- Derived coefficients are marked as such and reduce the dose-quality confidence component (ξ = 0.75). They never alter the dose itself.
- **Correction during drafting:** the first systemic-cost derivation used recruited muscle mass alone and failed 7 of 18 test exercises. Mass identifies which muscles work; posture and movement pattern determine what the effort costs. Restructured so pattern and equipment drive the value with mass as a modulator — 36/36 coefficients now fall inside the documented class bands. `tools/derivation_check.py` holds the check.

**Exercise pool**

- Direct core work added: cable crunch, hanging leg raise, ab wheel rollout.
- Loaded carries and structured conditioning explicitly excluded from v0. Non-resistance activity remains daily steps alone.

### 0.2 — 22 August 2026

Specification completeness pass before Phase 1. No change to the model's structure or scientific commitments; the revisions close gaps where one document required something another never defined.

**Newly specified**

- **Confidence.** Defined per channel rather than as a global scalar, with five named components, band thresholds and a required binding reason. Previously referenced by `PRODUCT.md` and `MODEL.tex` but never defined.
- **Explanation trace.** Defined as an exact impulse decomposition with a fixed record schema, including the versioned parameters and evidence grades a state depends on. Deterministic template rules for driver strings.
- **Capacity estimation.** $\bar P_e$ was described only as "a slow robust trend". Now a Huberised log-space update with specified learning rates, initialisation and a binding pre-session ordering rule.
- **Effective load for bodyweight exercises.** $w^{\mathrm{eff}} = \beta \cdot BM + w_{\mathrm{ext}}$, with v0 fractions, smoothed body mass, a unilateral convention and a missing-data policy.
- **Performance-relevance weights.** $\omega_{me}$ defined as the fatigue-contribution vector normalised to unit sum, with the rationale for using $c^F$ rather than $c^S$.
- **Relative-intensity domain policy.** Linear extension to the definitional point (1 repetition, 100% of 1RM) at the top; refusal to extrapolate below 50%; a three-level confidence flag.
- **Set-type inclusion rules.** Explicit channel-by-channel table. Drop segments contribute full dose but are excluded from performance estimation and PR detection.
- **Temporal conventions.** Recovery-context windows anchored to the sleep episode rather than the calendar day; daily step load distributed across the waking window with a closed-form constant-input solution; an explicit continuity test.
- **Adaptation gain.** $k_A = 0.014$, normalised so that $A_m \approx 1$ corresponds to a sustained twelve effective sets per week.

**Changed**

- **$\lambda_F$, $\lambda_N$, $\lambda_G$ raised** from 0.030 / 0.020 / 0.015 to 0.065 / 0.045 / 0.030. The originals produced ~2.4% suppression after an ordinary hard session, too small for fatigue states to be identifiable from observed performance. Now calibrated to explicit next-session decrement bands, with a numerical-stability clip at 0.25 in the exponent.

**Made explicit**

- **Load invariance.** The dose channels depend only on repetitions, RIR and exercise; absolute external load enters the performance channel alone. This was already true of the v0.1 equations but undocumented. Now recorded as a deliberate decision, with its rationale, its accepted consequences and the conditions that should trigger a revisit.
- **The adaptation state does not drive capacity in v0.** Recorded as a deliberate epistemic choice with its justification, and framed as a testable Phase-3 question rather than a gap.

**Evaluation**

- `DATA.md` §19 gains calibration targets, confidence-behaviour tests, explanation-trace integrity checks and capacity-estimator robustness tests. Generation requirements added for drop sets, near-maximal anchors and performance-test frequency, so that the new engine rules are actually exercised by the dataset.
