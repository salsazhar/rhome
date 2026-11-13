# Rhome — Product Specification

**Version:** 0.5  
**Date:** 25 August 2026  
**Status:** Canonical project document

## 1. Product definition

**Rhome** is a personal resistance-training load, recovery, and performance modelling system.

Its purpose is not merely to record workouts. Its purpose is to infer the changing state of the trained body from two primary information streams:

1. **Set-level resistance-training data** — exercise, load, repetitions, RPE/RIR, timestamp and session context.
2. **Daily recovery/context data** — principally sleep, nocturnal HRV, resting heart rate, temperature deviation and activity/steps from a wearable such as Oura.

Rhome converts these observations into a set of interpretable latent-state estimates: muscle-specific training stimulus, local residual fatigue, systemic fatigue, neuromuscular strain, training-capacity trends and projected performance/recovery.

The product thesis is:

> **A workout log tells the user what they did. A readiness score tells the user how they look today. Rhome should explain the trajectory connecting the two.**

## 2. Name

**Rhome** is derived from Greek *rhōmē* (ῥώμη), denoting strength, bodily vigour or force. The name is intentionally short, corporeal and non-descriptive: the product should feel like a performance system rather than a generic fitness tracker.

## 3. Problem

Resistance-training data and recovery data are usually fragmented.

A lifter may have:

- detailed set history in one training app;
- sleep, HRV, resting HR, temperature and activity in a wearable app;
- body mass in a separate weight-tracking app;
- no coherent model explaining how those streams interact.

Existing products commonly reduce recovery to a proprietary scalar or reduce training load to volume, tonnage, set counts or generic workload. These abstractions are useful but incomplete for resistance training because:

- training stress is **muscle-specific**;
- stimulus and fatigue are related but not identical;
- a hard set of lateral raises and a hard set of squats should not have the same systemic or neuromuscular cost;
- proximity to failure matters;
- relative load and exercise characteristics matter;
- fatigue evolves through time rather than disappearing at midnight;
- sleep and autonomic data are contextual signals, not direct measurements of muscle recovery;
- the same nominal session can have different consequences for the same athlete under different recent conditions.

Rhome is intended to model this structure explicitly.

## 4. Product goal

The principal user question is:

> **What state is my training system in now, why is it in that state, and where is it likely to be over the next several days?**

Rhome should eventually answer five subordinate questions:

1. **What did this session cost?**  
   Estimate local muscular fatigue, adaptive stimulus, systemic fatigue and neuromuscular strain from the workout.

2. **What has recovered?**  
   Evolve those states through time using athlete-specific recovery dynamics and daily physiological context.

3. **What is accumulating?**  
   Maintain slower training-capacity and adaptation/load trends without conflating them with acute fatigue.

4. **How is performance moving?**  
   Track exercise-specific estimated performance capacity using load, repetitions and RPE/RIR.

5. **What happens next?**  
   Project the state forward and permit counterfactual planning such as adding a hypothetical workout.

## 5. Intended user

### v0 user

A resistance-trained individual who:

- trains approximately 4–6 times per week;
- records working sets and RPE/RIR reliably;
- has reasonably stable exercise technique;
- uses a wearable that provides nocturnal HRV, resting HR and sleep data;
- wants quantitative training-state information rather than generic coaching content.

### Longer-term user

The architecture should generalise to other resistance-trained users, but **v0 is deliberately a single-athlete product and modelling problem**. Personalisation is a feature, not an inconvenience.

## 6. Product principles

### 6.1 Model first; logger second

The analytical engine is the product. Logging and integrations are data-acquisition layers.

Rhome should therefore be built so that the mathematical engine accepts a documented, platform-independent schema and returns deterministic state estimates. The engine must not depend on the mobile UI.

### 6.2 Muscle-specific by default

Resistance-training load should be decomposed by muscle or muscle group rather than represented only as a whole-body scalar.

### 6.3 Stimulus is not fatigue

Rhome must maintain distinct concepts for:

- **adaptive/muscular stimulus**;
- **local residual fatigue**;
- **neuromuscular strain**;
- **systemic fatigue/load**.

More work can increase both stimulus and fatigue, but not necessarily proportionally.

### 6.4 Do not claim to measure the CNS

