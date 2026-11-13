# Rhome — Build Plan

**Version:** 1.0
**Date:** 22 August 2026
**Status:** Canonical build plan
**Governs:** all implementation work from Layer 0 onward

This document plans the whole of Rhome v0 before any engine code is written. It exists so that the project can be built in small, separately verifiable pieces, so that every piece can be checked against a stated purpose, and so that the history of what was built and why remains legible months later.

It is written to be readable without a coding background. Each stage states, in plain language, what is being built and what "correct" means for it.

---

## 1. How this plan is organised

The project is divided into **layers**. A layer is a large, self-contained section of the system — the simulator is one layer, the inference engine is another. Layers are built in order, and each depends only on the layers beneath it.

Each layer contains **stages**. A stage is one focused piece of work, small enough to be verified on its own and to be understood in a single sitting.

Every stage produces four things:

1. **Working code**, in its own module.
2. **Tests** that check it does what the specification says.
3. **A build-log entry** recording purpose, decisions, validation results and any deviations.
4. **One git commit**, tagged with the stage ID.

Layers end in a **checkpoint**: a stop where the accumulated work is reviewed together, including a visual pack you can inspect directly, before the next layer begins.

### Mapping to the specification

`PRODUCT.md` §13 defines development phases. This plan refines them:

| Spec phase | Layer here |
|---|---|
| Phase 0 — Documentation | Complete (docs v0.2) |
| — | **L0 — Foundation** (new; shared substrate and guardrails) |
| Phase 1 — Simulator | **L1 — Simulator** |
| Phase 2 — Deterministic inference engine | **L2 — Engine** |
| — | **L3 — Evaluation** (split out; it is the proof the engine works) |
| Phase 3 — Personalisation | **L4 — Personalisation** |
| Phase 4 — Mobile product | **L5 — Product surface** |

L0 and L3 are additions. L0 exists because the simulator and engine share a substrate — muscle names, exercise metadata, time handling — and building that twice would guarantee they drift apart. L3 is separated from L2 because evaluation is the only part of the system permitted to see both the simulator's hidden truth and the engine's estimates, and that privilege needs its own boundary.

---

## 2. What "validated" means

A stage is not finished when the code runs. It is finished when it has passed four levels of checking, in this order.

**Level 1 — Automated tests.** Unit tests for individual calculations, property tests for rules that must always hold (a fatigue state can never go negative; a decay must never increase), and golden-value tests where a number computed by hand from `MODEL.tex` is compared against what the code produces. These run on every stage from then on, so a later stage cannot silently break an earlier one.

**Level 2 — Specification conformance.** Every stage carries an explicit map from specification clause to test. If `MODEL.tex` says the failure multiplier at 0 RIR is 1.35, a named test asserts exactly that, and the map records which test covers which clause. Clauses with no test are visible as gaps rather than invisible.

**Level 3 — Visual validation pack.** Plots and tables built for human inspection, not for machines. This is the level that matters most for your review: distributions, time series, a sample training month, before/after comparisons. A statistical test can confirm that sleep averages 7.5 hours; only a person looking at a chart can say whether the training log *looks like a real training log*.

**Level 4 — Your checkpoint sign-off.** At layer boundaries, you review the visual pack and the build log and decide whether to proceed. Nothing proceeds past a checkpoint without that.

A stage may finish in one of three states: **passed**, **passed with notes** (works, with a recorded caveat to revisit), or **blocked** (stops the layer until resolved).

---

## 3. Traceability: the build log

Every stage writes one file to `build_log/`, named for its stage ID.

Each entry records:

- **Stage ID and name**, date, and the git commit hash
- **Purpose** — one paragraph in plain language: what this is for and why the project needs it
- **What was built** — the modules and functions added
- **Specification references** — which document sections this implements
- **Validation** — what was checked, how, and the actual results
- **Decisions** — any judgement call made during the stage, with reasoning
- **Deviations** — anything that differs from the specification, and whether the specification was updated in response
- **Status** — passed, passed with notes, or blocked

Two additional files run across the whole project:

- `build_log/INDEX.md` — a running table of every stage, its status and its commit, so the whole history is visible on one page.
- `build_log/DECISIONS.md` — cross-cutting decisions that affect more than one stage, so they are not buried inside a single stage's entry.

Because each stage is also exactly one git commit carrying its stage ID, the code history and the written history line up. Any state of the project can be traced from a line of code back to the decision that produced it and the specification clause that required it.

---

## 4. The five guardrails

These are built first, in L0, before any modelling code. They are the mechanisms that stop the project degrading as it grows. Each is enforced by a test that fails loudly, not by discipline or memory.

**Guardrail 1 — The import boundary.** The simulator and the inference engine must never import from each other, and the engine must never read the hidden latent-state files. This is the project's central methodological rule: if the engine can see the simulator's internals or its answers, then every result afterwards is worthless. A test walks the import graph and fails if the boundary is crossed. The evaluation package is the single exception, and is the only package permitted to import both.

**Guardrail 2 — Frozen projections.** Before each session is revealed to the engine, its predicted performance is written down and locked. A test asserts that this stored prediction is unchanged after the session is ingested. Without this, the engine could quietly use a workout to predict itself, and every performance metric would flatter the model.

**Guardrail 3 — The parameter registry.** Every number from the specification lives in one versioned registry, never typed inline in code. Each entry carries its value, its evidence grade and its document reference. A test compares the registry against the documents and fails if they disagree. This is what stops a parameter being adjusted in code while the documentation continues to claim the old value.

