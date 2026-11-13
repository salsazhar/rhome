# Rhome — Synthetic Data Specification

**Document version:** 0.10.0
**Target dataset version:** 0.1.0 (not yet generated)  
**Date:** 26 August 2026  
**Status:** Canonical data-generation specification

> **Two version numbers.** *Document version* tracks this specification. *Dataset version* tracks a generated artefact and follows the scheme in §21. They move independently: a clarification here bumps only the document version, while a regeneration bumps only the dataset version.

## 1. Purpose

Rhome v0 will be developed and evaluated using a **fully synthetic longitudinal dataset**.

The purpose of the dataset is not to impersonate a real cohort. It is to create a controlled but realistically noisy environment in which:

- the simulator knows the athlete's latent physiological/training state;
- the inference engine receives only data that a real application could plausibly observe;
- model behaviour can be tested against known ground truth;
- difficult scenarios can be inserted deliberately;
- no external dataset schema or missing variable determines the product architecture.

The synthetic dataset is the **sole model-building dataset for v0**. Published research is used to constrain generative assumptions and model priors, not as training data.

## 2. Core rule: simulator and engine are separate

The simulator and inference engine must be implemented as separate packages/modules.

### Simulator knows

- true muscle-specific fatigue;
- true systemic fatigue;
- true neuromuscular strain;
- true adaptive state;
- true neutral exercise-performance capacity;
- true fatigue-adjusted expressible performance before random observation noise;
- true recovery propensity;
- true RIR;
- unobserved daily disturbances;
- scenario labels.

### Inference engine sees only

- logged exercise/set data;
- logged RPE/RIR;
- timestamps;
- exercise metadata;
- wearable-like sleep/autonomic/activity measurements;
- optional body mass.

The engine must never read simulator-only latent-state columns or scenario labels.

## 3. Athlete A: principal synthetic athlete

Athlete A is the canonical development case.

### 3.1 General profile

Athlete A is a healthy, resistance-trained adult whose programme combines strength and hypertrophy training.

The synthetic profile is deliberately not a powerlifter, bodybuilder or endurance athlete. The objective is a broad resistance-training distribution containing:

- heavy compound work;
- moderate-repetition compounds;
- isolation work;
- near-failure and submaximal work;
- regular progression;
- realistic exercise substitutions;
- occasional cardio/activity stress.

### 3.2 Upper/lower emphasis

**Upper- and lower-body training emphasis must be approximately even.**

This is a hard requirement.

Across every ordinary rolling four-week block:

- upper-body primary effective-set stimulus and lower-body primary effective-set stimulus should remain within approximately **±10%** of one another;
- deviations are permitted during explicitly labelled overload, injury/illness simulation, travel or deload scenarios;
- the simulator must not implicitly privilege upper-body development in its exercise pool, performance progression or recovery scenarios.

The weekly template is ordinarily:

1. Upper A
2. Lower A
3. Rest / activity
4. Upper B
5. Lower B
6. Full body / mixed
7. Rest / activity

This produces approximately five lifting sessions per week while retaining explicit upper/lower parity. Some weeks shift session days or omit/shorten sessions.

## 4. Dataset duration and scale

### 4.1 Duration

- **730 consecutive days** (approximately two years).

### 4.2 Expected size

Target ranges:

- 470–510 lifting sessions;
- 14–18 working sets per ordinary lifting session;
- approximately **7,500–8,500 working sets**;
- 730 daily recovery rows;
- body mass on most days, but with realistic missingness;
- occasional structured cardio sessions;
- daily step counts.

The exact count should emerge from the generative schedule rather than being forced to an exact integer.

## 5. Observable tables

The public synthetic dataset consists of the following tables.

## 5.1 `daily_recovery.csv`

One row per calendar day.

| Field | Type | Description |
|---|---|---|
| `date` | date | Calendar date |
| `sleep_start` | datetime | Main sleep start |
| `sleep_end` | datetime | Main sleep end |
| `total_sleep_min` | float | Total sleep time |
| `sleep_efficiency` | float | Fraction or percentage |
| `rem_sleep_min` | float | Synthetic Oura-like REM duration |
| `deep_sleep_min` | float | Synthetic Oura-like deep duration |
| `hrv_rmssd_ms` | float | Nightly RMSSD |
| `resting_hr_bpm` | float | Nightly/resting HR |
| `temperature_deviation_c` | float | Deviation from personal baseline |
| `steps` | integer | Daily steps |
| `active_minutes` | float | Optional general activity measure |
| `bodyweight_kg` | float/null | Optional body mass |
| `oura_like_readiness` | integer/null | Synthetic composite retained for display/validation only |
| `oura_like_sleep_score` | integer/null | Synthetic composite retained for display only |
| `wearable_missingness` | categorical | none / partial / full |

**Important:** `oura_like_readiness` must not be used by the v0 inference engine as a primary predictor because it is deliberately generated from overlapping underlying variables.

## 5.2 `workouts.csv`

One row per lifting or structured cardio session.

| Field | Type | Description |
|---|---|---|
| `workout_id` | string | Stable unique ID |
| `date` | date | Session date |
| `start_time` | datetime | Session start |
| `duration_min` | float | Total session duration |
| `session_type` | categorical | upper_a / lower_a / upper_b / lower_b / full_body / cardio / other |
| `planned_session` | boolean | Whether session followed original weekly plan |
| `session_rpe` | float/null | Optional post-session global RPE |
| `notes_code` | categorical/null | machine_unavailable / shortened / travel / etc. |

## 5.3 `sets.csv`

One row per set.

| Field | Type | Description |
|---|---|---|
| `workout_id` | string | Foreign key |
| `exercise_id` | string | Foreign key |
| `set_number` | integer | Set order within exercise |
| `set_type` | categorical | warmup / working / backoff / drop |
| `external_load_kg` | float | Logged external load |
| `reps` | integer | Completed repetitions |
| `rpe` | float/null | Logged RPE |
| `rir` | float/null | Logged RIR if logger is configured for RIR |
| `is_pr` | boolean | Observable PR flag based on prior logs, not latent truth |

