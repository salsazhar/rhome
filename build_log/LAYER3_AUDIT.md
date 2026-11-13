# Layer 3 audit — the evaluation harness, checked from outside

**Layer:** L3 — Evaluation
**Date:** 24 August 2026
**Status:** ⚠️ first pass 75/100 — seven new limitations, no arithmetic error.
See the **follow-up** at the end of this entry: LIM-15 closed, D21 taken,
§19.7 registered and two further acceptance criteria found failing. Current
state 82/106, 850 tests.
**Tests:** 842 at the first pass (a tool, not tests); 850 after the follow-up
**Tool:** `tools/layer3_audit.py`

---

## Why this was run

Layer 3 found eleven measurement errors and one modelling defect. Every one of
the eleven produced a plausible number with a ready explanation attached, and
every one was caught by checking the instrument against something *independent*
— the specification's own words, an earlier prototype, or a metric with a floor
it could not cross.

A harness cannot audit itself. A mis-scaled instrument reports a mis-scaled
number with complete internal consistency, and every existing Layer 3 report
imports the same fixture, the same metrics module and the same truth object. So
this stage re-derives every `DATA.md` §19 metric by a different route:

- truth from the **written hidden CSVs**, not from re-running `simulate()`;
- inputs from a **loader written in the audit**, not the `tests` fixture every
  report shares;
- correlation, RMSE, directional accuracy, the ablation ladder and the decaying
  counter **implemented from their definitions**, not imported;
- each re-derived figure then compared against what `rhome_eval` reports, with
  a stated tolerance.

Every check reports its sample size, and a check with an empty sample fails.

---

## The headline

**The harness's arithmetic is sound.** Not one computational disagreement was
found. Every §19.1 correlation, every §19.2 residual, both ablation ladders and
the scale alignment reproduce to 1e-9 or to the 1e-5 the six-decimal-place
hidden tables allow:

```
PASS  §19.1 local_fatigue   r +0.948803/+0.948803  RMSE 0.542299/0.542299
PASS  §19.2 pooled residuals  MAE 0.042524/0.042524  bias +0.006329/+0.006329
PASS  §19.2 ablation ladder (settled)  engine 0.039652/0.039652
PASS  alignment  local 0.872540/0.872540  neuro 0.587133/0.587133  sys 0.824174/0.824174
```

**Every finding is about what is being measured, not how.** That is the class
this project keeps finding, and it kept finding it here.

---

## The twelfth measurement error

`rhome_eval.run.latent_series` builds the §19.2 capacity target as
`true_expressible_capacity / fatigue_factor`. The simulator's chain is
capacity → fatigue → **stochastic shock** → load, and `RealisedSet` records
`performance_shock` as its own field. The shock is left in the target.

The hard-floor check — a quantity called *neutral capacity* must be constant
across the sets of one day:

| target | median within-day spread | p90 | max |
|---|---:|---:|---:|
| `cap / fatigue_factor` (as built) | **5.12%** | 10.59% | 24.31% |
| `cap / (fatigue_factor × shock)` | **0.0058%** | 0.0119% | 0.0198% |

0.0058% is the rounding floor of the CSV. Nothing else remains, which is the
kind of evidence D19 asks for: a value that has crossed to an impossible
boundary cannot be rationalised.

This one runs the *other* way from the previous eleven. It **understates** the
engine. Mean capacity correlation across 27 exercises rises **+0.690 → +0.973**;
every exercise improves; the worst goes +0.305 → +0.945. Mean absolute error
after alignment barely moves (4.43% → 4.32%), because a symmetric shock destroys
correlation without moving a mean.

Because it flatters the engine, it deserves more scepticism than the others, not
less. What convinced me: the within-day spread collapsing to the rounding floor
is a floor argument, not an explanation; `performance_shock` is a separately
recorded field with a documented role; and the correction resolves two questions
the build log left open, in the direction those entries predicted something was
wrong.