**Guardrail 4 — Deterministic seeding.** Every random draw comes from an explicitly passed generator, never a global one. Running the generator twice with the same seed must produce byte-identical output, and a test asserts it.

**Guardrail 5 — The conformance map.** A generated report listing every testable specification clause and the test covering it. Uncovered clauses appear as gaps. This is checked at every layer checkpoint.

---

## 5. Technical choices

Stated plainly, since these are decisions you are entitled to overrule.

- **Language: Python.** The right choice here because the work is numerical and exploratory, the libraries for it are mature, and it stays readable. Speed is not a constraint: two years of synthetic data is a small dataset.
- **Core libraries:** `numpy` and `pandas` for numerical work and tables, `pydantic` for schema validation, `pytest` for tests, `matplotlib` for the visual packs.
- **No machine-learning frameworks in v0.** The v0 model is deterministic and inspectable by design. Adding a framework now would obscure that.
- **Dependencies kept minimal**, because every dependency is something that can break later and something a reader has to understand.

Data is stored as CSV, as `DATA.md` §20 specifies, with the exact directory layout given there.

---

# Layer 0 — Foundation

**Purpose:** build the shared substrate and the guardrails before anything depends on them.

Nothing here is modelling. This layer exists so that the simulator and the engine agree about what a muscle is, what an exercise is and how time works, without either being able to see inside the other.

### L0.1 — Repository scaffolding and guardrails

**Purpose.** Put the project's structural rules in place while the codebase is still empty, when they are cheap to enforce.

**Builds.** Python project setup; the package skeleton (`rhome_core`, `rhome_sim`, `rhome_engine`, `rhome_eval`); the build-log structure; the test runner; and guardrails 1, 4 and 5.

**Validated by.** Deliberately writing a forbidden import and showing the test suite reject it, then removing it and showing the suite pass. The guardrails are demonstrated working, not merely asserted to exist.

### L0.2 — Canonical taxonomy, units and time

**Purpose.** Fix the vocabulary. Fifteen muscle groups, the unit conventions, and the time handling that `MODEL.tex` §Temporal conventions requires — continuous hours, windows anchored to waking rather than midnight.

**Builds.** Muscle group definitions; time utilities including the closed-form decay and constant-input solutions; the sleep-anchored window logic.

**Validated by.** Property tests: the closed-form decay agrees with slow numerical integration to tolerance; state is continuous across midnight; no quantity resets at a calendar boundary.

### L0.3 — Exercise metadata

**Purpose.** Encode the exercise library. This is the table that decides which muscles a movement loads and how expensive it is, so a great deal of the model's behaviour is determined here rather than in any equation.

**Builds.** ~23 exercises from `DATA.md` §8, each with primary/secondary/stabiliser muscles, the two contribution vectors, compoundness, systemic cost, bodyweight fraction, Nuzzo curve assignment and the unilateral flag.

**Validated by.** Schema validation and range checks; every muscle group reachable by some exercise; sanity rankings asserted as tests (a back squat must have higher systemic cost than a lateral raise); and confirmation that the upper/lower parity requirement of `DATA.md` §3.2 is achievable from this pool.

**Note.** This is the stage where your own judgement is most useful, because these are training-domain values rather than derived quantities. It is the first thing in the checkpoint pack.

### L0.4 — Relative-intensity mapping

**Purpose.** Implement the reps-to-%1RM relationship, including the near-maximal extension and high-repetition clip added in docs v0.2.

**Builds.** The general Nuzzo curve plus bench and leg-press curves; inversion by interpolation; the `u_confidence` flag.

**Validated by.** Reproducing every published table value exactly; monotonicity across the whole domain; explicit edge-case tests (one repetition returns 100%; thirty repetitions clips to 50% and flags low confidence).

**Important separation.** `rhome_core` provides the *population* curve only. The simulator draws its own athlete-specific deviations around it; the engine uses the population curve as its prior. They are therefore not solving the same equation, which is what keeps this shared component from becoming an inverse crime.

### ▣ Checkpoint 0

Review the exercise metadata table and the guardrail demonstrations. Substrate frozen before the simulator is built on top of it.

---

# Layer 1 — Simulator

**Purpose:** generate two years of Athlete A — the observable data a real app could collect, and the hidden truth used later to mark the engine's work.

The simulator must be *structurally richer* than the engine. If it were the same equations run forwards, the engine would succeed at inverting its own generator and prove nothing. Keeping them genuinely different is the point of this layer.

### L1.1 — Athlete A latent parameters

**Purpose.** Create the specific individual. Per-muscle recovery half-lives, RIR estimation bias, performance noise, autonomic baselines — the hidden constants that make this a particular athlete rather than an average one.

**Validated by.** Reproducibility under seed; every sampled parameter inside its documented range.

### L1.2 — Physiology core

**Purpose.** The true latent state evolving in continuous time: fatigue per muscle, systemic fatigue, neuromuscular strain, adaptation.

**Builds.** Non-linear fatigue accumulation with genuine interaction between volume and proximity to failure, per `DATA.md` §16.2 — deliberately unlike the engine's simple additive impulses.

**Validated by.** Invariants (states non-negative, decay monotone without input) and an **inverse-crime audit**: a written, structural comparison of simulator and engine, listing every point where they differ. This is a document you can read, not just a passing test.

### L1.3 — Recovery and wearable generation