Both RPE and RIR need not be populated simultaneously. The canonical v0 dataset records **whole-number RIR** as the primary field, with RPE derivable as `10 - RIR`, because that is what the athlete's logger accepts. A minority of RPE-only entries should be included to test input normalisation, since other loggers record effort that way.

#### `set_type` semantics

The generator must produce all four types, because each exercises a different engine rule (see the set-type section of `MODEL.tex`).

| `set_type` | Generation requirement |
|---|---|
| `warmup` | Present on most compound exercises; plausible ramping load and reps; never counted as working dose |
| `working` | The bulk of the dataset |
| `backoff` | Follows top sets on compounds at reduced load; ordinary working sets in every respect |
| `drop` | Occasional, principally on isolation work; consecutive `set_number`s within one exercise, each segment its own row |

Drop segments must appear often enough to be evaluable — roughly 1–3% of all sets is sufficient — and must be generated with genuinely pre-fatigued performance, so that a naive engine treating them as fresh sets would visibly mis-estimate capacity. This is a deliberate trap for the inference engine, and the engine is required to avoid it by excluding drop segments from performance estimation.

## 5.4 `exercise_metadata.csv`

One row per exercise.

| Field | Type | Description |
|---|---|---|
| `exercise_id` | string | Stable ID |
| `name` | string | Display name |
| `movement_pattern` | categorical | horizontal_push, hinge, squat, etc. |
| `equipment` | categorical | barbell, dumbbell, machine, cable, bodyweight |
| `primary_muscles` | array/string | Canonical muscle IDs |
| `secondary_muscles` | array/string | Canonical muscle IDs |
| `stabiliser_muscles` | array/string | Optional |
| `stimulus_primary_coeff` | float | Default 1.0 |
| `stimulus_secondary_coeff` | float | Default 0.5 |
| `fatigue_stabiliser_coeff` | float | Default 0.2 |
| `compoundness` | float | 0–1 neuromuscular coefficient |
| `systemic_cost` | float | 0–1 large-muscle/systemic coefficient |
| `axial_load` | float | Optional 0–1 descriptor |
| `eccentric_demand` | float | Optional 0–1 descriptor |
| `bodyweight_fraction` | float/null | Effective body-mass contribution if relevant; see below |
| `nuzzo_curve` | categorical | general / bench / leg_press |
| `unilateral` | boolean | Whether loads and capacity are expressed per working limb |
| `exercise_kind` | categorical | Measurement form; see §5.4.1 |
| `coefficient_source` | categorical | curated / derived; see §5.4.2 |
| `tertiary_muscles` | array/string | Display alias for `stabiliser_muscles` |

### 5.4.1 Exercise kinds

A logger must accept movements that are not load × repetitions. The `exercise_kind` field records the measurement form, and determines whether the exercise can enter the resistance dose model at all.

| `exercise_kind` | Example | v0 dose model | Reason |
|---|---|---|---|
| `weighted_reps` | Barbell bench press | Full | The core case |
| `reps_only` | Pull-up, hanging leg raise | Full | Body mass via `bodyweight_fraction` |
| `assisted_reps` | Assisted dip | Full | Negative external load |
| `time_only` | Plank | Recorded, excluded | No repetitions, so no reps-to-failure and no relative intensity |
| `weight_time` | Loaded carry | Recorded, excluded | As above |
| `weight_distance` | Sled push | Recorded, excluded | As above |
| `distance_time` | Running, rowing | Activity channel | Conditioning, not resistance volume |

Exclusion works exactly as it does for warm-up sets: the row is stored, appears in the log and contributes to session context, but produces no impulse in any of the four dose channels.

This is a v0 boundary, not a permanent one. The relative-intensity mapping is *defined* on repetitions, so time- and distance-based work needs a separate effort model rather than an extension of the existing one. Recording the field now means adding that model later requires no schema migration.

The v0 Athlete A dataset contains `weighted_reps`, `reps_only` and `assisted_reps` only.

### 5.4.2 Curated and derived coefficients

Rhome's exercise database has two layers.

The **base layer** — name, movement pattern, equipment, muscle tags — is commodity data and may be imported from any standard exercise list.

The **scoring layer** — `compoundness`, `systemic_cost`, the contribution vectors and `bodyweight_fraction` — is specific to this model. It is what turns a logged movement into a dose, and no external source provides it.

Curated exercises have a hand-assigned scoring layer. User-created exercises do not, and cannot: a person tagging a new movement supplies muscles, not coefficients. Their coefficients are therefore **derived** from the base layer, as specified in `MODEL.tex`.

Every exercise records which it is. Derived coefficients reduce confidence through the dose-quality component, so a state built largely from user-created exercises reports that fact rather than presenting the same certainty as one built from the curated library.

The v0 dataset is entirely `curated`. The derivation rules are implemented and tested against the curated library — by deriving coefficients for exercises whose true values are known and measuring the error — but no generated data depends on them.

`bodyweight_fraction` ($\beta$) is the fraction of body mass forming part of the resistance. v0 values: pull-up/chin-up 1.00, weighted dip 0.95, push-up 0.65, back extension 0.55, Bulgarian split squat 0.85 (per working limb). It is null for conventional externally loaded exercises. These are engineering priors from gross segmental mass distribution and live in metadata precisely so they can be revised without code changes.

Because effective load for these exercises is $\beta \times \text{bodyweight} + \text{external load}$, the simulator must use body mass when generating true performance demand, and body-mass changes across the two years will legitimately move pull-up and dip performance even at constant external load.

## 5.5 `performance_tests.csv`

Optional sparse table containing deliberately standardised tests or anchor sets.

Examples:

- a top set at prescribed RIR on a major compound;
- a periodic AMRAP stopped at technical failure;
- a low-fatigue single used as a performance anchor.

These are not required every week. Their purpose is to provide occasional relatively high-information observations for model calibration.

The engine weights these anchors roughly three times more heavily than an ordinary set when updating capacity, so the generator must earn that weight: anchor efforts are performed in a deliberately low-fatigue state (typically after a rest day or early in a session), with reduced RIR-estimation noise, and they must be distributed across the whole two years rather than clustered.