**It closes L3.3's open note.** L3.3 wrote that low correlation on the main
lifts was "likely a range effect… not verified, and L3.7 should check it is not
something worse." It is something else, and the stated pattern is not in the
data: the two worst exercises are `lateral_raise` (+0.305) and `leg_curl`
(+0.414), both isolation, while deadlift and bench sit mid-range. This is D19
exactly — a reason was available, written down as "likely", flagged forward, and
L3.7 did not return to it.

**It closes L3.4's open note.** L3.4 asked whether the fifteen disagreeing
deload-rebound pairs were "noise or a subset with something in common". Six were
this. With the shock removed from `expressible`, sign agreement goes 34/49 →
**40/49** and the expressed contrast 0.424 → 0.564.

Recorded as **LIM-15**. Not fixed here: correcting it changes reported numbers
in the flattering direction and belongs against a frozen baseline.

---

## Two headline numbers restated

**The "67% of true contrast" (LIM-2, L3.4)** averaged five *dose-contrast*
ratios with one *performance-gain* ratio — different quantities on different
scales. It also ran the engine at `novelty = 1` while the simulator applied its
novelty ramp: `_engine_dose` builds an `exposures` counter and never uses it.
Like for like, novelty matched, the five commensurable cases mean **0.699**, not
0.723 as built. The sixth reads 0.564 once LIM-15 is corrected. The six-case
mean is 0.677 — close to the published 0.67 only because the two errors nearly
cancel.

**"Beats recency on the settled ablation" (`CLAUDE.md`)** is stronger than the
measurement. The verdict on the settled sample is *tie* on both windows, which
is what L3.8 says. And on the pooled sample the engine **loses outright** to
mean-of-last-five (0.0423 vs 0.0408, Δ −0.00154 ± 0.00116). L3.3 recorded that
honestly in its entry; LIM-5 did not carry it forward. Corrected.

---

## The guardrails, attempted rather than read

D3 requires guardrails to be tested against planted violations. They are — but
each test plants the one spelling its author had in mind. **All five have a live
evasion**, recorded as LIM-17. The two that matter most:

**Guardrail 5 does not exist as a gate.** `conftest.py` *writes*
`build_log/conformance.md`; nothing asserts on it. A clause registered with no
test was planted and the full suite still reported **842 passed** while coverage
fell to 99%. `CLAUDE.md` says "a registered clause with no test fails the
suite"; it does not. Markers are also collected at *collection* time, so a
skipped or failing test still counts as covering its clause.

**Guardrail 1 is defeated by this codebase's own house style.** The path markers
require a slash — `"hidden/"`, `"data/real"` — and every path in this project is
written `REPO_ROOT / "data" / "…"`. `Path("data/synthetic/athlete_a") / "hidden"`
inside `rhome_engine` passes. So does `Path("data") / "real"`. So do
`importlib.import_module` and `__import__`.

And the seal has a second copy it does not cover: `real_oura/` and
`spotr_data/` hold the *originals* the sealed files were copied from, matched by
no marker and listed in no manifest. `tools/seal_real_data.py verify` reports
"seal intact: 3 files unchanged" and is telling the truth about one of the two
places the data lives.

**Guardrail 2 has no ordering check.** Re-freezing is caught. Freezing *after*
the session is not: `frozen_at_h` is stored, hashed into the digest, and never
compared to anything. `performance.py` states that "a residual can only be
scored against a projection that was frozen strictly before the session it
predicts" — the ordering rests on statement order in `RhomeEngine.process_day`.
It holds today; all 2087 projections froze at hour 17.00, before the first set.
It is a convention with a docstring, not a mechanism.

**Guardrail 3 is D17 recurring inside the fix for D17.** 21 of 105 parameters
are "proved read" only by an f-string *inside their own `register()` call*.
`ast.walk` visits the f-string node independently of the `register` call that
the scanner skips, so the registration certifies itself. No live drift — the
registry and the arithmetic share one dict — but the check reports 105/105 when
its real coverage is 84/105.

**The holdout seal.** `run_engine(days, Window.HOLDOUT, seal=HoldoutSeal())`
runs all 210 holdout days, records nothing, and the run's caveat reads
`"holdout unopened"`. The guard tests `seal is None`.

