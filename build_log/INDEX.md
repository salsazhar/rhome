# Build log — index

One row per stage. Every stage is exactly one git commit carrying its stage ID,
so this table and the git history describe the same events.

**Status key:** ✅ passed · ⚠️ passed with notes · ⛔ blocked · ⬜ not started

## Layer 0 — Foundation

| Stage | Name | Status | Tests | Entry |
|---|---|---|---|---|
| L0.1 | Repository scaffolding and guardrails | ✅ | 25 | [entry](L0.1_scaffolding_and_guardrails.md) |
| L0.2 | Canonical taxonomy, units and time | ✅ | 96 | [entry](L0.2_taxonomy_units_and_time.md) |
| L0.3 | Exercise metadata | ✅ | 193 | [entry](L0.3_exercise_metadata.md) |
| L0.4 | Relative-intensity mapping | ✅ | 430 | [entry](L0.4_relative_intensity.md) — built late; see entry |
| — | **Checkpoint 0** — substrate frozen | ✅ | — | [record](CHECKPOINT_0.md) |

## Layer 1 — Simulator

| Stage | Name | Status | Tests | Entry |
|---|---|---|---|---|
| L1.1 | Athlete A latent parameters | ✅ | 225 | [entry](L1.1_athlete_parameters.md) |
| L1.2 | Physiology core | ✅ | 248 | [entry](L1.2_physiology_core.md) · [audit](INVERSE_CRIME_AUDIT.md) |
| L1.3 | Recovery and wearable generation | ✅ | 271 | [entry](L1.3_recovery_and_wearables.md) |
| L1.4 | Programme generator | ✅ | 312 | [entry](L1.4_programme_generator.md) |
| L1.5 | Performance generation chain | ✅ | 341 | [entry](L1.5_performance_chain.md) — resolved by DATA.md 0.6.0 |
| L1.6 | Scenario engine | ✅ | 367 | [entry](L1.6_scenario_engine.md) |
| L1.7 | Missing data and dirty fixtures | ✅ | 381 | [entry](L1.7_missing_data.md) |
| L1.8 | Full generation run and quality report | ✅ | 409 | [entry](L1.8_generation_run.md) |
| — | **Checkpoint 1** — does this look like real training? | ✅ | 409 | [record](CHECKPOINT_1.md) · [audit](LAYER1_AUDIT.md) · [figures](checkpoint1/) |

## Layer 2 — Inference engine

| Stage | Name | Status | Tests | Entry |
|---|---|---|---|---|
| L2.1 | Input normalisation and set transformation | ✅ | 524 | [entry](L2.1_set_transformation.md) |
| L2.2 | State evolution | ✅ | 546 | [entry](L2.2_state_evolution.md) |
| L2.3 | Recovery context | ✅ | 563 | [entry](L2.3_recovery_context.md) |
| L2.4 | Performance and capacity | ✅ | 586 | [entry](L2.4_performance_capacity.md) |
| L2.5 | Session driver | ✅ | 598 | [entry](L2.5_session_driver.md) |
| L2.6 | Confidence | ✅ | 698 | [entry](L2.6_confidence.md) |
| L2.7 | Explanation trace | ✅ | 726 | [entry](L2.7_explanation_trace.md) |
| — | **Layer 2 audit** — 46/46 after fixing one defect | ✅ | 733 | [audit](LAYER2_AUDIT.md) |
| L2.8 | Projection | ✅ | 749 | [entry](L2.8_projection.md) |
| — | **Checkpoint 2** — engine runs end to end | ✅ | 749 | [gate](CHECKPOINT_2.md) · [pack](checkpoint2/) |
| — | **Drift investigation** — two fixes tried, both reverted | ✅ | 749 | [report](DRIFT_INVESTIGATION.md) |

## Layer 3 — Evaluation