Target frequency is one anchor per major exercise every 3–6 weeks, yielding roughly 60–120 anchor observations across the dataset.

Anchors must include occasional near-maximal singles and doubles. These exercise the near-maximal branch of the relative-intensity mapping, which extends below the tabulated Nuzzo domain to the definitional point (1 repetition, 100% of 1RM). Without such sets that branch is never tested.

## 6. Simulator-only tables

These files exist for evaluation but **must be isolated from the application input directory**.

## 6.1 `latent_daily.csv`

One row per day containing:

- `true_fatigue_<muscle>` for every modelled muscle group;
- `true_neuromuscular_strain`;
- `true_systemic_fatigue`;
- `true_adaptation_<muscle>`;
- `true_recovery_propensity`;
- `true_performance_capacity_<major_exercise>` — neutral/low-fatigue latent capacity;
- `true_expressible_performance_<major_exercise>` — capacity after the simulator's current fatigue/recovery modulation but before stochastic performance shock;
- latent illness/stress/travel state;
- true sleep propensity;
- true autonomic baseline.

## 6.2 `latent_sets.csv`

May contain:

- true RIR;
- true relative intensity;
- true set stimulus by muscle;
- true set fatigue by muscle;
- true neuromuscular impulse;
- true systemic impulse;
- latent technique/performance disturbance;
- true pre-set expressible performance;
- stochastic performance shock applied before the observable set is generated.

## 6.3 `scenario_manifest.csv`

Contains known scenario intervals and intended effects. This is available to evaluation/test code, never to the inference engine.

## 7. Canonical muscle groups

v0 models enough anatomical resolution to be useful without pretending to resolve every muscle independently.

Rhome uses **two levels of muscle taxonomy**, and the distinction is deliberate.

### 7.1 Model groups (16)

These are the muscles the model maintains state for. Every latent column, contribution vector and stored state is keyed by these identifiers.

**Upper body (9)**

- chest;
- lats;
- upper_back;
- anterior_delts;
- lateral_delts;
- posterior_delts;
- biceps;
- triceps;
- forearms.

**Core (1)**

- abs.

**Lower body (6)**

- quads;
- hamstrings;
- glutes;
- calves;
- adductors;
- spinal_erectors.

The exercise metadata matrix, not arbitrary session labels, determines which groups receive load.

### 7.2 Display labels

A training log must let an athlete record what they think they trained. Lifters think in terms of upper chest, traps, obliques and grip; a logger offering only sixteen coarse groups would feel impoverished next to any competitor.

Rhome therefore presents a finer **display taxonomy** that maps onto the model groups:

| Display label | Model group |
|---|---|
| Upper Chest, Mid Chest, Lower Chest | `chest` |
| Lats | `lats` |
| Upper Back, Trapezius, Rhomboids | `upper_back` |
| Lower Back | `spinal_erectors` |
| Front Delts | `anterior_delts` |
| Side Delts | `lateral_delts` |
| Rear Delts | `posterior_delts` |
| Biceps | `biceps` |
| Triceps | `triceps` |
| Forearms, Grip | `forearms` |
| Upper Abs, Lower Abs, Obliques | `abs` |
| Glutes, Hip Abductors | `glutes` |
| Quadriceps | `quads` |
| Hamstrings | `hamstrings` |
| Calves | `calves` |
| Adductors | `adductors` |

The mapping is many-to-one and lives in one table. Adding a display label is a data change requiring no model change.

### 7.3 Why the model layer is coarser

This is a claim-boundary decision, not a simplification for convenience.

The evidence this model rests on operates at muscle-group resolution. Pelland et al. (2026) count direct and indirect sets per muscle; the volume dose-response literature is reported per muscle. **No part of the reviewed evidence supports modelling upper-chest fatigue as a state distinct from lower-chest fatigue**, and presenting one would be exactly the false precision `RESEARCH.md` §17 prohibits.

Splitting a group also thins the data behind each state. Regional labels would divide an already modest per-muscle set count across states that the model has no independent means of distinguishing.

The two-level design resolves the tension honestly: the athlete logs at the granularity they think in, and the model claims only what it can defend. Should evidence later support regional resolution for a specific muscle, that group can be split without disturbing the rest of the taxonomy.

### 7.4 Revisiting the split

`abs` is a single group in v0 despite anti-rotation and flexion work being plausibly different demands. This is recorded as a known simplification. Splitting `abs` from `obliques` is the most likely future refinement and should be driven by whether the engine's residuals show systematic error on rotational work, not by anatomical intuition.

## 8. Exercise pool

The dataset should contain a stable core with occasional substitutions.

### 8.1 Upper-body core

- Barbell bench press
- Incline dumbbell press
- Weighted dip
- Overhead press
- Pull-up / weighted pull-up
- Lat pulldown
- Chest-supported row
- Cable or machine row
- Lateral raise
- Rear-delt fly / reverse pec deck
- Dumbbell or cable curl
- Triceps pressdown / extension
- Wrist curl or direct grip work (low frequency)

Direct forearm work appears at low frequency, but the pool must contain it: `forearms` is a model group, and a group that can only ever be loaded indirectly could never be trained on purpose.

### 8.2 Lower-body core

- Back squat
- Front squat or hack squat
- Leg press
- Romanian deadlift
- Conventional or trap-bar deadlift (lower frequency than squat/RDL)
- Bulgarian split squat
- Leg extension
- Leg curl
- Calf raise
- Back extension
- Hip adduction as an occasional accessory

### 8.3 Core

- Cable crunch (`weighted_reps`)
- Hanging leg raise (`reps_only`, progressing to weighted)
- Ab wheel rollout (`reps_only`)

Direct core work is part of the ordinary programme rather than an afterthought. `abs` is a model group like any other and accumulates fatigue, stimulus and adaptation on the same terms; the weekly effective-set targets of §9.3 apply to it.

Loaded carries and structured conditioning are **not** part of the v0 exercise pool. Athlete A's non-resistance activity is represented by daily steps alone, as specified in §11. The `cardio` session type remains in the schema and appears rarely, so that the activity channel is exercised without conditioning becoming a material part of the training load.