**Purpose.** Generate sleep, HRV, resting heart rate, temperature, steps and body mass as correlated consequences of a hidden daily recovery state, then corrupt them with realistic measurement error.

**Validated by.** `DATA.md` §18 invariants; correlation structure between channels; and specifically that a hard session does *not* deterministically drive HRV down the next morning, since that ambiguity is the property the engine must learn to handle.

### L1.4 — Programme generator

**Purpose.** Decide what Athlete A actually trains: the weekly template, exercise selection, set and rep prescription, progression and substitutions.

**Validated by.** Distributions matched against `DATA.md` §9 — rep ranges, RPE spread, 10–14 effective sets per muscle per week — and the hard upper/lower parity requirement of ±10% across rolling four-week blocks.

### L1.5 — Performance generation chain

**Purpose.** Produce each set in the correct causal order: latent capacity, then fatigue, then expressible performance, then a random shock, and only then the load and repetitions actually performed, the true RIR, and finally the noisy logged RPE.

This ordering is what makes the dataset a genuine test. Observable data must be a *consequence* of hidden state, never assigned alongside it.

**Validated by.** An ordering test asserting no observable quantity depends on a latent value computed after it; confirmation that performance noise is heteroskedastic as specified.

### L1.6 — Scenario engine

**Purpose.** Place the thirteen scenarios S0–S12 across the two years and record them in the manifest.

**Validated by.** One test per scenario, each asserting the documented expected latent effect actually occurred — that the failure block did raise fatigue disproportionately, that the deload did produce rebound.

### L1.7 — Missing data and dirty fixtures

**Purpose.** Make the dataset imperfect on purpose, so the engine is forced to cope with gaps rather than assuming clean input.

**Validated by.** Missingness rates within spec, and a statistical check that missingness is *not* concentrated in adverse scenarios — otherwise the engine could learn that absent data implies a bad day.

### L1.8 — Full generation run and quality report

**Purpose.** Produce dataset v0.1.0: 730 days written to the specified directory layout, with a generation config recording seed, parameters and commit hash, and a machine-generated quality report.

**Validated by.** Size targets from `DATA.md` §4; every §18 invariant; full reproducibility from the config alone.

### ▣ Checkpoint 1

The largest review point in the project. You receive a visual pack: a sample training month, the scenario timeline, all distributions, wearable time series, body-mass and performance trajectories. The question you are answering is a domain question, not a technical one — **does this look like two years of real training?** If it does not, the engine built on it is not worth building.

---

# Layer 2 — Inference engine

**Purpose:** build the actual product — the model that sees only observable data and reconstructs the athlete's state.

From here the hidden files are off limits. The engine is developed against days 1–520 only.

### L2.1 — Input normalisation and set transformation

**Purpose.** Turn a logged set into the four dose channels: stimulus, local fatigue, neuromuscular strain and systemic load.

**Validated by.** Golden values computed by hand from `MODEL.tex`; the ranking tests from `DATA.md` §19.3 (a failure set must produce more fatigue than a matched non-failure set); correct handling of every set type.

### L2.2 — State evolution

**Purpose.** Carry those impulses forward through continuous time.

**Validated by.** The midnight-continuity test; closed-form decay agreeing with numerical integration; distributed step load behaving as specified.

### L2.3 — Recovery context

**Purpose.** Compute the recovery multiplier from wearable data relative to the athlete's own 42-day baselines, conditioned on recent training.

**Builds.** The conditional autonomic expectation added in docs v0.4: the multiplier uses the *residual* after subtracting what recent systemic load predicts, rather than the raw deviation from a rolling baseline. A depressed HRV reading after a heavy session and the same reading on a rest day are different evidence, and the previous form could not tell them apart.

**Validated by.** That one anomalous HRV night does not dominate the state, and that missing wearable data contributes zero rather than a penalty — both explicit requirements. Plus the partition itself: on synthetic data the true recovery propensity is known, so the split between explained and unexplained deviation can be checked directly. Persistent unexplained deviation must reduce confidence rather than move the multiplier.

### L2.4 — Performance and capacity

**Purpose.** Estimate observed performance from each set, project expected performance under current fatigue, and update underlying capacity with the bounded-influence rule.

**Validated by.** Guardrail 2 in force — frozen projections proven unchanged after ingestion. Plus the S11 robustness test: one anomalously bad session must move estimated capacity by less than 1%.

**Note.** This is the most delicate stage in the project. It is where target leakage would enter if it entered anywhere, and leakage is invisible in results — it simply makes everything look better than it is.

### L2.5 — Session driver

**Purpose.** Wire the engine's parts into one pass over the calendar, in the order the specification requires.

**Why this was inserted.** Guardrail 2 enforces the freeze-then-score ordering, but until something drives it, no caller has ever exercised it — a guardrail that has never been used is only half-validated. L2.2 is the precedent: its activity-window ordering bug was invisible until the engine ran over real data, because a session at five in the afternoon sits inside a day's walking and nothing in isolation revealed that.

The stage after this one also depends on it. Confidence needs observation counts per exercise and residual spread, and both exist only once the performance model has processed real sessions; building it against hand-constructed state would test it against a fiction.

**Builds.** A day loop resolving recovery context on waking, extending the recovery timeline, advancing state, declaring the activity window, **freezing every projection before any of the day's sets are ingested**, applying the dose, then scoring residuals and updating capacity — strictly in that order.