---

## The dataset is no longer the output of its own generator

`tools/layer1_audit.py` is **red — 52/53 — and has been since L2.1.**
`INDEX.md` marks the Layer 1 audit passed; nobody re-ran it. Layer 2's audit is
47/47 green.

One file of twelve differs: `metadata/raw_dirty.csv`. Every `observable/` and
`hidden/` table reproduces byte-for-byte, so **no Layer 3 number is affected**.
The cause is clean: `rhome_sim/missingness.py` last changed in commit `7bbcbda`
("L2.1"), when the parser's bounds were corrected; the dataset was written at
L1.8 and never regenerated.

Both checksum manifests certify the stale file, so every provenance check —
including this audit's — passes on a self-consistently stale artefact.
`test_regeneration_reproduces_the_dataset_byte_for_byte` cannot see it: it
compares two *fresh* regenerations to each other, both from current code. It
proves the generator is deterministic and says nothing about whether the
committed dataset came from it.

The stale fixture also documents two defect classes the parser no longer has.
**`140 kg × 20 reps at RPE 10` is now accepted as a working set** and feeds
capacity estimation; it used to be rejected as physiologically impossible. The
pounds-without-a-unit-change repair is likewise gone. The ingest module
documents the RPE-floor correction at length and says nothing about either.
Recorded as **LIM-18**.

---

## Findings that are about the specification

**Four of thirteen scenarios exist only inside the holdout** (LIM-16): S5, S10,
S11, S12. `DATA.md` §19 names three of them as acceptance criteria, so each is
verified against a constructed substitute — S12 by a 60-day-plus-14-blank toy,
S11 by a hand-scaled session, S10 not at all. There is no natural analogue
either: the longest training-free stretch in the whole 520-day development
window is **three days**, against S12's ten. §15 requires scenario families in
both windows; §14's chronology places all four after day 530. The generator
followed §14.

**The §19.4 bands describe the engine, not the simulator** (LIM-21). §19.4 says
they are "checked against the simulator's own suppression". The engine is in
band 5 of 6; **the simulator is in band 2 of 6**, and 9.7 points above the top
at the overload peak. So "5 of 6" is the engine agreeing with a target derived
from its own λ values. This has a concrete consequence for L5.3: fixing LIM-2
moves the engine *toward* the simulator and therefore *out of* these bands, and
§19.4 forbids widening them quietly. It has to be settled before L5.3.

**Set timestamps do not exist on either side** (LIM-19). §18 requires them
"explicit and spread realistically across the session"; §5.3's schema defines no
column for them. Logged sessions run a median 138 minutes; the engine spreads
them over 25; the simulator applies every set at one instant.

**The latent pairing is 8.5 hours out** (LIM-20). `LATENT_OFFSET_DAYS = 1` is
correct and dominant, re-confirmed. But the engine's day-N state is captured at
23:30 and the simulator's on waking at 08:00, so the pairing compares states
across the whole overnight recovery. No integer offset closes it. `run.py` says
they "line up".

**S11's 1% requirement is not met by a real session** (LIM-22). The test applies
one `update_capacity` call; the engine applies one per eligible set, and a real
session has three to five. On the real log at 28 prior observations, a 40% miss
displaces capacity −1.08% (bench) to −1.53% (squat), against the −0.60%
recorded. It washes out within a month, so the spirit holds. And
`single_bad_day_displacement` — the function written to measure exactly this
"by running the engine twice over the same log" — is called by nothing.

---

## Smaller corrections

- **LIM-3** re-measured: **−9.35%**, not −8%, over the same fourteen blind
  nights. Confidence falls 0.282.
- **L3.7's bad-HRV figure** samples +0/+3/+14/+60 days and concludes "three and
  a half per cent". Sampled consecutively the peak is **+5.64% at +1 day**, the
  one horizon the grid skips. Every printed value is right; the conclusion is
  61% low. Still bounded, still gone within a week.