### 8.4 Exercise substitutions

Substitutions should occur for plausible reasons:

- equipment unavailable;
- planned variation after a block;
- temporary discomfort without simulating injury diagnosis;
- travel gym constraints;
- novelty block.

When a new exercise is introduced, the simulator may transiently increase local fatigue/DOMS propensity through its hidden novelty mechanism.

## 9. Training distribution

## 9.1 Rep ranges

Approximate working-set distribution, measured on repetitions actually performed:

| Repetitions | Share |
|---|---:|
| 1–3 | 10–15% |
| 4–6 | 24–29% |
| 7–10 | 31–37% |
| 11–15 | 18–22% |
| 16–25 | 5–9% |

Compound lifts should be biased toward the lower/middle ranges; isolation movements toward the middle/higher ranges.

Unlike effort, repetition count carries no observation error: the athlete records exactly what they performed. These figures therefore describe the training itself, with no measurement layer between.

### 9.1.1 Why the low-repetition share exceeds the prescription

Roughly 6% of working sets are *prescribed* in the 1–3 range — heavy top sets on the squat, deadlift and bench press. The band nonetheless holds 10–15% of all sets, and the difference is not an error.

Later sets of a prescription fall short of their range under within-session fatigue. A four-set prescription at 4–6 repetitions commonly records 6, 5, 4, 3, and that final set lands in the band below. Real training logs show exactly this, and a generator that avoided it would be producing tidier data than the product will ever receive.

An earlier version of this section specified 5–8%, which implicitly assumed either no repetition drop-off across sets or a load light enough to prevent it. Both would misrepresent how the athlete actually trains. The athlete does strip weight when a set lands at the bottom of its range, which limits the leakage without eliminating it.

## 9.2 Effort distribution

Ordinary working sets should not all be maximal.

**Effort is recorded as whole-number repetitions in reserve.** This is what the athlete's logger accepts, and the granularity matters more than it appears. On the Zourdos convention each whole RIR value maps to one RPE point, so the bands below are equivalently RPE 10, 9, 8 and 7-or-lower.

### 9.2.1 Two distributions, not one

The distribution of effort the athlete *trains at* and the distribution recorded in the *log* are materially different, because reported RIR carries roughly 0.9 repetitions of estimation error (`MODEL.tex`, §From RPE to RIR). Both are specified, because they serve different purposes: the first describes the programme, the second describes the data file the inference engine will actually receive.

| Repetitions in reserve | Equivalent RPE | **True effort** | **Logged effort** |
|---|---|---:|---:|
| 0 — at failure | 10 | 10–14% | 17–25% |
| 1 | 9 | 28–33% | 22–28% |
| 2 | 8 | 35–39% | 24–28% |
| 3 or more | ≤ 7 | 18–23% | 24–35% |

Failure-heavy scenario blocks may temporarily increase the proportion at 0 RIR.

### 9.2.2 Why the logged distribution is so much flatter

This is not a defect in the generator, and the engine must not treat it as one.

An athlete training almost entirely between 1 and 2 repetitions in reserve produces a log in which every value from 0 to 4 appears substantially, because their estimate of proximity to failure is only accurate to about one repetition. Roughly a fifth of logged sets read as taken to failure when the true figure is closer to an eighth; roughly a quarter read as comfortably short when the athlete was in fact working hard.

Two consequences follow.

**No inference engine can recover the true effort distribution from the logged one.** The smearing is irreversible at the level of a single set. This is a floor on how well relative intensity can ever be estimated, and it is why `MODEL.tex` treats RIR as a noisy observation rather than as ground truth.

**The logged distribution is unavoidably flat.** An earlier version of this section specified only one distribution, with bands tight enough that reaching them on logged values would have required the athlete to train every working set at almost identical proximity to failure — contradicting §8, which prescribes heavy triples alongside isolation work taken near failure. The original figures survive as the true-effort column; the logged column records what those figures become after the estimation error this specification itself mandates.

### 9.2.3 Half-point logging

Some loggers accept RPE in half-point steps. Rhome supports it, but it is not what the v0 dataset uses, and it behaves worse: the RPE 9.5–10 band spans 0 to 0.5 RIR, so half-point logging places two reportable values inside it against one for whole numbers. The estimation-error tail then piles onto the top of the scale hard enough to make RPE 10 the single most common entry in the log, which no real training record resembles.

## 9.3 Weekly effective volume

During ordinary accumulation blocks, most major muscle groups should receive approximately **10–14 direct/fractional effective sets per week**, with natural variation.

Short overload blocks may rise to approximately 15–18 effective sets for selected muscles. Sustained volumes above ~20 should be uncommon and reserved for deliberate stress tests.

This is not a claim that 10–14 is universally optimal. It is a realistic synthetic operating region that provides enough variation to model dose and fatigue without permanently saturating the athlete.

## 9.4 Progression

Progression should arise from latent capacity and programme logic, not fixed weekly weight increments.

Possible progression rules:

- double progression within a rep range;
- add load after exceeding a rep/RPE target;
- retain load when RPE is unexpectedly high;
- occasional rep PR despite unchanged load;
- back-off after a failed progression;
- planned deload reductions in sets and/or intensity.

## 9.5 Performance-generation chain

Performance must be generated causally rather than assigned as an independent random field. For each major exercise and session, the simulator proceeds in this order:

1. evolve **true neutral performance capacity** from prior adaptation/learning history;
2. apply the simulator's true local, neuromuscular and systemic fatigue states to obtain **true expressible performance** for that moment;
3. add a bounded exercise/day-specific stochastic performance shock;
4. choose load/repetitions that are feasible under that realised performance level and the programme target;
5. derive true RIR/RPE from the realised set;
6. add RPE/RIR observation noise to create the logged value.

This ordering is essential. It creates observable sets from a hidden performance state rather than manufacturing a performance score from the same equations later used by the inference engine.

