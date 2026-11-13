# Checkpoint 1 — Layer 1 complete

**Date:** 22 August 2026
**Status:** ✅ Passed — proceed to Layer 2
**Dataset:** v0.1.0, seed 20260822

---

## What was reviewed

| Item | Where |
|---|---|
| Visual pack: timeline, distributions, scenarios | [`build_log/checkpoint1/`](checkpoint1/) |
| `sets.csv` and `daily_recovery.csv` | Delivered to the athlete directly |
| Layer 1 audit, 53 checks | [`LAYER1_AUDIT.md`](LAYER1_AUDIT.md) |
| Inverse-crime audit | [`INVERSE_CRIME_AUDIT.md`](INVERSE_CRIME_AUDIT.md) |

## State at the gate

- **409 tests passing**, 46 of 46 specification clauses covered
- **53 of 53 audit checks passing**, measured against the written dataset
- **Guardrails 1, 3, 4, 5 live**, each demonstrated rejecting a planted violation
- **Dataset v0.1.0**: 730 days, 495 sessions, 7,526 dose-bearing sets, regenerating byte-identically from its seed

## Decisions taken at this gate

Two documented distributions were revised during Layer 1 and **both were confirmed by the athlete at this checkpoint**:

**`DATA.md` §9.1 — repetition bands.** The 1–3 band moved from 5–8% to 10–15%. Only ~6% of sets are prescribed there; the rest are later sets of 4–6 prescriptions falling short under within-session fatigue. The previous range implicitly assumed no drop-off across sets.

**`DATA.md` §9.2 — effort distribution.** Now specifies true effort and logged effort separately. The athlete corrected a misreading on my part: a training log contains logged values, and effort is recorded as whole-number repetitions in reserve. The original figures survive as the true-effort column; the logged column records what they become after the reporting error the specification itself mandates.

Both revisions are recorded in the `rhome_docs` README changelog at documentation version 0.4, with `DATA.md` at 0.6.0.

## What the audit found

Three readings did not survive being examined, and two were defects in the *checking* rather than the data. They are recorded in full in the audit report; in brief:

- a test whose failure message quoted the documented range while asserting a looser one, so it would have passed on a value the specification forbids;
- a measurement taken across the whole record where the specification described ordinary nights only;
- a check that would have reported PASS on an empty sample — the same vacuous-pass failure found in Guardrail 3 at L0.2, now guarded against by requiring checks to declare their sample size.

## Open item carried into Layer 2

Upper/lower parity sits at **exactly 95.0%** of rolling four-week blocks within ±10%, against a 95% threshold. Median 2.2%, worst 13.6%. Not a failure, but not comfortable either. Any change that nudges it will fail loudly, which is the intended behaviour.

## What changes cheaply from here

Nothing. Layer 2 builds the engine against this dataset and Layer 3 evaluates it, so from this point a coefficient change means regenerating the dataset and invalidating every baseline built on it. Dataset versioning (`DATA.md` §21) exists for that case, and the committed checksum manifest is what makes a version claim verifiable.
