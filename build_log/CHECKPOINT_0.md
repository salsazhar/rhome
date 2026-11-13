# Checkpoint 0 — Substrate frozen

**Date:** 22 August 2026
**Layer:** L0 — Foundation
**Status:** ✅ Passed — proceed to L1

---

## What was reviewed

| Item | Where |
|---|---|
| Exercise library, 27 exercises | [review page](https://claude.ai/code/artifact/b8d6dad1-2572-49e2-9bc7-90d6f8cb9725), `data/exercises/exercise_library.csv` |
| Guardrail demonstrations | L0.1 and L0.2 build-log entries |
| Conformance coverage | `build_log/conformance.md` — 15/15 clauses |

## State at freeze

- **193 tests passing**, four stages complete
- **Guardrails 1, 3, 4, 5 live**, each demonstrated rejecting a planted violation
- **16 model muscle groups**, 24 display labels, all groups both loadable and directly trainable
- **27 curated exercises**, derivation reproducing 26 of them within ±0.15

## Decision

Proceed to Layer 1. Library size held at 27 for the simulator: Athlete A is one
person over two years, and a larger library would make the generated data less
realistic rather than more. Expansion is scheduled as L5.1 and is being drafted
in parallel by the athlete.

## Open until L1.8

**Coefficient changes are cheap until the dataset is generated.** Editing a
value in `exercise_library.csv` today costs nothing; editing it after L1.8 means
regenerating 730 days of data and invalidating every evaluation baseline built
against it.

Library review therefore continues in parallel through L1.1–L1.7.
`tools/validate_library.py` checks any candidate CSV against the same schema the
engine enforces.