The inference engine will subsequently derive **observed performance** from the logged set using load, repetitions and RPE/RIR. It will also hold its own estimate of **underlying performance capacity** and produce a **pre-session projected performance** from that capacity plus its inferred fatigue states. These engine quantities are deliberately distinct from the simulator's hidden truth.

The source's performed set order is part of the observation and must be
preserved through ingestion. Sorting exercises alphabetically is not an
equivalent representation: the repaired engine uses the number of prior
dose-bearing sets for each muscle as an explicit within-session input.

### Anti-leakage timing rule

For every evaluable workout:

- the engine must write/freeze `projected_performance_pre_session` from information available immediately before the session;
- the workout is then revealed;
- observed performance is calculated;
- the performance residual is stored;
- only then may the engine update underlying capacity or personalised parameters.

No evaluation may recompute the projection after ingesting the target workout.

## 10. Synthetic athlete starting parameters

These are **dataset-scale parameters**, not Rhome recommendations.

Suggested starting state:

- body mass: ~80 kg;
- barbell bench estimated 1RM: ~105 kg;
- back squat estimated 1RM: ~155 kg;
- deadlift estimated 1RM: ~185 kg;
- overhead press estimated 1RM: ~65 kg;
- pull-up: comfortably trained, with weighted working sets;
- habitual steps: ~10,000/day;
- total sleep time: mean ~7.5 h;
- nocturnal RMSSD: personal baseline ~60 ms;
- resting HR: personal baseline ~52 bpm.

The exact values may be adjusted before generation. Their purpose is simply to create a trained but non-elite athlete with room for two years of plausible progression.

## 11. Recovery-data generation

Recovery variables must be correlated and state-dependent; they must **not** be sampled independently.

### 11.1 Hidden daily recovery propensity

Generate a latent daily recovery variable influenced by:

- circadian/sleep propensity;
- recent systemic training load;
- recent illness/stress state;
- travel state;
- stochastic daily disturbance.

### 11.2 Sleep

Ordinary total sleep:

- centre near 7.5 h;
- realistic night-to-night SD roughly 0.6–0.9 h;
- occasional short nights;
- occasional long recovery nights;
- serial correlation (a bad night modestly increases the chance of another bad night, but not deterministically).

Sleep efficiency should typically be high but noisy. REM/deep duration should co-vary with total sleep while retaining large stage-level noise.

### 11.3 HRV

Generate latent log-RMSSD around a slowly varying personal baseline. It should respond probabilistically to:

- poor sleep;
- systemic training stress;
- illness/stress;
- recovery rebound;
- stochastic autonomic variation.

A single hard workout must not force HRV downward every time. Some overreaching/adaptation states can produce ambiguous or even elevated vagal indices; this is deliberate.

### 11.4 Resting HR

Resting HR should be negatively but imperfectly correlated with recovery propensity and should tend to rise with:

- illness;
- substantial sleep loss;
- high systemic stress;
- some high-load blocks.

### 11.5 Temperature

Temperature deviation should usually remain close to zero, with small noise. Illness-like scenarios produce larger positive deviations. The model must not interpret every small temperature movement as pathology.

### 11.6 Measurement noise

Wearable-like observations are measurements of latent signals, not the latent signals themselves.

Suggested v0 noise:

- RMSSD: multiplicative/log-space error approximately 5–7% scale;
- resting HR: SD approximately 0.5–1.0 bpm;
- total sleep time: SD approximately 10–15 min around latent measured sleep;
- sleep efficiency: SD approximately 1–2 percentage points;
- body mass: daily water/noise SD approximately 0.5–0.9 kg around latent tissue mass.

These are engineering approximations inspired by wearable-validation literature, not fitted Oura error distributions.

## 12. Body-mass generation

Body mass is optional to the model but present in the dataset.

Separate:

1. **latent tissue/body-mass trend** — changes slowly;
2. **daily observed scale mass** — includes water/glycogen/gut-content noise.

Across two years, Athlete A may undergo modest gain/maintenance/cut phases, e.g. a net range of ~4–5 kg, but body-mass changes should not dominate the load model.

For pull-ups/dips, the simulator should use body mass plus external load when generating true performance demand.

## 13. Scenario library

The dataset must deliberately contain scenarios that test model behaviour.

Each scenario has a known intended latent effect but retains stochasticity.

### S0 — Ordinary progressive training

**Purpose:** baseline model behaviour.

Expected pattern:

- oscillating local fatigue;
- stable recovery metrics;
- slow performance improvement;
- no pathological fatigue accumulation.

### S1 — High-volume accumulation block

**Duration:** 2–4 weeks.

Manipulation:

- +20–35% sets for selected upper and lower muscle groups;
- intensity approximately stable;
- upper/lower emphasis remains balanced unless the scenario explicitly tests asymmetry.

Expected latent effect:

- greater local/systemic fatigue;
- slow fitness/adaptation continues to rise;
- transient suppression of observed performance may appear.

### S2 — Failure-heavy block

**Duration:** 7–14 days.

Manipulation:

- higher share of sets at RPE 9.5–10;
- total volume need not increase dramatically.

Expected effect:

- disproportionate acute fatigue relative to extra stimulus;
- slower 24–48 h recovery;
- greater session-to-session performance suppression.

### S3 — Deload and rebound

**Duration:** 7–10 days plus following week.

Manipulation:

- reduce set volume ~40–60%;
- retain some intensity exposure;
- avoid frequent failure.

Expected effect:

- fatigue falls rapidly;
- slower adaptation state decays little;
- observed performance rebounds and may produce PRs.

### S4 — Acute sleep restriction

**Duration:** 2–5 nights.

Manipulation:

- total sleep around 5–6 h;
- optionally late sleep restriction;
- training programme initially unchanged.

Expected effect:

- modest-to-material performance/RPE impairment probabilistically;
- HRV/RHR changes are likely but not deterministic;
- recovery decay slows modestly.

### S5 — Chronic mild sleep compression

**Duration:** 1–2 weeks.

Manipulation:

- repeated ~6–6.5 h nights rather than complete deprivation.

Expected effect:

- accumulated recovery disadvantage;
- increased subjective effort;
- more subtle than S4.

### S6 — High-step / travel block