**Validated by.** A full pass over the development window with no leakage error raised, and the first comparison of engine estimates against the simulator's latent truth. Also by deliberately driving the loop out of order and requiring Guardrail 2 to stop it.

### L2.6 — Confidence

**Purpose.** Compute the per-channel confidence defined in docs v0.2.

**Validated by.** `DATA.md` §19.5, including the deliberately counter-intuitive case: confidence in *fatigue* must not fall during a missed-session block, because not training is informative rather than a gap in evidence.

### L2.7 — Explanation trace

**Purpose.** Make every displayed number auditable, decomposed into the exact sets that produced it.

**Validated by.** `DATA.md` §19.6: contribution shares sum to one; the state can be reconstructed from its listed contributors; every parameter used appears with its evidence grade; and no generated driver string violates the claim boundaries in `RESEARCH.md` §17.

### L2.8 — Projection

**Purpose.** Project state forward 72 hours and 7 days, and support counterfactual sessions.

**Validated by.** Monotone decay under no training; counterfactual sessions producing the expected change; confidence widening with horizon.

### ▣ Checkpoint 2

The engine runs end to end across the development window. Visual pack shows estimated states over time against the training log — still without opening the hidden files.

---

# Layer 3 — Evaluation

**Purpose:** find out whether the engine actually works. This is the layer that turns the project from plausible into demonstrated.

`rhome_eval` is the only package permitted to see both the engine's estimates and the simulator's truth.

### L3.1 — Evaluation harness
The scoring framework and the scale alignment between latent and estimated quantities.

### L3.2 — State reconstruction metrics
`DATA.md` §19.1: correlation, error, directional accuracy, peak-timing error for every latent channel.

### L3.3 — Performance and capacity metrics

**Raised in priority at Checkpoint 2, and re-aimed by the drift investigation.**
The drift is a per-exercise warm-up transient, not a persistent lag: the engine
under-predicts by 5.6% until it has roughly twenty observations of an exercise,
then beats a recency baseline by 7.6%. The leading candidate is a **gain schedule** on the capacity learning rate — α
fixed at 0.06 from the fourth observation is far too slow when four
observations are all there is. Tried and measured: it improves residual MAE
from 0.0460 to 0.0425 and moves the pooled ablation from a loss to a tie, and
it breaks scenario S11 (one bad session moves capacity 3.3% against a 1%
requirement) along with anchor and confidence weighting. **It must therefore be
evaluated jointly with L3.7**, since the trade is accuracy against early
robustness and the accuracy metrics alone cannot make it. A Holt trend term and
a flat bias correction were also tried and rejected; see
`build_log/DRIFT_INVESTIGATION.md`.

 The ablation run at that gate found the
engine losing to a median-of-last-three baseline by 4.8% on mean absolute
error, and found the cause: once each predictor's slow bias is removed the
engine wins by 3.4%, but its own drift contributes fourteen times more variance
than the baseline's and spends the whole advantage. This stage must run the
full `PRODUCT.md` §15 ladder as a **gate**, not a report — an engine that
cannot beat recency on its most-tested output has not earned its complexity —
and must settle whether the drift is the Huber clip lagging sustained change or
a mis-scaled fatigue-suppression term λ.
`DATA.md` §19.2: one-step-ahead error, prediction bias, capacity reconstruction, residual calibration across fatigue bins. **A model that fits history but predicts the next session badly fails here** — which is the intended severity.

**Load and effort are scored separately**, not rolled together. Two sessions can produce identical load and repetitions at very different effort; both are produced by the training system, so both are predictable, and a model that predicts both makes a stronger claim than one predicting only their ratio. Wearable channels are not scored, because they are inputs rather than outputs (`PRODUCT.md` §15.3).

**The ablation ladder of `PRODUCT.md` §15.4 runs here**, against the synthetic data first, so the procedure is settled before it decides anything about the real dataset.

### L3.4 — Ranking tests
`DATA.md` §19.3: the six orderings the engine must get right.

### L3.5 — Calibration bands
`DATA.md` §19.4: the performance-suppression bands verified numerically during the v0.2 documentation pass.

### L3.6 — Confidence and trace integrity
`DATA.md` §19.5–19.6 run as a full suite.

### L3.7 — Robustness
`DATA.md` §19.8: bad HRV nights, bad sessions, missing data, high step counts, upper/lower parity.

### L3.8 — Holdout run

**Purpose.** The final examination, on days 521–730, which have never been looked at.

**The rule.** The holdout is opened **once**. Results are recorded whatever they are. If the engine fails, we fix it against the development window and it is recorded permanently that the holdout was consumed — a second run on the same data is a weaker test and must be reported as such. This discipline is the difference between an honest result and a number that has been tuned until it looked good.

### L3.9 — Library versioning and expansion

**Purpose.** Bring the athlete-authored 1 074-exercise library into the project without breaking anything built on the 27-exercise one.

**Why versioning comes first.** The library is an input to dataset generation, and `generation_config.json` pins the seed, the commit and every simulator constant but *not* the library. Nineteen of the twenty-seven v0 exercise IDs do not exist in v1 — `bench_press` became `barbell_bench_press` — so swapping the file does not subtly perturb the synthetic dataset, it invalidates it. The synthetic dataset must pin the library version and digest it was generated against, and Layer 1's byte-identical reproducibility check must verify that pin.