Rhome must not expose a metric called “CNS fatigue” or imply direct measurement of central nervous-system fatigue from a workout log or wearable.

The product term is **Neuromuscular Strain**: a modelled index reflecting the burden of high-force, high-relative-intensity, compound and near-limit resistance work. It is an inference, not a direct physiological measurement.

### 6.5 Recovery data are contextual evidence, and flow one way

Sleep, HRV, resting HR and temperature modify confidence in recovery and may alter estimated recovery dynamics. They do not directly reveal whether a particular muscle is “82% recovered”.

They are also **inputs only**. Rhome does not predict tomorrow's HRV, because autonomic variance is dominated by influences outside training and forecasting it would serve no athlete. The model does hold an *expectation* for these channels given recent training — but only so that it can separate the part of a reading that training explains from the part it does not. The residual is the informative half, and the athlete sees it as an explanation rather than a forecast: "below baseline, expected after Thursday's session" rather than "tomorrow will be 58 ms".

### 6.6 Personal baselines over population cut-offs

Wearable signals should be interpreted primarily as deviations from the athlete's own rolling baseline rather than against universal HRV or resting-HR thresholds.

### 6.7 Relative effort, not absolute load

Training dose is modelled as a function of proximity to failure and repetitions performed, not of the number on the bar.

A set of five repetitions at one repetition in reserve represents a comparable proportional demand whether the athlete is moving 60 kg or 160 kg. Both lifters are near their own limit. Rhome therefore routes absolute load exclusively to the performance channel, where it is the primary signal, and keeps it out of the fatigue, stimulus, strain and systemic channels entirely.

The consequence is that modelled fatigue per set does not inflate simply because the athlete has become stronger. This is intended. See the load-invariance section of `MODEL.tex` for the formal statement, the accepted limitations and the conditions under which the decision should be revisited.

### 6.8 Log at the athlete's granularity; model at the evidence's

Lifters think in terms of upper chest, traps, obliques and grip. A logger that offered only coarse muscle groups would feel impoverished, and Rhome should not ask the athlete to translate their own training into the model's vocabulary.

But the evidence base underneath this model is reported per muscle group, not per region. Nothing in it supports treating upper-chest fatigue as a state distinct from lower-chest fatigue.

Rhome therefore separates the two. The **display taxonomy** is as granular as any competitor's; the **model taxonomy** is sixteen groups, and the mapping between them is explicit. The athlete logs what they did; the model claims only what it can defend.

### 6.9 Preserve uncertainty

Where science does not identify an exact coefficient, Rhome should use a transparent prior, label it as such, and make it calibratable.

### 6.10 No false injury prediction

Rhome may show acute and chronic load trends, but it must not claim an acute:chronic workload “safe zone”, diagnose overtraining, or predict injury risk from a simple ratio.

## 7. v0 inputs

### 7.1 Required workout inputs

For each working set:

- timestamp / workout ID;
- exercise ID;
- set number;
- external load;
- repetitions;
- RPE or RIR;
- set type (working, warm-up, drop set, etc.);
- **equipment context** — which physical station the load was read from.

**Equipment context, added at version 0.5.** Through version 0.4 this list
assumed a logged load meant the same thing wherever it was recorded. It does
not. A barbell is 60 kg in any room; a cable stack marked 14 is not, and two
leg-extension machines disagree by more than a year of training gains.

This is not a refinement. It was the largest single source of error in the real
cold run. Measured on the athlete's 99-session log, the best possible naive
predictor scores **0.0976** on free weights and **0.1657** on cable and machine
work — the gap is the labelling, not the athlete. One `exercise_id` was found
running 18 → 9 → 5 kg across gyms, and four such identities accounted for 78%
of the error.

The evidence is **between rooms, not within them.** On `cable_lateral_raise`,
first-set load across the athlete's two gyms:

| | sessions | first-set load | median |
|---|---:|---|---:|
| Main gym | 8 | 6.3 → 8.8 | 7.5 |
| Second gym | 21 | 3.4 → 18.0 | 14.0 |

The medians differ by 1.9×, on the same movement by the same athlete. That is
the labelling problem. The wide range *inside* the second gym is mostly a
training trajectory — 3.4 rising to a stable 14.0 by day 340, held for ten
sessions — and not a stack disagreeing with itself. An earlier draft of this
clause read that range as within-gym machine variation. It was not, and the
distinction matters: it is the difference between needing a station and needing
a room.