- **The written hidden tables are rounded to 6 dp**, so truth-from-disk and
  truth-from-`simulate()` differ by up to 3.5e-6. Immaterial, but the two are
  not the same object and nothing said which one the numbers came from.
- **`daily_recovery.csv`** omits `oura_like_readiness` and
  `oura_like_sleep_score`, both in §5.1's schema. Both are display-only and
  §5.1 forbids the engine using readiness, so nothing is lost — but the written
  table does not match the documented one.

---

## What passed, and is worth saying

- The contribution ledger's fold-and-residual arithmetic **conserves surviving
  mass exactly** (delta 2.2e-16 across 40 impulses), and a re-expressed residual
  decays like any other contributor (delta 1.1e-16). Two identically-valued
  impulses fold as two, despite `Impulse` using value equality.
- **9347 traces**: shares sum to one within 1.2e-12, states reconstruct within
  1.2e-12, and none of 5970 distinct driver strings crosses a `RESEARCH.md` §17
  claim boundary.
- **2087 frozen projections**: every digest verifies, no duplicate keys, all
  froze at hour 17.00 before the first set.
- Every model group beats the decaying counter (mean +0.966 vs +0.520); every
  channel's directional accuracy is 94.6–95.2%, well clear of the 50% floor.
- Drop segments (123, 1.20%) are wholly excluded from performance estimation;
  1848 warm-ups contribute nothing.
- Observable and hidden set tables key one to one across 10215 rows, with no
  latent column in an observable table.
- The engine is deterministic over the development window; the sealed export is
  unmoved; the committed observable and hidden tables match both manifests.

---

## Decisions

**Nothing was fixed in this stage.** Seven of the findings change reported
numbers, and three of them change them in the engine's favour. Correcting them
inside the audit that found them would leave nothing to compare against, which
is the same reasoning that deferred L5.3. They are recorded, sized, and left for
Salman to sequence against Checkpoint 3.

**`tools/layer3_audit.py` exits non-zero.** Like the Layer 1 and Layer 2 audits
it is a tool rather than a test, but unlike them it is expected to be red until
the limitations it names are closed. Each failing check names the limitation it
corresponds to.

---

## Notes carried forward

- LIM-15's correction should land against a frozen v0 baseline, with before and
  after both reported, because it improves a headline number.
- LIM-21 blocks L5.3: the calibration bands must be resolved before non-linear
  accumulation is added, not after.
- LIM-16 needs a regenerated dataset, so it is a v0.2.0 decision.
- The guardrail evasions in LIM-17 are each a one-line fix; the *class* is not,
  and D15's rule that a guardrail must assert its own scope is met by none of
  the five.
- This audit found a twelfth measurement error in the harness. On the record so
  far the correct prior is that a thirteenth exists.

---

# Follow-up — D21, and what registering §19.7 exposed

**Date:** 24 August 2026 · **Status:** ⚠️ audit 82/106 · **Tests:** 850

## D21 — the calibration bands, decided before the number is known

Taken by the athlete, recorded as **D21**. The §19.4 bands do not gate L5.3;
L5.3 is judged on its own four criteria. When non-linear accumulation moves the
engine out of band, one of three options is chosen with its reason stated
*before* the new figures are read: re-derive λ, revise the bands and version
`DATA.md`, or question the simulator's own curve.

The third option is recorded because nobody had raised it. The simulator's
non-linearity constants are D8 simulator invention — not in the registry, no
evidence grade, no cited section, never checked against anything. LIM-2 treats
the simulator as the truth the engine falls short of; that is an assumption,
and D21 is the first place it is written down as one.

The pre-registration is the whole point. §19.4 says the bands are *not* quietly
widened, so revising them is a departure from the specification and needs an
argument. Made after seeing a 22% figure against a 13–16% band it is
indistinguishable from fudging, however sound. Made now, with the number
unknown, it is a decision.

## LIM-22 — the root cause was in `MODEL.tex`, not in the test

Measuring S11 properly found something better than a test bug. `MODEL.tex`
§Estimation of underlying capacity says:

