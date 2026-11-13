# Rhome

A model that infers latent, per-muscle training fatigue from a resistance-training log and nightly wearable data (HRV, resting heart rate, sleep), and uses it to predict next-session performance.

The fatigue state can never be observed directly, so the project is as much about **how to validate a model like this honestly** as about the model itself.

## The model

- Each logged set is converted into a fatigue impulse using a published reps-to-failure vs %1RM relationship, distributed across 16 muscles by an exercise-to-muscle contribution map.
- Fatigue evolves by linear impulse–response ODEs (fitness–fatigue lineage). The recovery rate is modulated by personal z-scores of HRV, resting heart rate and sleep, after removing what recent training already explains.
- Expected performance decays exponentially with local, neuromuscular and systemic fatigue. Capacity is estimated online with a Huber-robust estimator that limits how far one bad session can move it.
- Projections are frozen before each session is revealed, so there is no target leakage.

Full specification: `rhome_docs/MODEL.tex`. Data and evaluation protocol: `rhome_docs/DATA.md`.

## How it was validated

1. **Synthetic athlete.** A 730-day simulated athlete with hidden latent state and a scenario library (overload, deload, sleep restriction, illness, novelty). The simulator is deliberately structurally richer than the engine (two-compartment recovery, non-linear accumulation, an unobserved stress process) so the engine is not tested on its own assumptions.
2. **Sealed real data.** The author's own log (99 sessions, 976 sets, 569 nights of wearable data) was checksummed and left unread during development, then opened once as an independent test.
3. **No score without a trivial competitor.** Every result is reported next to the simplest baseline that could match it.

## Results

| claim | engine | simple baseline |
|---|---:|---:|
| per-muscle latent fatigue, synthetic (r) | +0.965 | +0.955 (decaying set counter given the same muscle map) |
| next-session performance, real data (MAE) | 0.315 | **0.143** ("repeat last session") |

The engine recovers latent fatigue on synthetic data, but a simple baseline given the same exercise-to-muscle map gets almost all of the way there (advantage +0.010). On real data the engine lost to "repeat last session".

Diagnosis (`build_log/real_diagnosis.txt`, `build_log/directional_fatigue.txt`): real noise was about 4.9x larger than the simulator assumed; and a power analysis showed the directional validation test could not have detected an effect of the size the engine predicts, even for a perfect model (ceiling 50.6%). The historical log was reclassified as spent development data, the model was frozen (v0, 24 Aug 2026), and validation moved to sessions logged after the freeze.

Every known limitation, what it costs and what would fix it: `build_log/LIMITATIONS.md`. Every design decision: `build_log/DECISIONS.md`. Stage-by-stage build record: `build_log/INDEX.md`.

## Repository layout

| path | contents |
|---|---|
| `src/rhome_engine` | the inference engine |
| `src/rhome_sim` | the synthetic-athlete simulator (kept separate from the engine) |
| `src/rhome_eval` | evaluation harness, holdout enforcement, real-data adapter |
| `src/rhome_core` | shared taxonomy, units, exercise metadata |
| `tests/` | test suite, including guardrails tested by attempting the violation |
| `tools/` | audits and reports |
| `app/` | RhomeLogger, an iOS app for logging sessions in the format the engine reads |
| `rhome_docs/` | specification |
| `build_log/` | build record, decisions, limitations, results |

## Data

The author's personal training and wearable data are **not included**. Tools that read them (`tools/real_*.py`) will not run without it. The synthetic dataset is regenerable from its seed and configuration (`rhome_docs/DATA.md` §21); its checksums are in `data/`.

## Authorship

I specified the model, the simulator and the validation protocol, and directed AI-assisted implementation.