**Granularity is the athlete's, per §6.8.** Where a gym's cables genuinely share
one weighting, the gym *is* the context and one label for the building is
correct. Where two machines of a kind disagree, the station is the context.
The athlete knows which case they are in and the logger must not overrule them —
it treats each distinct label as its own load scale and asks no more than that.

What cannot be recovered is a context never recorded at all, which is why the
field is required at logging time. Free-weight and bodyweight movements need no
context and must not demand one; asking where it does not apply is friction
that buys nothing.

**Per-set timestamps.** Sets carry their own completion time, not merely a
workout time. `DATA.md` §18 already requires this and no source has yet
supplied it — the synthetic generator applies a whole session at one instant,
and the imported archive carries no set-level clock. Within-session position is
now a model input, so a logger that records when each set actually happened
closes a standing gap rather than adding a new demand.

Set type determines which channels a set enters:

| `set_type` | Load model | Performance model |
|---|---|---|
| `warmup` | excluded (configurable) | excluded |
| `working` | included | included |
| `backoff` | included | included |
| `drop` | included | excluded |

Warm-up sets are stored but excluded from the principal load model unless explicitly configured otherwise. Drop-set segments contribute their full training dose — the work was genuinely performed — but are excluded from performance estimation and PR detection, because a set begun in a deliberately pre-fatigued state carries no clean information about fresh capacity.

### 7.2 Exercise metadata

Rhome maintains **its own exercise database**, in two layers.

The **base layer** — name, movement pattern, equipment, muscle tags — is commodity data and can be seeded from any standard exercise list. The **scoring layer** — the muscle contribution weights, compoundness, systemic cost and bodyweight fraction — is specific to this model. It is what converts a logged movement into a dose, and no external exercise database provides it. This layer is Rhome's, and is the reason the product can say what a session cost rather than only what it contained.

Athletes may create their own exercises, tagging **primary**, **secondary** and optionally **tertiary** muscles. Those tiers map onto the model's existing contribution roles, so a user-created exercise is a first-class citizen rather than a special case. A tertiary muscle accrues fatigue but no adaptive credit — correct for stabilising work, and worth stating plainly in the interface, since it is not obvious.

What a user cannot supply is compoundness and systemic cost, which are properties of the movement rather than of its muscles. These are derived from equipment, movement pattern and the muscles tagged, and the exercise is marked as carrying derived rather than curated coefficients. That distinction flows into the confidence indicator, so an athlete relying heavily on self-created exercises is told that their estimates rest on inferred coefficients — rather than being shown the same confidence as someone using the curated library.



Each exercise requires metadata including:

- movement pattern;
- primary muscles;
- secondary muscles;
- stabilising muscles where relevant;
- exercise class (isolation / machine compound / free-weight compound / bodyweight compound);
- compoundness coefficient;
- large-muscle/systemic-cost coefficient;
- optional axial-loading, novelty and eccentric-demand metadata.

### 7.3 Recovery/context inputs

Daily:

- total sleep time;
- sleep efficiency;
- nocturnal RMSSD HRV;
- resting/nocturnal heart rate;
- temperature deviation;
- steps/activity;
- optional body mass.

Oura Readiness and Sleep scores may be stored and displayed but are not primary inputs to the v0 recovery equation because they already combine several underlying variables.

### 7.4 Body mass

Body mass is optional for most loaded exercises. It becomes materially useful for bodyweight movements such as pull-ups and dips, and potentially for running/activity modelling.

## 8. v0 outputs

### 8.1 Today

The home view should answer “what state am I in?” with:

- Recovery Context score/index;
- Systemic Fatigue;
- Neuromuscular Strain;
- muscle-by-muscle residual fatigue;
- recent muscle-specific stimulus;
- confidence/uncertainty indicator;
- short explanatory drivers (for example: “high hamstring fatigue from RDL volume yesterday; sleep normal”).

#### Confidence

Confidence is reported **per channel**, not as one global number, because the conditions that undermine one estimate do not undermine the others. A fortnight without training leaves fatigue estimates highly certain — they have decayed to near zero — while leaving performance-capacity estimates stale.