**What the library needs.** Validation found it schema-exact: no duplicate IDs, every movement pattern, equipment, exercise kind, Nuzzo curve and coefficient source recognised, every numeric field in range, every exercise carrying a primary muscle. Two things to resolve:

- **Twelve muscle labels outside the model taxonomy.** Three are our own display labels in a different spelling (`upper_chest`, `obliques`, `abductors`). The rest fold into existing groups per D16. The display layer keeps the finer label; the model does not gain a dimension.
- **Fifty-seven `reps_only` exercises with no bodyweight fraction** — band and suspension work. These yield dose but no effective load and therefore no performance observation. Correct for a resistance band, probably wrong for `ring_fly`. Each needs a fraction or an explicit decision that it has none.

**Validated by.** `tools/validate_library.py` and `tools/derivation_check.py` over all 1 074 rows; the v0 dataset still regenerating byte-identically with its pinned library; and every muscle label resolving to a model group.

### L3.10 — Exercise vocabulary mapping

**Purpose.** Resolve the exercise names in the athlete's Spotr log to library IDs, and freeze the result before anything runs.

**The disclosure, declared rather than avoided.** The engine cannot run on a log whose exercise vocabulary it has not seen, so this stage looks at the sealed data. The extraction is bounded to the **sorted distinct exercise-name strings** and nothing else — no counts, no dates, no loads, no repetitions, no session order. Frequencies are excluded deliberately: knowing which exercises the athlete trains most would let library curation be steered toward them, which is tuning through the back door.

**Why matching is proposed, not decided.** Automated name matching fails on exactly the cases that matter — "Chest Press" is machine or barbell, with different systemic cost, axial load and stabiliser tags, and a fuzzy match will pick one confidently. So the tool proposes, the athlete reviews every row, and the reviewed file is committed and frozen. L3.12 then makes no decisions; it reads a mapping that already exists.

**Names with no match are derived, never dropped.** The derivation path built at L0.3 gives an unmatched exercise coefficients from its muscle tags and equipment, and the confidence system built at L2.6 already docks dose quality for a derived coefficient. Silently discarding unmatched sets would delete training load from the athlete's history without saying so.

**Validated by.** Every distinct name in the log resolving to either a library ID or a derived exercise; the frozen mapping being a committed artefact with a digest; and a test that the run refuses to proceed on an unreviewed mapping.

### L3.11 — Real-data ingest adapter

**Purpose.** Read the Spotr SQLite archive and the Oura trends export into the engine's own schema.

**Scope: this athlete, not the product.** The Spotr archive exists only because
it was scraped from a device export; no user will arrive with one. This adapter
is validation scaffolding for L3.12 and nothing else. General import — from
Hevy, Strong or a CSV — is a genuine product feature and belongs in Layer 6,
where it also happens to shorten the capacity warm-up for anyone switching from
another logger. It is not a mitigation the engine may assume.

**Written against the schema, not the values.** The adapter is developed against the table structure and column types, with the synthetic dataset re-expressed in Spotr's shape as its test fixture. That keeps the L3.12 seal intact while the parsing code is debugged, which is where most of the work is.

**What it must handle.** Set types the logger records differently from ours; effort logged as RPE, RIR, or not at all; exercises substituted mid-programme; sessions with no wearable night attached; and the first six weeks of Oura data consumed warming up the 42-day baselines.

**Validated by.** Round-tripping the synthetic dataset through the Spotr schema and back with no loss; the existing L2.1 parser's reject-and-repair rules applying unchanged; and no field being invented where the source has none.

### The validation regime changes once logging is continuous

The ~99 historical sessions are a **one-shot** resource: opened once, and any
model change made after looking at them consumes them. That framing shaped
every sequencing decision above.

It stops being the whole picture the moment the athlete is logging daily with
Oura attached. At roughly five sessions a week, three months produces about
sixty sessions that **did not exist when the model was frozen** — and data that
did not exist cannot have been fitted to.

**This is prospective validation, and it is stronger than a holdout split.** A
random holdout can leak through a hundred small decisions; data from the future
cannot leak at all. It also renews, which the 99 do not.

So the regime becomes:

| Resource | Role |
|---|---|
| Synthetic dataset | the sandbox — iterate freely, it is generated on demand |
| ~99 historical sessions | **warm start**, and the L3.12 cold run. Seeds capacity so the athlete does not spend twenty weeks per exercise in the warm-up regime |
| Everything logged after a model freeze | the recurring exam, on material that did not exist when the model was written |

**What this requires of the software.** Every model version must be stamped
with the date it was frozen, and every evaluation must state which sessions
post-date that stamp. Without that the regime is a claim rather than a
procedure, and the temptation to quietly include a session from before the
freeze is exactly the kind of thing that needs to be impossible rather than
discouraged. `rhome_eval.window` already does this for the synthetic holdout;
the same mechanism extends.

**What it does not require.** It does not require rushing Layer 6. The athlete
is logging in Spotr today and Oura is recording regardless, so the data
accumulates whether or not our logger exists; L3.11's importer reaches it
either way. The one thing that would change this is discovering at L3.10 or
L3.11 that Spotr does not record a field the engine needs — set type or effort
granularity being the likely candidates. If that turns up, a minimal logger
moves up the order, because a missing field cannot be recovered later.

### L3.12 — Real-data cold run

**Purpose.** Run the engine, once, against the athlete's own recorded training and Oura history — approximately 99 sessions with matching wearable data.