| Stage | Name | Status | Tests | Entry |
|---|---|---|---|---|
| L3.1 | Evaluation harness | ✅ | 773 | [entry](L3.1_evaluation_harness.md) |
| L3.2 | State reconstruction metrics | ✅ | 789 | [entry](L3.2_state_reconstruction.md) |
| L3.3 | Performance and capacity metrics | ✅ | 805 | [entry](L3.3_performance_capacity.md) |
| L3.4 | Ranking tests | ✅ | 811 | [entry](L3.4_ranking_tests.md) |
| L3.5 | Calibration bands | ✅ | 818 | [entry](L3.5_calibration_bands.md) |
| L3.6 | Confidence and trace integrity | ✅ | 834 | [entry](L3.6_confidence_trace.md) |
| L3.7 | Robustness | ✅ | 842 | [entry](L3.7_robustness.md) |
| — | **Pre-holdout audit** — everything fixed or noted | ✅ | 842 | [audit](PRE_HOLDOUT_AUDIT.md) |
| — | **Limitations register** — living, updated as they change | 📋 | — | [register](LIMITATIONS.md) |
| L3.8 | Holdout run *(opened once)* | ✅ | 842 | [entry](L3.8_holdout_run.md) · [result](holdout_result.txt) |
| — | **Layer 3 audit** — 82/106; harness arithmetic sound, LIM-15 closed, D21 taken | ⚠️ | 850 | [audit](LAYER3_AUDIT.md) |
| L3.9 | Library versioning and expansion | ⚠️ | 858 | [entry](L3.9_library_versioning.md) — v1.1 registered; 11 fractions await review |
| L3.10 | Exercise vocabulary mapping | ✅ | 871 | [entry](L3.10_exercise_vocabulary.md) — 68 names reviewed and frozen |
| L3.11 | Real-data ingest adapter | ⚠️ | 882 | [entry](L3.11_real_data_adapter.md) — round-trips; LIM-30 needs a decision |
| L3.12 | Real-data cold run *(opened once)* | ⛔ | 886 | [entry](L3.12_real_cold_run.md) · [result](real_cold_run_result.txt) — **engine fails the severe criterion** |
| L3.13 | Accuracy--robustness repair gate | ✅ | 887 | [entry](L3.13_accuracy_robustness_gate.md) — athlete-approved before tuning |
| L3.14 | Coordinated capacity-estimator repair | ⚠️ | 903 | [entry](L3.14_capacity_estimator_repair.md) — robustness passes; historical real accuracy still fails |
| L3.15 | Directional fatigue test | ⛔ | 915 | [entry](L3.15_directional_fatigue_test.md) — **the test design is void**: it scores 49.0% on synthetic data (n=4228) where the model reconstructs truth at +0.941, so the real-data 49.7% refutes nothing. Survives: the fatigue signal is **7.8x weaker relative to noise in reality than in the simulator**. [external diagnostic](DIAGNOSTIC_FOR_REVIEW.md) · LIM-36, LIM-37, LIM-38 |
| L3.16 | Model version freeze | ✅ | 924 | [entry](L3.16_model_version_freeze.md) — D22's prospective regime was a claim, not a procedure: no freeze machinery existed. Versions are now content-addressed and **dated from git, not declared**. v0 freezes at **2026-08-24T22:23+01:00**, so every session logged since 25 August post-dates it. v0 carries LIM-38 in its record. LIM-39 |
| L3.17 | D20 re-audit: a competent competitor | ⛔ | 938 | [entry](L3.17_d20_reaudit.md) — **the headline synthetic results do not survive**. Given only the authored muscle map, a decaying counter scores **+0.955** against the engine's +0.965 longitudinally and **+0.934** against +0.941 cross-sectionally; it takes **5 of 6** ranking orderings for free. The famous "+0.966 vs +0.520" compared against an accumulator with no attribution. Engine advantage: **+0.010**. Neuromuscular peak timing, the last claim expected to survive, goes the other way: **88.5% for the counter against the engine's 81.5%**. Calibration is the only place the engine leads (2/6 vs 1/6). D23 · LIM-40 · retracts the comparison in L3.2 |
| — | **Checkpoint 3** — the v0 scorecard | ⬜ | — | — |

## Layers 4–5

Outline only until Checkpoint 3 results are known, with one exception recorded
because it is often asked about:

| Stage | Name | Status | Note |
|---|---|---|---|
| L5.1 | Exercise library expansion | ✅ authored | Delivered early by the athlete: 1074 exercises, schema-exact, at `data/exercises/exercise_library_v1.csv`. Integration is L3.9, which must pin the v0 dataset to its own library first. |
| L6.1 | [iOS logger](L6.1_ios_logger.md) | ⚠️ | Built ahead of its layer because D22 made validation prospective and nothing can be logged well until something records the right fields. `PRODUCT.md` → 0.5: equipment context and per-set timestamps are now required inputs. Logs against library ids directly, retiring name-mapping. **On device and in use** since 25 August 2026; first real session logged that day. Signed on free provisioning, so it expires 1 September unless the membership lands. |
| L6.2 | [Rhome log ingest](L6.2_rhome_log_ingest.md) | ✅ | 12 tests. The adapter from the logger's export to `DayInput`, the counterpart to `spotr.py`. Cumulative exports deduplicate by session id with the latest winning; unknown ids and unknown schemas raise rather than resolve. Built and tested entirely on fabricated fixtures — the athlete's logged sessions were not read. |

See `BUILD_PLAN.md` for the rest.

---

## Guardrail status

Coverage measured at the Layer 3 audit by attempting the violation, not by
reading the test. Every one has a live evasion; see [LIM-17](LIMITATIONS.md).

| # | Guardrail | Built | Enforced by | Measured coverage |
|---|---|---|---|---|
| 1 | Import boundary | L0.1 ✅ | `tests/test_guardrail_import_boundary.py` | ⚠️ static imports only; `importlib` and pathlib-joined paths pass |
| 2 | Frozen projections | L2.4 ✅ | `tests/test_engine_performance.py` | ⚠️ catches re-freezing; **no check that the freeze precedes the session** |
| 3 | Parameter registry | L0.2 ✅ | `tests/test_guardrail_parameter_registry.py` | ⚠️ 84 of 105 genuinely; 21 self-certify via an f-string in their own `register()` |
| 4 | Deterministic seeding | L0.1 ✅ | `tests/test_guardrail_determinism.py` | ⚠️ static scan catches one spelling; real cover is the `rhome_sim` regeneration test |
| 5 | Conformance map | L0.1 ✅ | `tests/conftest.py` → `conformance.md` | ⛔ **report is written, never asserted on** — an uncovered clause does not fail the suite |
| — | Holdout seal | L3.1 ✅ | `rhome_eval.window` | ⚠️ `run_engine(…, seal=HoldoutSeal())` runs it unrecorded |