**Duration:** 5–10 days.

Manipulation:

- 18,000–25,000 steps/day;
- irregular workout timing;
- some equipment substitutions;
- sleep may shift modestly.

Expected effect:

- small systemic and lower-limb background load;
- not equivalent to a lower-body resistance session;
- travel noise in sleep and autonomic variables.

### S7 — Mild illness-like perturbation

**Duration:** 3–6 days.

Manipulation:

- elevated temperature deviation;
- higher resting HR;
- altered HRV;
- worse sleep;
- reduced or missed training.

Expected effect:

- poor recovery context;
- suppressed performance;
- model confidence should recognise multiple concordant signals.

This is a synthetic stress test, not a medical diagnostic feature.

### S8 — Exercise novelty

**Duration:** 2–3 weeks around exercise substitution.

Manipulation:

- replace a familiar movement with a biomechanically related movement;
- hidden novelty/eccentric-fatigue modifier temporarily elevated.

Expected effect:

- more local fatigue than workload alone initially predicts;
- novelty effect decays with repeated exposures.

### S9 — Plateau

**Duration:** 4–8 weeks.

Manipulation:

- underlying performance trend nearly flat;
- ordinary training continues;
- day-to-day PR attempts occasionally fail.

Expected effect:

- engine should not hallucinate continuous linear progression.

### S10 — Excellent recovery / PR window

**Duration:** 5–10 days.

Manipulation:

- consistent adequate sleep;
- favourable HRV/RHR;
- low residual fatigue after deload or easy week.

Expected effect:

- observed performance may exceed both recent rolling trend and the pre-session projection;
- a positive prediction residual is permitted and should inform capacity only after the observation is recorded;
- model should attribute the result partly to low fatigue rather than suddenly large fitness gain.

### S11 — Random bad performance day

**Duration:** one session.

Manipulation:

- unobserved stochastic performance shock;
- a conspicuous negative observed-versus-projected residual despite otherwise ordinary latent recovery state;
- wearable data may look normal.

Expected effect:

- one poor session must not force a complete model-state collapse or falsely declare systemic under-recovery.

### S12 — Missed-session block

**Duration:** 5–12 days.

Manipulation:

- one or more planned sessions missed for non-physiological reasons.

Expected effect:

- fatigue declines;
- slow adaptation declines minimally over short gaps;
- the engine must distinguish absence of training from evidence of illness when recovery data remain normal.

## 14. Scenario placement

The final generator should use a fixed random seed and a stored scenario manifest.

Recommended broad chronology:

- Days 1–70: ordinary baseline/progressive training;
- Days 71–100: high-volume block + deload;
- Days 101–170: ordinary progression;
- Days 171–180: failure-heavy block;
- Days 181–195: deload/rebound;
- Days 196–240: ordinary progression;
- Days 241–250: acute sleep restriction;
- Days 251–310: ordinary training;
- Days 311–320: high-step/travel block;
- Days 321–370: ordinary training with exercise novelty;
- Days 371–378: mild illness-like perturbation;
- Days 379–450: ordinary progression;
- Days 451–500: plateau;
- Days 501–515: overload/failure accumulation;
- Days 516–530: deload/rebound;
- Days 531–590: ordinary progression;
- Days 591–600: excellent-recovery/PR window;
- Days 601–660: ordinary training with occasional random bad day;
- Days 661–670: missed-session block;
- Days 671–730: ordinary training/holdout finish.

The exact day numbers can be adjusted once the generator is implemented, but every required scenario must be present and documented.

## 15. Development and holdout split

To reduce hand-tuning against every known outcome:

- **Development window:** days 1–520.
- **Holdout window:** days 521–730.

The inference engine may be designed and tuned using the development window. The latent holdout states should remain inaccessible until an evaluation run.

Scenario families should appear in both windows, but exact combinations and stochastic realisations should differ.

## 16. Preventing target leakage and the inverse crime

### 16.1 Performance target leakage

A workout's observed performance cannot be used to construct its own prediction. One-step-ahead projections must be persisted from the pre-session model state. Capacity and parameter updates occur only after the residual has been scored. Holdout metrics use these frozen predictions.

### 16.2 Simulator/inference inverse crime

The simulator must be more complex than the inference model.

At minimum, the simulator should include:

- per-muscle recovery parameters sampled independently around population priors;
- non-linear fatigue accumulation with interaction between volume and proximity to failure;
- a latent day-level stress variable not directly observed;
- correlated but imperfect wearable responses;
- exercise-specific RIR bias;
- heteroskedastic performance noise (larger at high rep counts / unfamiliar exercises);
- stochastic sleep/autonomic variation;
- exercise novelty;
- occasional unexplained performance shocks.

The inference engine should not be given the random seed, latent parameters or scenario state.

## 17. Missing data

Real data will be incomplete; synthetic data must test this.

Required missingness:

- 3–5% nights with one missing wearable metric;
- ~1–2% fully missing wearable nights;
- occasional missing bodyweight blocks;
- occasional missing RPE on a set;
- very rare malformed/duplicate input rows for parser tests in a separate `raw_dirty` fixture.

Missingness must not be concentrated only in adverse scenarios.

## 18. Data realism constraints

The generator must enforce the following invariants.

### Workouts

- Loads change in realistic increments by equipment.
- RPE generally increases within repeated sets at fixed load/reps unless reps decrease or adequate adaptation/recovery offsets it.
- Impossible combinations (e.g. 20 reps at 95% true 1RM) are rejected unless explicitly generated as a deliberate corruption fixture.
- Warm-up load/reps are plausible and do not count as normal working-set dose.
- Exercise progression is smooth enough that PRs are notable events.

### Sleep/autonomic data

- Total sleep is bounded to plausible values.
- Sleep stages sum to less than or equal to total sleep.
- HRV and RHR are noisy and only partially anti-correlated.
- Illness/stress can alter both, but ordinary hard sessions do not guarantee a specific next-day direction.

### Body mass

- Tissue trend changes slowly.
- Day-to-day scale readings are noisier than tissue trend.

### Training schedule