Each channel is displayed as a band with the reason attached:

| Band | Range | Example presentation |
|---|---|---|
| High | ≥ 0.75 | “High confidence” |
| Moderate | 0.50–0.75 | “Moderate: baselines still forming” |
| Limited | < 0.50 | “Limited: no wearable data for six nights” |

The band alone is not sufficient. The interface must always show the **binding reason** — the component driving confidence down — because a bare number tells the athlete nothing actionable.

Confidence is an index of evidence sufficiency. It is never presented as the probability that an estimate is correct.

#### Explanation trace

Every displayed state must be expandable into the exact set of contributions that produced it. This is not a nicety; it is the mechanism by which the model stays honest.

Because each state is a sum of decaying impulses, attribution is exact rather than reconstructed. Expanding a state shows:

- the ranked contributing sets or sessions, with each one's surviving share of the current value and its age;
- the modifiers applied, such as the recovery-context multiplier and the wearable deviations behind it;
- **every parameter used, with its evidence grade and version.**

The last item matters most. It allows the athlete — and any later reviewer — to see that a displayed number rests on a specific set of engineering priors rather than on measured physiology. Driver strings are generated deterministically from the trace through fixed templates, never by free text generation.

### 8.2 Load

Display:

- per-muscle effective/fractional set load;
- per-muscle stimulus trend;
- local-fatigue impulses and decay;
- systemic and neuromuscular load;
- short-horizon and long-horizon exponentially weighted load traces.

The short and long traces are shown separately. Their ratio is not presented as an injury-risk score.

### 8.3 Recovery

Display:

- HRV relative to rolling personal baseline;
- resting HR relative to baseline;
- sleep duration and sleep debt/context;
- sleep efficiency;
- temperature deviation;
- recovery-context multiplier/index;
- relationship between recovery signals and subsequent performance over time.

### 8.4 Performance

For each major exercise:

- load/repetition/RPE history;
- RIR-adjusted estimated relative intensity;
- estimated 1RM/performance-capacity trend;
- observed performance versus model expectation;
- PR and trend detection;
- optional fatigue-adjusted performance estimate.

### 8.5 Projection

Project forward at least 72 hours and preferably 7 days:

- local muscle fatigue curves;
- systemic-fatigue curve;
- neuromuscular-strain curve;
- expected recovery context if no further information arrives;
- projected exercise-performance capacity.

The projection screen should eventually support **counterfactual sessions**: the user enters a hypothetical workout and sees the projected change in load/fatigue states.

## 9. Product screens

### Screen 1 — Today

A concise system-state view with body map, major load states, recovery context and the dominant explanatory factors.

### Screen 2 — Load

Time-series view of local, systemic and neuromuscular load, with muscle filters.

### Screen 3 — Recovery

Wearable-derived recovery variables, personal baselines and their relationship to training/performance.

### Screen 4 — Performance

Exercise-specific progression and fatigue-adjusted performance trends.

### Screen 5 — Projection

Future-state curves and counterfactual training planning.

### Screen 6 — Log / Import

Not a v0 priority. If external workout ingestion is unavailable, Rhome will later require a minimal native logger optimised for rapid entry of load × reps @ RPE/RIR.

## 10. Data strategy

### 10.1 Model development dataset

Rhome v0 is developed against a **fully generated longitudinal dataset**, not a public training dataset.

The synthetic dataset is valuable because the simulator knows latent ground truth—true local fatigue, systemic fatigue, neuromuscular strain and underlying performance capacity—while the inference engine is given only observable workout and wearable-like data.

This permits direct evaluation of whether the inference engine reconstructs the hidden state.

### 10.2 Separation of simulator and inference engine

This is a hard architectural rule.

The simulator must not simply expose the same equations used by the inference engine. Doing so would create an inverse-crime problem in which the estimator succeeds because it is effectively solving the exact process that generated the data.

The simulator therefore includes:

- stochastic physiology;
- measurement error;
- non-linear effects;
- athlete-specific latent parameters;
- unobserved daily disturbances.

The inference engine uses simpler, transparent priors that are later personalised from observed data.

## 11. Technical architecture