> The clip at $c=0.10$ bounds the influence of any single **set** to a 0.6%
> movement in capacity at the base rate, **so one anomalously poor session** —
> scenario S11 — produces a large negative residual without depressing capacity.

The first clause is correct — $e^{\alpha c}-1 = 0.602\%$. The second does not
follow. A session is two to five eligible sets, one possibly an anchor test at
$\alpha=0.20$. The false inference propagated into §19.7's 1% threshold and into
a test that applied exactly one `update_capacity` call.

Measured across 18 sessions and three exercises: **median 2.1%, worst 3.3%**,
settling under 0.2% within 90 days.

**And a second thing, which is more interesting.** Any innovation beyond the
clip is clipped to the same value, so a 14% miss and a 40% miss move capacity
*identically*. The engine's response to a bad session does not depend on how
bad it was — only on the session's eligible set count and whether one was an
anchor. Scenario S11's own magnitude is a median 13.9% shortfall; the stand-in
used 40%, so its severity was decorative and a reader would reasonably have
thought it the harder test.

`single_bad_day_displacement` — written to measure exactly this and called by
nothing — now works, and is called.

## Registering §19.7 exposed two failing acceptance criteria

Seven of the eight subsections of §19 carried conformance clauses. **§19.7
carried none** — five requirements, unregistered since L2.4. Coverage read
100% throughout, because coverage is measured against the register and nobody
asked whether the register was complete. D15's rule applied to the map instead
of to a test, and the fourth appearance of the same shape.

Registering the five clauses immediately produced two failures:

**LIM-22**, above.

**LIM-23 — a deload rebound is attributed to new capacity, not to lost
fatigue.** Projected performance is $\bar P_e(1-s)$, so the change across a
deload factors exactly in log space. It does, to 1e-9 — and it says:

| across an S3 deload | |
|---|---:|
| attributed to capacity | **+0.0116** |
| attributed to reduced fatigue | +0.0034 |
| capacity across matched ordinary gaps | +0.0035 |
| **excess attributable to the deload** | **+0.0080 ± 0.0025** |

Capacity dominates the fatigue term by 3.4×, where §19.7 requires the reverse.
The control is the substance: capacity rises across any three weeks, which is
the trap L3.4 fell into three times on this metric. Only the excess over a
matched stretch is attributable.

The mechanism is LIM-2. The engine removes the fatigue it *believes* was acting
before updating capacity; accumulating linearly, it understates how much fatigue
a deload removed, and the unexplained part of the rebound is absorbed as
capacity. Stated for the athlete: **after a deload the app will tend to say you
got stronger, when what happened is you got fresher.** That is the specific
false and encouraging claim §19.7 exists to prevent.

This gives L5.3 a falsifiable prediction, which it should carry as an
acceptance criterion: if linear accumulation is the cause, this ratio must
invert. If it does not, the cause is something else.

## What was closed

Three of §19.7's five requirements now have honest tests and pass: the S9
plateau is engine-side flat (+0.90% over fifty plateau days against +2.17% per
fifty days during genuine growth), no drop segment or out-of-domain set reached
the capacity update in 520 days, and a 4 kg body-mass change moves pull-up
capacity in system-load units without touching bench press.

Two tests failed first and were rewritten rather than re-thresholded. The
plateau test compared against days 400–449, where the estimate was already
flat — it would have "shown" growth stopping in a window with no growth. The
deload test used a 14–21 day window with no control, which measured ordinary
progress. Both were instrument errors, caught by their own vacuity guards, and
both are recorded in the tests that replaced them.

## Where this leaves the numbers

- 850 tests, conformance **100% of 95 clauses** (was 90; §19.7 added five).
- Layer 3 audit **82/106**.
- Two new limitations, LIM-23 and LIM-24; LIM-22 rewritten with its root cause.
- One decision, D21.
- **`MODEL.tex` is not yet corrected.** Its paragraph contains a false
  inference and versioning the specification is the athlete's act, not mine.