- Five lifting sessions/week is an average, not an invariant.
- No artificial reset occurs at Monday or month boundaries.

### Temporal continuity

The generator must match the engine's temporal conventions, otherwise the two disagree about when things happened and evaluation measures that disagreement rather than model quality.

- Set timestamps are explicit and spread realistically across the session, not collapsed onto the session start.
- Latent state evolves in continuous hours. No latent quantity is recomputed or rebased at midnight.
- Daily step load is accumulated across the waking window, not applied as a single midnight impulse.
- Recovery propensity is anchored to the sleep episode. A night's physiology influences the day that follows it, never the training that preceded it.

`latent_daily.csv` reports a daily snapshot for convenience, but the underlying simulation is continuous and the snapshot timestamp must be recorded explicitly rather than implied.

## 19. Evaluation metrics

The engine is evaluated against latent state only through dedicated evaluation code.

### 19.1 State reconstruction

For each latent channel:

- Pearson/Spearman correlation;
- RMSE after agreed scale normalisation;
- directional accuracy (rising/falling);
- peak timing error after high-load sessions;
- recovery-crossing timing error.

**Per-muscle claims are scored cross-sectionally as well as longitudinally.**
A longitudinal correlation per muscle is dominated by "was this athlete
training recently", which is common to all sixteen and therefore free. The
claim the body map actually makes is an ordering *between* muscles on a given
day. So per-muscle local fatigue additionally reports the correlation between
the engine's and the simulator's day-centred muscle vectors — day means
removed from both sides — pooled across muscle-days and averaged per day.

On the development window 74% of true latent local-fatigue variance is
within-day between-muscle and 26% is between-day, so the cross-sectional
figure is the majority of what there is to reconstruct.

**Every per-muscle figure carries a competitor that shares the muscle map.**
Under D23 a trivial competitor is given every structure the engine is not
claiming credit for, and the exercise-to-muscle contribution matrix is
authored data rather than an inference. A per-muscle score reported only
against an unattributed global accumulator is not a result: that comparison
measures the absence of a lookup table. The required competitor is a decaying
per-muscle counter weighted by `c^F`, carrying no repetitions, effort,
novelty, wearable or recovery-context information.

### 19.2 Performance prediction and capacity reconstruction

For major exercises, evaluate:

- one-step-ahead MAE and RMSE for log/percentage performance residuals;
- mean residual (prediction bias) on development and holdout periods;
- correlation/RMSE between inferred underlying capacity and the simulator's true neutral capacity after scale alignment;
- calibration of residuals across inferred local-fatigue, neuromuscular-strain and systemic-fatigue bins;
- residual autocorrelation and time drift;
- directional accuracy for predicted performance suppression/rebound around high-fatigue blocks and deloads;
- robustness of the capacity estimate to a single random bad-performance day.

A model that fits historical observations but has biased or poor one-step-ahead residuals fails this criterion.

#### Joint accuracy--robustness gate

Accuracy and stability are a **lexicographic gate**, not a weighted score. A
capacity-estimator candidate is eligible for an accuracy comparison only after
it passes the frozen S11 robustness battery. A lower MAE can never compensate
for failing that battery.

For a settled estimate (at least twenty prior observations), the S11 battery
must satisfy all three limits:

| quantity | acceptance limit |
|---|---:|
| median immediate absolute capacity displacement | $\le 2.1\%$ |
| worst immediate absolute capacity displacement | $\le 3.3\%$ |
| worst absolute displacement after ninety days | $<0.5\%$ |

The immediate limits freeze the behaviour measured for v0 before the repair;
they are a product non-inferiority floor approved by the athlete, not values
derived from a candidate estimator. The ninety-day limit is the existing S11
recovery requirement. The scenario cases, horizons and settled threshold are
fixed before candidate scores are read.

Only candidates that pass all three limits are ranked by matched one-step-ahead
MAE. Every such comparison also reports RMSE and bias, and places the engine
beside `last observation`, `median of last 3` and `mean of last 5` on the same
sample. Robustness is reported beside those accuracy figures. In particular,
`last observation` adopts a one-session outlier in full and has no internal
wash-out mechanism; its immediate S11 displacement is therefore 100% of the
shock rather than zero.

Historical real-log figures are development results under D22. Passing this
gate on data that predate a model's freeze is evidence that a candidate is
admissible for prospective testing, not validation.

### 19.3 Ranking tests

The engine should correctly rank:

- failure-heavy > matched-volume non-failure fatigue;
- high-volume > ordinary-volume local fatigue;
- large lower-body compound session > arm-isolation session for systemic load;
- heavy low-rep compounds > isolation work for neuromuscular strain;
- deload week < accumulation week for acute fatigue;
- low-fatigue post-deload state > pre-deload state for expected performance.

### 19.4 Calibration targets

These are **Grade-C simulator-centred reference bands**, not measured human
physiology. Document version 0.8.0 used bands derived from the linear engine's
own coefficients; the simulator missed four of six, so agreement principally
rewarded the limitation under evaluation. Under the athlete's pre-registered
D21 option 2, version 0.9.0 centres the bands on the simulator values before
judging the repaired engine. Both columns are mandatory whenever a calibration
figure is reported.

| State, evaluated 24 h after the most recent session | v0.9 reference band | repaired engine | simulator |
|---|---:|---:|---:|
| Fresh; after a deload week | 0–1.5% | 1.11% | 1.07% |
| One ordinary hard session for that muscle | 5–7% | 5.44% | 6.00% |
| One failure-heavy session | 8–10% | 6.94% | 9.26% |
| Within an ordinary training week (two sessions in 72 h) | 7–9% | 6.82% | 8.18% |
| Within a failure-heavy block | 12–14% | 8.68% | 13.16% |
| Peak of a deliberate overload block | 24–27% | 14.14% | 25.67% |

The simulator is inside all six reference bands. The repaired engine is inside
two. That gap is an open calibration limitation, not a reason to widen the
bands: the relative contrast criterion improves while absolute accumulated
suppression remains compressed.

Upper-body suppression is expected to run roughly one percentage point below lower-body for an equivalent session, because compoundness and systemic-cost coefficients are lower. That difference is a correct prediction, not a calibration error.