**Why this is separate from everything above it.** The synthetic dataset can answer a question no real data can: whether the engine recovers latent state, since only a simulator knows the truth. Real data answers the question no simulator can: whether the engine survives real RPE reporting habits, real wearable noise, real illness, travel, and missed sessions that happened for reasons nobody recorded.

**The discipline, which matters more here than anywhere else.** There is one athlete and one such dataset. It must not be seen — by the model author or by any tooling — before the engine is complete and the synthetic evaluation has passed. Data seen during development is data tuned against, whether or not anyone intends it.

Concretely: the export is frozen before the engine is finished; nothing reads it except the bounded name-only extraction at L3.10; the run happens once; and results are recorded whatever they are. If the engine performs poorly, that is a finding, and any subsequent fix must be reported as having consumed the real holdout.

**What this dataset can support.**

- One-step-ahead performance residuals and their bias. This is the strongest available test and `DATA.md` §19.2 already names it the severe criterion: a model that fits history but predicts the next session badly fails regardless of how plausible its fatigue curves look.
- Ranking behaviour: do sessions the athlete recalls as hard rank as hard?
- Robustness: missing wearable nights, missed sessions, exercise substitutions.
- Whether confidence falls where it should.

**What it cannot support.**

- Latent-state reconstruction. Nobody knows the athlete's true hamstring fatigue, so there is nothing to score against.
- Reliable per-muscle half-life estimation. Sixteen parameters from ~99 sessions with heavy confounding is thin, and any estimate should be reported with its uncertainty rather than adopted.
- The first six weeks of wearable data, which are consumed warming up the 42-day rolling baselines.

**Preparation, already done.** The export is sealed in `data/real/` with its checksums committed and unread; `tools/seal_real_data.py verify` proves at run time that the files have not moved since. The library expansion, the vocabulary mapping and the ingest adapter are L3.9 to L3.11, so that by the time this stage runs, nothing is left to decide. The data is not tidied: the messiness is part of what is being tested.

### ▣ Checkpoint 3

The v0 scorecard: all ten success criteria from `PRODUCT.md` §14, marked pass or fail, with evidence — plus the real-data cold-run result, reported separately. This is the point at which the model is either ready to drive a product or is not.

---

# Layer 4 — Personalisation

**Purpose:** learn Athlete A's own parameters from their history, rather than using population priors.

Planned at lower resolution deliberately. The right approach depends heavily on what L3 reveals about which parameters are identifiable at all, and planning it in detail now would be false precision.

Anticipated scope: muscle-specific half-lives, RIR bias by exercise, the fatigue-to-performance coefficients, recovery-context weights, exercise-specific rep curves, and the open question recorded in docs v0.2 — whether the adaptation state carries any predictive information about capacity beyond recent observed performance.

Every personalised parameter must beat its population prior on held-out data before it is adopted.

**Personalisation is continuous, not a switch.** Every parameter starts at its
population prior from `RESEARCH.md` and moves toward the individual estimate as
that individual's evidence accumulates — partial pooling, which is what the
hierarchical extension in `MODEL.tex` §Personalisation buys. A user with twenty
sessions keeps almost every prior and still gets a working model; a user with
two years moves most of the way. Nothing is gated behind a data threshold and
nothing is switched on at one.

The rule that every personalised parameter must beat its prior on held-out data
is what makes this safe rather than a promise. For a new user almost nothing
will beat its prior, so almost nothing changes — and that is the guard working,
not the feature failing.

Data requirements differ enormously by parameter, which is why this is per
parameter rather than per user:

| Parameter | Realistically identifiable from |
|---|---|
| RIR bias per exercise | tens of sets — the fastest to personalise |
| Capacity learning rate and Huber clip | a few months of one exercise |
| λ_F, λ_N, λ_G performance sensitivities | a few months across several exercises |
| Recovery-context coefficients | a few months of wearable nights |
| Sixteen muscle-specific half-lives | thin from one person's record at any length; report with uncertainty, adopt cautiously |

**The athlete's own history is for validating and personalising, never for
designing.** Fitting *their* half-lives, RIR bias and performance sensitivities
inside a design that has already passed the synthetic evaluation is
personalisation, and it is the point of this layer. Adjusting the design until
their data looks better is not, and it would consume the only real-world check
this project gets. The distinction is not a matter of degree: one happens after
L3.12 and is validated on held-out portions of their own record, the other
happens before it and destroys the evidence.

---

### L5.3 — Non-linear fatigue accumulation *(specified here, evaluated against a frozen baseline)*

**The engine is linear and should not be.** Ten sets deposit exactly ten times
one set. Fatigue is not like that: the eighth set of a session lands on tissue
the first seven have already fatigued, and costs more for it. The ranking tests
at L3.4 measured the consequence — the engine gets every ordering right and
expresses only 67% of the true contrast, because the simulator has curvature it
cannot represent.

**Why it was linear, and why that reason has expired.** `MODEL.tex`
§Simulator versus inference engine lists "non-linear fatigue accumulation"
among the properties *the simulator* must have so that the two are not
algebraic mirrors. The linearity was an inverse-crime precaution taken during
development, not a claim about physiology. Its job was to make Layer 3's
evaluation mean something, and Layer 3 has now done that.

**What it must not become.** Copying the simulator's form — impulse multiplied
by one plus a coefficient times current local state — would create exactly the
inverse crime the precaution existed to prevent, and every number measured
afterwards would be worthless. The engine's curvature must be structurally
different.