```text
Raw workout data ─┐
                  ├─> Normalisation layer
Wearable data ────┘          │
                             v
                     Set-load transformation
                             │
              ┌──────────────┼──────────────┐
              v              v              v
       Local muscle      Neuromuscular    Systemic
        stimulus/fatigue     strain        load/fatigue
              └──────────────┼──────────────┘
                             v
                    Recovery-state update
                             │
                             v
                    Time-evolution engine
                             │
              ┌──────────────┼──────────────┐
              v              v              v
         Current state   Performance     Projection
                         estimation
```

The core should be implementable as a pure library, e.g.:

```text
engine(inputs, previous_state, timestamp) -> new_state, outputs
```

with versioned model parameters.

## 12. Explicit non-goals for v0

Rhome v0 will **not**:

- track calories or nutrition;
- track water intake;
- provide meal plans;
- provide generic AI-coach chat;
- diagnose illness, overtraining syndrome or medical conditions;
- claim direct measurement of CNS fatigue;
- claim an exact muscle-recovery percentage as a measured biological fact;
- produce injury-risk predictions from ACWR or similar heuristic ratios;
- optimise a full programme automatically;
- depend on public datasets for model training.

## 13. Development phases

### Phase 0 — Documentation and scientific priors

- Product specification.
- Mathematical model specification.
- Research/validation summary.
- Synthetic-data specification.

### Phase 1 — Simulator

- Generate Athlete A over two years.
- Produce observable workout/recovery data.
- Produce simulator-only latent ground truth.
- Verify invariants and scenarios.

### Phase 2 — Deterministic inference engine

- Transform sets into load impulses.
- Maintain local/systemic/neuromuscular states.
- Apply recovery dynamics.
- Estimate performance trends.
- Compare estimates with simulator ground truth.

### Phase 3 — Personalisation

Estimate athlete-specific parameters from longitudinal observations, for example:

- muscle-specific recovery half-lives;
- sensitivity to proximity-to-failure work;
- relationship between sleep/autonomic deviations and performance;
- exercise-specific REPS–%1RM curves;
- individual RPE/RIR bias.

A Bayesian/state-space approach is a likely later extension, but v0 should remain inspectable.

### Phase 4 — Mobile product

- Today dashboard.
- Load/recovery/performance/projection screens.
- Oura integration.
- Native workout logger if a reliable third-party workout integration is unavailable.

## 14. v0 success criteria

The model is ready to drive a UI when it can satisfy the following tests on withheld synthetic data:

1. Correctly rank high-fatigue versus low-fatigue sessions.
2. Recover the broad time course of local fatigue after ordinary, high-volume and failure-heavy sessions.
3. Distinguish local fatigue from systemic and neuromuscular strain.
4. Show slower recovery under deliberately adverse recovery conditions without letting one bad HRV reading dominate the model.
5. Identify deload/rebound patterns.
6. Track exercise-performance trends despite noisy RPE and daily performance variation.
7. Produce sensible 72-hour and 7-day projections.
8. Avoid implausible discontinuities at calendar-day boundaries.
9. Remain numerically stable under missing wearable data.
10. Provide an explanation trace for every displayed state: the model must be auditable. Concretely, every state must expand into its exact impulse decomposition, its applied modifiers, and the versioned parameters it depends on.

## 15. From synthetic to real: how the model is validated

The v0 model is developed against synthetic data and will be used on real data. The logic connecting the two is the argument the whole project rests on, and it is written down here so that it can be checked rather than assumed.

### 15.1 The synthetic dataset is not training data

Nothing in the inference engine is learned from the synthetic dataset. The engine's equations come from `MODEL.tex`, which draws on `RESEARCH.md`, which draws on the literature. Fitting the engine to synthetic data would teach us nothing: we would recover our own assumptions and call it validation.

The dataset is a **test harness with an answer key**. The simulator generates observable data from a hidden state using one process; the engine estimates that state from the observables using a different and simpler process; evaluation scores the second against the first. The inverse-crime audit exists to prove those two processes genuinely differ, because if they were the same equations run backwards the exercise would be circular.

### 15.2 What synthetic data can and cannot establish

It can establish four things, each necessary:

1. **Identifiability.** Can the latent state be recovered from observable data at all? If the engine cannot recover fatigue from a dataset where the answer is known, it certainly cannot from real data where nobody knows it. Only synthetic data can test this.
2. **Absence of target leakage.** Verifiable only with a complete pipeline and a known future.
3. **Behavioural correctness.** A deload reduces fatigue; one bad session barely moves capacity; a missed week is not illness.
4. **Numerical robustness.** Missing data, malformed input, edge cases.

It cannot establish that the quantity labelled "hamstring fatigue" corresponds to anything occurring in a hamstring. `DATA.md` §22 states this, and it remains true however well the engine scores.

There is a further limit worth naming plainly. The simulator and the engine were written from the same literature by the same hands. They differ structurally, which the audit demonstrates, but **they share their author's blind spots**. If something physiologically real matters that neither model contains, synthetic evaluation is structurally incapable of revealing it. Only real data can.

### 15.3 What is scoreable on a real person

On real data there is no answer key and never will be. Fatigue cannot be scored directly, ever.

What can be scored is prediction — but only of quantities the training system itself produces:

| Observable | Origin | Rhome's treatment |
|---|---|---|
| Load x repetitions | Produced by the training system | Predicted and scored |
| RPE / RIR | Produced by the training system | Predicted and scored |
| HRV, resting HR, sleep, temperature | Produced largely by life outside training | Consumed as input; never predicted as an output |

The distinction is not fastidiousness. Autonomic variance is dominated by work stress, sleep timing, alcohol and illness. A model scored on predicting HRV would be scored chiefly on its ability to predict things that have nothing to do with training, which would create pressure to bolt on life-event models in pursuit of a number no athlete wants. Optimising a proxy that is not the target is how a model gets worse while its scores improve.

Load and effort are different observations of the same state, and are scored separately. Two sessions can produce identical load and repetitions at very different effort; a model that predicts both makes a stronger claim than one that predicts only their ratio.

### 15.4 Latent fatigue earns its place by prediction, or not at all

Fatigue is a construct. It is justified only if modelling it improves the prediction of things that are observed. Before real data is opened, the following ladder is committed to, so that a disappointing result cannot be rationalised afterwards:

| Baseline | What it winning would mean |
|---|---|
| Last session's performance | Nothing built here helps |
| Rolling average of recent sessions | The trend is all there is |
| Fatigue model, no recovery context | The wearable adds nothing |
| Recovery context, no fatigue model | The training-load machinery adds nothing |
| Full engine | Each component earns its place |

**Any component that does not beat its ablation should be removed, not defended.**

### 15.5 What real data contains that the synthetic athlete does not

Three categories, and the third is the reason the real-data run is a genuinely different test rather than more of the same.

**Simulated deliberately:** missed sessions, wearable gaps, illness, travel, plateaus, unexplained bad days.

**Knowingly absent:** Athlete A's training is balanced by design — §3.2 of `DATA.md` forces upper/lower parity within 10%. Real training is not like that. Programmes change, injuries intervene, someone runs three upper days to one lower for a month. The engine has never seen it.

**Not anticipated by anyone.** The unknown remainder. This is what the real-data run exists to find.

### 15.6 The progression

| Stage | Question | Answerable |
|---|---|---|
| Synthetic evaluation | Can the estimator recover structure it was not given? | Yes — only here |
| Real-data cold run | Does it survive real data and beat simpler baselines? | Yes |
| Personalisation | Can this athlete's own parameters be estimated? | Partially |
| Population calibration | Are the priors right in general? | Not from one athlete |

On personalisation from roughly a hundred sessions: RIR reporting bias is estimable, since it appears systematically in residuals, and a single scaling factor on fatigue sensitivity probably is. Sixteen muscle-specific half-lives are not. Anything claiming to fit those from a hundred sessions is fitting noise, and the honest output there is a wide posterior stating that the value is unknown.

## 16. Canonical documentation

The project directory contains four canonical documents:

- `PRODUCT.md` — what Rhome is and what it should do.
- `MODEL.tex` — mathematical definitions and v0 equations.
- `DATA.md` — rules for generation, schemas, scenarios and validation of the synthetic dataset.
- `RESEARCH.md` — scientific evidence, citations, parameter provenance and claim boundaries.

If implementation and documentation disagree, the discrepancy should be resolved explicitly and the relevant document version incremented.