Future changes may re-derive the engine's $\lambda$ coefficients against these
references and version `MODEL.tex`; the bands are not widened to fit the
engine. Human prospective performance is the eventual calibration authority,
not either synthetic column.

The numerical-stability clip on total suppression must not bind outside scenarios S1, S2 and the day-501–515 overload block. If it binds during ordinary training, that is a defect.

### 19.5 Confidence behaviour

Confidence is deterministic, so it is testable:

- confidence falls when wearable channels are withheld and recovers when they return;
- confidence in **fatigue** does *not* fall during the missed-session block (S12) — an absence of training is informative about fatigue, not a gap in evidence;
- confidence in **capacity** does fall for an exercise that has not been trained recently;
- confidence rises over the first 42 days as baselines mature, and the binding reason during that period is baseline maturity;
- the reported binding reason always matches the lowest-scoring component.

### 19.6 Explanation-trace integrity

The trace is an exact decomposition, so it can be checked exactly:

- contributor shares for any state sum to 1.0 within numerical tolerance;
- reconstructing a state from its listed contributors reproduces the reported value;
- every parameter appearing in a computation appears in the trace's parameter block, with an evidence grade;
- no driver string is emitted that is not derivable from the trace;
- no driver string violates the claim boundaries of `RESEARCH.md` §17.

The last two are enforced by test, not by review.

### 19.7 Capacity-estimator tests

- **S11 (random bad day):** one anomalously poor session produces a large negative residual, moves estimated capacity no further than the explicit session bound, and leaves no lasting displacement — under 0.5% after ninety days. All eligible sets for one exercise-context are fatigue-corrected and aggregated into one robust session target. They count as evidence, not independent capacity movements. `MODEL.tex` Eq. (session bound) limits an ordinary session to 2.1% and a session containing an anchor to 3.3%, at every maturity.

  Two corrections are recorded here rather than silently applied. Through document version 0.6.0 this clause read "**less than 1%** ... from about ten observations onward", with a profile of 3.3% at three prior observations, 1.0% at ten and 0.6% at fifteen. Both the threshold and the profile were measured by applying a **single** capacity update, while the engine applies one per eligible set and a real session carries two to five. The 1% was not an independent requirement that the engine failed; it was `MODEL.tex`'s per-*set* figure restated as a per-*session* threshold, inheriting an invalid inference corrected in `MODEL.tex` v0.5. This clause is therefore re-derived from the mechanism, not widened to fit an observed number — the distinction §19.4 draws, applied here.

  The severity of the miss is deliberately unspecified, because once the robust Huber term and session cap bind, a larger miss cannot move the estimate further. Scenario S11's own magnitude is a median 13.9% shortfall. Tests include both that miss and a 40% stand-in and require the bounded response to remain unchanged.

  The gain schedule (`MODEL.tex` §Gain schedule) may make a young estimate more responsive below the cap. It never widens the session cap itself.

  `PRODUCT.md` §14.3's requirement — "one bad session barely moves capacity" — is the criterion this clause exists to make testable. On 24 August 2026 the athlete resolved the product judgement: v0's measured median 2.1%, worst 3.3% and ninety-day displacement under 0.5% are the non-inferiority limits in §19.2. Model version 0.6 implements those product limits directly at session scale rather than relying on a per-set inference.
- **S9 (plateau):** estimated capacity stays approximately flat; the engine does not extrapolate prior progress.
- **S3/S10 (deload rebound, PR window):** post-deload performance gains are attributed principally to reduced fatigue rather than to a sudden capacity increase, verified by decomposing the projected change.
- **Drop segments and clipped high-rep sets** are confirmed absent from the capacity update.
- **Bodyweight exercises:** a simulated body-mass change moves estimated pull-up capacity in system-load units and is not misreported as a strength change.

### 19.8 Robustness tests

- one bad HRV night does not dominate state;
- one anomalously poor workout produces a negative residual but does not permanently depress underlying capacity;
- repeated systematic residuals can move capacity/parameters gradually;
- missing wearable data reduce confidence rather than fabricating fatigue;
- high steps affect lower/systemic load modestly, not as resistance volume;
- upper/lower parity remains preserved in normal training blocks.

## 20. Reproducibility

The generator must be deterministic under a fixed seed.

Recommended output directory:

```text
data/
  synthetic/
    athlete_a/
      observable/
        daily_recovery.csv
        workouts.csv
        sets.csv
        exercise_metadata.csv
        performance_tests.csv
      hidden/
        latent_daily.csv
        latent_sets.csv
        scenario_manifest.csv
      metadata/
        generation_config.json
        schema_version.json
        quality_report.json
```

`generation_config.json` must include:

- random seed;
- dataset version;
- all simulator parameters;
- scenario schedule;
- baseline athlete parameters;
- software commit hash if available.

## 21. Dataset versioning

These versions describe a generated dataset artefact, and are distinct from the document version in this file's header.

Use semantic-style dataset versions:

- `0.1.0` — first complete Athlete A generator;
- patch — bug fixes that do not materially alter statistical design;
- minor — new scenario/field or changed parameterisation;
- major — changed simulator architecture or schema.

Model results should always report the dataset version against which they were evaluated.

## 22. What this dataset can and cannot validate

The synthetic dataset can validate that:

- the engine is internally coherent;
- the engine can recover known latent structure under noise;
- pre-session performance projections can be scored without target leakage;
- observed-versus-projected residuals are approximately unbiased when the engine is well specified;
- projections behave sensibly;
- edge cases do not break the model;
- model components are identifiable enough to be useful.

It **cannot** prove that a numerical fatigue index corresponds to a literal biological quantity in humans.

`PRODUCT.md` §15 sets out the full validation logic connecting this dataset to real data: what the synthetic phase establishes, what only real data can establish, which observables are scoreable on a real person and which are inputs only, and the ablation ladder each model component must beat before it is kept. Real longitudinal data are still required for external calibration and validation. The synthetic phase is an engineering and model-identifiability test, not clinical or physiological validation.