The candidate: amplify by **position within the session** rather than by state.
A set's impulse scales with how many dose-bearing sets that muscle has already
taken in the same session, saturating. That agrees qualitatively — later sets
cost more — and differs mechanically: one reads a hidden state, the other
counts something the log always records. It is also the more identifiable of
the two from a real training log, where the state is never observed and the set
index always is.

**It does not break the explanation trace.** The amplification is decided when
the impulse is deposited, and the ledger records the amplified value, so
contributions still sum to one exactly. The exactness in `MODEL.tex`
§Exact contribution decomposition depends on *decay* being linear, which it
remains, not on deposition being state-independent.

**Sequencing, which matters more than the change.** This lands **after
Checkpoint 3**, against a frozen v0 baseline, and must be shown to pay for
itself:

- the L3.4 contrast ratios move toward 1.0;
- one-step-ahead MAE does not worsen on the settled ablation;
- the trace's shares still sum to one;
- scenario S11 robustness is unaffected.

Adding it now would invalidate every number L3.1 to L3.4 produced and leave no
baseline to compare against. The point of measuring the linear model honestly
first is to be able to prove the curvature earned its place rather than assume
it, which is the same discipline the ablation ladder imposes everywhere else.

### L5.2 — Attribution of autonomic deviation *(deferred, specified here)*

**The problem, found at L3.3.** During the illness block the engine over-predicts
suppression by +0.0254 ± 0.0201: autonomic signals degrade, ρ falls, fatigue is
held elevated, while the athlete — who has cut volume — is muscularly fresher
than the engine believes. It reads a wearable deterioration as training load,
the confusion `RESEARCH.md` §12 exists to warn against.

**Why detection is the wrong shape of fix.** Classifying illness from wearables
is feasible and is what a ring vendor does, but it is a *diagnosis*, and
`RESEARCH.md` §17 forbids "your wearable proves you are ill". It also solves
one case. Travel, a poor week's sleep, a stressful fortnight, a new baby and a
hangover all produce the same failure and would each need their own classifier.

**The better mechanism, and the engine already computes its input.** L2.3 built
a conditional autonomic expectation: how far the readings sit from what recent
training predicts. Measured over the development window, that residual
separates the two cases cleanly —

| | Unexplained RMS | Ratio to ordinary |
|---|---:|---:|
| Ordinary days | 1.042 | 1.00 |
| **High-volume block** | **0.867** | **0.83** |
| Travel | 1.237 | 1.19 |
| Illness | 1.442 | 1.38 |
| Sleep restriction | 1.443 | 1.38 |

When the wearable is reacting to training, the residual *falls*, because the
conditional model explains it. When it is reacting to something else, it rises.

So: **shrink ρ toward neutral in proportion to the unexplained deviation.** ρ is
a training-recovery multiplier; an autonomic movement that training cannot
explain should not be treated as training fatigue. No classifier, no diagnosis,
no claim boundary crossed — the statement is only "this is not explained by
your training", which is exactly what was measured.

**One refinement it needs.** Sleep restriction raises the residual just as much
as illness, and short sleep is a *legitimate* recovery signal that should slow
recovery. The expectation must therefore be conditioned on the directly observed
inputs — sleep duration and efficiency — as well as on training, so that only
what neither explains drives the shrinkage. Without that, the mechanism would
correctly ignore illness and wrongly ignore a bad week's sleep.

**Validated by.** The illness block's residual difference falling inside its
interval; the high-volume and deload responses unchanged; and the
sleep-restriction block *not* losing its ρ suppression.

**Deferred deliberately.** The engine works and this is a refinement of one
episode measured over 22 sets. It belongs after the product exists and after
the same effect has been looked for in the athlete's own record, where illness
and travel are real rather than simulated.

**The athlete's refinement, recorded 25 August 2026 and not yet implemented.**
ρ-shrinkage is the right mechanism but it is not the whole shape. Illness is
systemic, so it should also enter as a *uniform* knock-down applied across all
muscle groups at whatever level they currently sit — not absorbed into any
muscle's local fatigue, which is what the engine does today.

The value of stating it this way is that it makes the two causes separable by
their **shape across muscles**, not by a classifier:

| pattern across muscle groups | reading |
|---|---|
| uneven, and it tracks the training log | training fatigue |
| flat, across muscles that were not trained | something else — illness, travel, a bad week |

That is the same structure the L3.x directional fatigue test relies on, seen
from the other side: differential knock-down is what validates the fatigue
model, uniform knock-down is what identifies illness. Building either gets much
of the other.

It also matters for the change-scored criterion. Without an explicit global
term there is nowhere for an illness week to go except into local fatigue,
which is precisely how a model learns to call illness "training fatigue" while
its score improves.

Still deferred, and still for the reason above: this needs real episodes in the
athlete's own forward record, not simulated ones.

### L5.4 — Hierarchical capacity *(specified here, deferred)*

**The problem, measured on the athlete's log at L3.14.** Capacity is estimated
per exercise, and after the equipment split, per exercise *per gym*. That
fragments 99 sessions into ~40 identities holding about 2.5 sessions each. The
median exercise has **4.5 sessions**; half have fewer than five. Combined with
the 2.1% per-session movement cap that D23 requires, a 25% level error needs
~13 sessions to close and the typical identity never gets them. The engine sits
systematically low and cannot climb out.

**Why this is not fixed by loosening the cap.** The cap is what makes the
estimator robust, and it was approved as a product non-inferiority floor. The
level problem is a *data* problem wearing a parameter's clothes.

**The mechanism: three levels, each borrowing from the one above.**

| level | what it estimates | evidence available | appears |
|---|---|---:|---|
| muscle-group trend | broad strength direction | 27–65 sessions | almost at once |
| exercise offset | this movement against that trend | a few sessions | weeks |
| equipment-context offset | this machine's labelling against the movement | one session | when seen |

Each level is one number relative to the level above, so a new exercise or a
new gym inherits the whole history instead of restarting. Today a new context
gets only a weak 0.25 exercise-level prior — it partially starts over.

**What the pooling is worth**, from the athlete's log:

| muscle | exercises | typical sessions per exercise | sessions hitting the muscle | gain |
|---|---:|---:|---:|---:|
| quads | 7 | 2.0 | 25 | 12.5× |
| upper back | 7 | 4.0 | 30 | 7.5× |
| glutes | 7 | 4.0 | 26 | 6.5× |
| lats | 8 | 5.0 | 27 | 5.4× |
| chest | 10 | 10.5 | 48 | 4.6× |

**Deferred, with the reason.** Change-scoring takes the level from a trivial
rolling reference per exercise, so the model no longer needs to supply it. That
removes the urgency without removing the problem: hierarchical capacity is what
per-movement prediction will need when it eventually comes off the shelf, and
it is what turns "hidden until 20+ observations" into a ramp rather than a
cliff. It is not on the critical path to a usable prototype.

**One thing it cannot fix.** On cable and machine work the best possible naive
predictor is still off by 0.1657 against 0.0976 on free weights, because a
stack marked 14 means different things in different rooms. That gap closes only
by recording the machine at logging time, never retrospectively.

# Layer 6 — The application

**Purpose:** a working app the athlete uses daily — logging sessions, Oura
connected by API, the engine running live on real input.

Deliberately last, and deliberately outlined only. Everything above produces a
model that can be trusted; this produces something that can be used. Building
it earlier would mean building an interface around numbers whose behaviour was
not yet known, and the confidence and trace work at L2.6–L2.7 exists precisely
so that the interface has something honest to display.

Anticipated scope: a session logger matching the athlete's own granularity
(`PRODUCT.md` §6.8); Oura API ingestion replacing the CSV export path built at
L3.11; the engine running as a service with the day loop driven by real
timestamps rather than the fixed waking and training hours L2.5 assumes; and
the Today screen, whose driver strings and widening projection bands are
already specified and tested.

Two things from earlier layers become load-bearing here rather than
theoretical: the explanation trace, because every displayed number must expand
into what produced it; and the claim boundaries, because product copy is where
`RESEARCH.md` §17 was always aimed.

---

# Layer 5 — Product surface

**Purpose:** the application. Also planned at lower resolution, for the same reason.

Anticipated order: the library expansion below; then a stable engine API; then the five screens in the order Today, Load, Recovery, Performance, Projection; then Oura integration; then a native logger only if no reliable third-party workout integration exists.

The claim boundaries in `RESEARCH.md` §17 become user-facing copy constraints here, and should be enforced by test rather than by review.

### L5.1 — Exercise library expansion

**Purpose.** Grow the curated library from the ~27 exercises the synthetic athlete needs to the several hundred a real training log requires.

**Why here and not earlier.** Athlete A is one person over two years, and a real lifter cycles through 20–40 movements in that time. Loading three hundred exercises into the simulator would make the generated data *less* realistic, not more. L1, L2 and L3 all run against Athlete A and are indifferent to library size. The first thing that genuinely needs a large library is a real person logging a real workout.

**How it scales.** The derivation built in L0.3 is not only for user-created exercises; it is also the bulk-import mechanism.

1. Import the base layer — names, movement patterns, equipment, rough muscle tags — from an open exercise dataset. Commodity data.
2. Run the derivation across all of it to generate the scoring layer automatically.
3. Hand-curate the high-frequency movements, realistically the 40–60 exercises that cover most training. This is the actual work, and it is bounded.
4. Leave the long tail marked `derived`, which reports lower confidence through the dose-quality component rather than claiming precision it does not have.

The result is a mixed library: curated where it matters, derived where it does not, and honest about which is which. This is why `coefficient_source` exists as a field rather than being assumed.

**Validated by.** Every imported exercise passing the same schema validation as the curated set; coverage of all 16 model groups preserved; spot-checking derived coefficients for the highest-frequency imports against hand assignment; and confirmation that confidence falls appropriately for a session built from derived exercises.

**Can be pulled forward.** This stage is data authoring rather than engine work, and it blocks nothing before L5. It can be brought forward at any point if a larger library would be useful for its own sake — for example to stress-test the derivation at a scale a 27-row library cannot.

---

## 6. Scale and pacing

Roughly 39 stages, weighted towards L1 and L2. Individually small; collectively substantial.

**Proposed working rhythm:**

- I build one stage at a time and report at the end of each: what was built, what was validated, what the results were. Short — a few paragraphs.
- I do not proceed past a **checkpoint** without your explicit sign-off.
- Any deviation from the specification stops work and comes to you, rather than being absorbed quietly. If the specification turns out to be wrong, we change the specification and bump its version, per the implementation rule in the docs README.
- You can interrupt, redirect or ask for more depth at any point.

**The rule that matters most:** if a stage cannot be validated, it does not pass, and the layer does not proceed. A stage that "seems to work" is a stage that has not been checked.
