# Limitations register

**A living document.** Every known limitation of the model, where it was found,
what it costs, and what would fix it. Updated whenever one is found, fixed, or
changes size — not written once and left.

Rules for keeping it honest:

- a limitation is added the moment it is *measured*, not when it is fixed;
- each carries a number, so it can be referred to from a build-log entry or a
  commit without restating it;
- **status** is one of `open`, `specified`, `mitigated`, `closed`;
- a limitation is only moved to `closed` with the measurement that closed it;
- if a fix makes something worse, that goes here too.

Last updated: **26 August 2026**, at L3.17. The D20 re-audit found the
project's headline synthetic results were scored against a competitor too
weak to be informative; D23 and [LIM-40] record what they are worth against
a competent one. Historical real-log results remain development-only (D22).

---

## Open and specified

### LIM-1 — The engine reads illness as training fatigue
**Status:** `specified` → L5.2 · **Found:** L3.3, confirmed L3.7

During an illness block the engine over-predicts suppression by **+0.0254 ±
0.0201** over 22 sets. The mechanism is measured: ρ falls to 0.802 against 0.992
on nearby days because the autonomic signals collapse, while working sets fall
from 15.0 to 8.8 a day. The engine holds fatigue elevated exactly as the athlete
gets fresher.

Travel — ρ 0.892, the nearest analogue — shows no effect, so this is specific to
autonomic collapse coinciding with reduced load.

**Fix:** shrink ρ toward neutral in proportion to the deviation training cannot
explain, conditioned on observed sleep as well as training so a genuinely bad
sleep week still slows recovery. Detection would be a diagnosis and is refused.

### LIM-2 — Fatigue accumulation is linear
**Status:** `mitigated` — bounded session-position curvature implemented at
L3.14; prospective human effect unresolved · **Found:** L3.4, corroborated L3.5

Ten sets deposit exactly ten times one set. Fatigue is not like that: the eighth
set lands on tissue the first seven already fatigued. The engine ranks every
ordering correctly and expresses a consistently compressed share of the true
contrast; none is overstated.

**Re-derived at the L3 audit.** The headline "67%" averaged five *dose-contrast*
ratios with one *performance-gain* ratio — a different quantity on a different
scale. It also ran the engine at `novelty = 1` while the simulator applied its
novelty ramp, which flattered the engine by 2.4 points. Like for like, on the
five commensurable dose cases with novelty matched:

| ordering | expressed |
|---|---:|
| failure vs matched-volume non-failure | 0.576 |
| high volume vs ordinary volume | 0.788 |
| lower compound vs arm isolation, systemic | 0.764 |
| heavy compound vs isolation, neuromuscular | 0.688 |
| deload vs accumulation | 0.681 |
| **mean of the five** | **0.699** |

The sixth ordering, post- against pre-deload performance, now reads **0.564**
against the 0.424 recorded at L3.4, [LIM-C5] having been closed. The six-case
mean as the report renders it is **70%**; with novelty also matched it is
0.677. The published 0.67 was close only because the two errors nearly
cancelled.

**The novelty asymmetry is fixed at L3.14.** The independent ranking harness
now uses the same observable novelty and session-position path as the driver;
tests reject bypassing it.

Corroborated independently by the calibration bands: the simulator suppresses
6.00% against the engine's 5.87% after one session, and 25.67% against 14.97% at
an overload peak. See [LIM-21]: the simulator is outside four of the six
documented bands, so those bands cannot survive this fix unchanged.

**Fix:** amplify by position within the session rather than by current state —
structurally different from the simulator's form, so it does not create an
inverse crime. Lands after Checkpoint 3, against a frozen v0 baseline, and must
prove it pays.

**Measured on the real log (development, D22).** The athlete raised this
directly, and it is real. Within a session the engine models the fatigue that
actually occurs at roughly a third of its size:

| | |
|---|---:|
| observed capacity, last set vs first | **−9.6 pp** |
| what the engine's suppression rises by across four sets | **+3.4 to +5.4 pp** |

Testing L5.3's own specified form — the dose scaled by `1 + γ·position` —
against a responsive estimator:

| γ | 5th-set multiplier | MAE | bias |
|---:|---:|---:|---:|
| 0 | 1× | 0.1656 | +0.0752 |
| 1 | 5× | 0.1618 | +0.0605 |
| **2** | **9×** | **0.1604** | **+0.0470** |
| 4 | 17× | 0.1668 | +0.0349 |
| 8 | 33× | 0.1755 | +0.0536 |
| 16 | 65× | 0.1760 | +0.0794 |

**It plateaus and reverses**, which is the signature of a mechanism that is
really there. A parameter absorbing some *other* error would have kept improving
monotonically toward an implausible value; this one has an optimum and then
degrades. That is the check, not the improvement.

**But the fixes interact, and the order matters more than either of them.** At
v0's own settings — rate 0.06, clip 0.10 — the same change makes things
*worse*: MAE 0.3183 → 0.3274 at γ=2. The estimator is too rate-limited to use
the better fatigue estimate, so all the extra suppression does is lower the
projection. **Building L5.3 first, as planned, would have made the engine worse
and read as a refutation of this very limitation.**

Effect once the estimator can use it: MAE 0.1656 → 0.1604, bias +0.0752 →
+0.0470. It corrects *bias* far more than error, which is what a within-session
correction should do.

**Qualified implementation at L3.14.** The real-log optimum above is not the
shipped parameter: it fails the frozen synthetic contrast gate. The smallest
maximum-impulse-normalised candidate that clears every frozen criterion uses
$\gamma=0.25$, a position cap of 4 and $d_0=0.06$. On the corrected harness:

| criterion | frozen v0 | repaired |
|---|---:|---:|
| settled one-step MAE | 0.03965 | **0.03958** |
| high/ordinary-volume contrast expressed | 0.788 | **1.156** |
| deload/accumulation dose contrast expressed | 0.681 | **0.943** |
| post/pre-deload performance contrast expressed | 0.564 | **0.678** |

The first overshoots truth by 15.6%, but is closer than v0's 21.2% shortfall;
the other three affected measures also move toward 1.0. Direction remains 6/6.
This closes the structural linearity defect but not the human calibration
claim: on the historical real development log the admissible candidate still
loses badly to recency, so prospective data must decide whether the curvature
helps the athlete.

### LIM-3 — Missing wearables fabricate freshness
**Status:** `open` · **Found:** L3.7

`DATA.md` §19.8 asks that missing wearable data reduce confidence rather than
fabricating fatigue. It does not fabricate fatigue — it fabricates a little
**freshness**. With no input the multiplier goes neutral, and this athlete's ρ
sits below one on average (0.986, on the 0.80 floor 5.4% of days), so a
fortnight blind leaves the model more cheerful than it should be.

**Re-measured at the L3 audit: −9.35% local fatigue**, not the −8% recorded at
L3.7, over the same fourteen nights from day 300. Confidence falls by 0.282 on
the same block, which says so.

**Candidate fix:** default to the athlete's own recent mean ρ rather than to
neutral. Interacts directly with LIM-1 — both concern what to do when the
wearable signal is absent or untrustworthy — and should be decided with it.

### LIM-4 — Capacity warm-up
**Status:** `mitigated` · **Found:** Checkpoint 2 · **Mitigated:** L3.3, L3.6

The engine under-predicts performance until it has seen an exercise about twenty
times. Originally **+5.8%** over the first ten sessions; the L3.3 gain schedule
halved it to **+3.4%**, and L3.6's capacity-maturity component made confidence
report it — the first ten sessions now carry **no** `high` readings, against 238
of 270 before.

Not removed. An exercise trained once a week takes about twenty weeks to clear
it, and the athlete's imported history is the practical answer for a real user.

### LIM-5 — The engine only ties a five-set moving average
**Status:** `open` · **Found:** L3.3 · **Re-measured:** L3.8

On the settled ablation the engine's MAE is 0.0397 against mean-of-last-five at
0.0394 — a tie. It clearly beats median-of-three (0.0424) and last-observation
(0.0491). But a moving average matches it.

**"Loses to nothing" is true of the settled sample only.** Pooled across all
1948 scored sets the engine *loses outright* to mean-of-last-five: MAE 0.0423
against 0.0408, Δ −0.00154 ± 0.00116, which clears its own interval. L3.3
recorded this in its stage entry; this register did not carry it, and the
one-line summary in `CLAUDE.md` says the engine "beats recency on the settled
ablation" where the measured verdict on both windows is *tie*. Corrected at the
L3 audit.

**On the holdout the direction reverses**: engine 0.0424 against mean-of-last-five
at 0.0444, still a tie on the interval. Two ties in opposite directions is not a
victory, but it is better than one loss.

This is the bar personalisation at Layer 4 has to clear. If personalised
parameters do not produce a clear win here, they are not paying for themselves.

### LIM-6 — Fatigue confidence is almost always high
**Status:** `open` · **Found:** Checkpoint 2, unchanged at L3.6

`high` on 498 of 520 days. Defensible on clean synthetic data with near-complete
wearables, but an index that is almost always high is close to not being an
index. Untested against a real record, where inputs are worse. L3.12 is the
test.

### LIM-7 — Nuzzo curves for bench press and leg press are approximations
**Status:** `open` · **Found:** L0.4

The exercise-specific repetitions-to-failure tables were not obtained, so both
exercises carry Grade C approximations of a Grade A relationship. Everything
downstream of relative intensity on those two lifts inherits the grade.

**Fix:** obtain the tables and replace the approximation.

### LIM-8 — One calibration band is missed
**Status:** `open` · **Found:** L3.5

The failure-heavy single session suppresses **7.51%** against a documented 5–7%.
Half a percentage point over, on a two-point band, with the other five in band.

`DATA.md` §19.4 re-derives λ only if suppression is *systematically* outside, so
λ is not re-derived — and the band is not widened either. A test enforces that
reading: at most one case outside, overshooting by under a full point.

The state is the one most sensitive to $\phi_F(0)/\phi_F(2) = 1.35$, and LIM-2's
fix will change accumulation behaviour, so this is re-read after L5.3 — under
D21, at the same time and under the same choice as [LIM-21], not separately.

### LIM-9 — Hinge ambiguity in exercise metadata
**Status:** `open` · **Found:** L0.3

`torso_supported` was deferred as a remedy for distinguishing supported from
unsupported hinge movements. Revisit if residuals show systematic error on
supported movements, or when the library expands at L3.9.

---

## Found by the real-data cold run

### LIM-34 — Accuracy and robustness trade almost one for one, and v0 sits at the extreme
**Status:** `mitigated` — joint gate executable and repaired candidate passes;
accuracy failure remains [LIM-31] ·
**Found:** post-L3.12 diagnosis · **Development analysis (D22)**

Three candidate fixes were tested against the real log by sweeping the capacity
estimator's parameters. Identity splitting and clip width were each insufficient
alone ([LIM-33]); the **learning rate** turned out to be the largest single
lever, and sweeping all three together maps the trade exactly.

Split identity, `last observation` = 0.1255:

| rate ↓ / clip → | 0.10 | 0.20 | 0.35 | unbounded |
|---|---:|---:|---:|---:|
| **0.06** (v0) | **0.3183** | 0.2648 | 0.2324 | 0.2133 |
| 0.15 | 0.2559 | 0.2010 | 0.1794 | 0.1754 |
| 0.30 | 0.1952 | 0.1690 | 0.1656 | 0.1615 |
| 0.45 | 0.1749 | 0.1656 | 0.1670 | 0.1614 |

**Two findings, in opposite directions.**

*The estimator's shape is not wrong.* Accuracy improves to about rate 0.30–0.45
and then **worsens** again — at rate 1.00 it reads 0.1839. Smoothing earns its
place; v0 simply applies about five times too much of it. Raising the rate alone
takes MAE from 0.3183 to 0.1952 without touching anything else.

*But every gain is bought from robustness, at close to one for one.* What one
four-set session can do to a settled estimate, by `MODEL.tex`'s own session
bound:

| rate | clip | one bad session moves capacity by |
|---:|---:|---:|
| 0.06 | 0.10 | **2.4%** ← v0 |
| 0.15 | 0.20 | 12.7% |
| 0.30 | 0.35 | **52.2%** |

52% from a single session is precisely what `DATA.md` §19.7 exists to forbid —
"one anomalously poor session does not permanently depress capacity" — and it is
the behaviour that would tell an athlete they had lost half their strength
because they trained badly once.

**The reframing this forces.** `last observation` scores 0.1255 while having
**no robustness whatsoever**: by construction it adopts every outlier in full,
so a single bad session moves its next prediction 100%. The D20 ladder is
measuring accuracy alone, and on that metric an estimator that is asked to be
both accurate *and* robust is competing against one that is only asked to be
accurate.

That does not excuse the failure — the engine loses on the criterion `DATA.md`
§19.2 states, and D19 forbids treating an available explanation as a
resolution. It does mean the criterion is **incomplete**: nothing in §19 scores
robustness alongside accuracy, so a change that improved MAE by abandoning S11
would read as pure progress. That gap is a specification defect, and it should
be closed before any of these parameters is moved.

**What follows.** A single scalar rate-and-clip cannot serve both ends. The
mechanism has to distinguish a *persistent regime change* from *one bad
session*, which is the change-point argument the external audit reached from a
different direction. Tuning to rate 0.30 on this data would also be fitting a
parameter to the very log it is measured on, which D22 forbids reporting as
validation.

**Implemented at L3.14.** Correlated sets now produce one session update, the
Huber clip is $1.345$ times a per-context MAD scale with a 0.10 prior floor,
and ordinary/anchor session movements are hard-capped at 2.1%/3.3%. The S11
battery passes its median, worst and ninety-day gates. This prevents the
52.2%-per-session fitted solution from becoming eligible. It also exposes the
cost without euphemism: on the D22 historical log the admissible engine scores
MAE **0.2955** on the 125-row matched sample, against last observation 0.1255,
median-of-last-three 0.1348 and mean-of-last-five 0.1486. Robustness is fixed;
competitiveness is not.

### LIM-33 — One exercise id can span several incomparable load scales
**Status:** `mitigated` — gym context and confirmed unmerges implemented;
exact-machine context remains open · **Found:** external audit of L3.12 ·
**Confirmed by the athlete**

The engine keys capacity by `exercise_id` and assumes each one has a single,
continuous, comparable load scale. The athlete's log does not work that way. The
same logged name spans different machines, cable stations, attachments and gyms,
whose stack numbers are not comparable — a pulley ratio changes what "18" means.

Verified directly from `data/real_export/engine_input.csv`, first set of each
session:

```
cable_lateral_raise   3.4 → 3.4 → 8.0 → 5.0 → 8.0 → 8.0 → 8.0 → 14.0 → 14.0 → 14.0 → 18.0 → 9.0 → 5.0 → 7.5
bayesian_cable_curl   7.5 → 18.0 → 23.0 → 18.0 → 23.0 → 14.0 → 14.0 → 14.0 → 18.0 → 9.0 → 11.3 → 13.8
```

`18 → 9 → 5` is not a strength change. **The athlete confirms these are logging
mismatches across machines.**

The engine reads each jump as an enormous capacity innovation; the Huber clip
then does precisely what it was designed to do and refuses to follow it, because
it cannot distinguish a persistent regime change from an isolated bad set.
`last observation` wins by adopting the new scale immediately.

**Part of this is self-inflicted, at L3.10.** The frozen mapping merges several
logged names onto one capacity state, on advice given in the review artefact —
*"they can map to the same id; nothing requires them to be distinct."* That
advice was wrong wherever the names denote different equipment:

| capacity state | logged names merged into it |
|---|---|
| `seated_calf_raise` | Calf Raise · Seated Calf Raise · Seated Machine Calf Raise |
| `leg_extension` | Machine Leg Extension · Seated Machine Leg Extension |
| `overhead_rope_triceps_extension` | Cable Overhead Tricep Extension (Rope) · Overhead Tricep Extension |
| `incline_dumbbell_curl` | Dumbbell Incline Curl · Incline Dumbbell Curl |

The last of those is probably harmless — two spellings of one movement. The
first two merge machines that plainly differ.

**Necessary but not sufficient.** The external audit reports that descriptively
excluding the four worst identities moves matched MAE from 0.3148 to 0.1350,
against `last observation` at 0.1086 — so the engine still loses on the
remainder. Identity resolution is the largest single cause and does not on its
own make the model competitive.

**Fix:** key capacity by exercise *and* equipment context, with hierarchical
pooling so a new machine starts near the exercise-level estimate rather than
from nothing. **This conflicts directly with the product goal of being useful
quickly** — fragmenting histories lengthens warm-up — and the pooling is what
has to resolve that tension, not a detail of it.

**Implemented and bounded at L3.14.** Cable and machine capacity now splits by
the athlete's recorded gym; free-weight/bodyweight capacity remains shared. A
new context receives only a weak 0.25 exercise-level prior. Library v1.2 fixes
the pressdown/calf equipment labels, and calf/leg-extension machine names are
unmerged. The input now yields 40 capacity identities.

Gym is still only a proxy for the machine. Within `cable_lateral_raise::Second
gym`, first-set implied capacity runs **3.9 → 16.4** over 19 scored sessions.
That is not plausible strength progression, and the 2.1% session cap correctly
refuses to absorb it as if it were. Future logging must record the exact
machine/station/attachment; this limitation cannot be closed retrospectively
from the stack number alone.

### LIM-31 — The engine loses decisively to recency on real data
**Status:** `open` · **Found:** L3.12, the one-shot cold run · **The headline finding**

`DATA.md` §19.2 calls one-step-ahead residuals the severe criterion: *a model
that fits historical observations but has biased or poor one-step-ahead
residuals fails this criterion.* On the athlete's own history the engine fails
it.

**After the L3.14 repair (development only, D22):** on a 125-row sample matched
across every predictor, the engine remains decisively worse:

| predictor | MAE | RMSE | bias |
|---|---:|---:|---:|
| repaired engine | **0.2955** | 0.4340 | +0.2496 |
| last observation | **0.1255** | 0.2214 | +0.0095 |
| median of last 3 | 0.1348 | 0.2390 | +0.0044 |
| mean of last 5 | 0.1486 | 0.2301 | +0.0155 |

At 20+ prior context-specific observations only four matched rows remain, so
their 0.2716 versus 0.0641--0.0897 comparison is descriptive, not settled
evidence. The repair is admissible for prospective testing; it is not a claim
that the real-data failure is solved.

| matched sample | engine | last observation | verdict |
|---|---:|---:|---|
| all scored sets (n=162) | **0.3148** | **0.1427** | beaten by 2.2× |
| 20+ prior observations (n=21) | **0.3513** | **0.1333** | beaten by 2.6× |

Every baseline beats it, and every margin clears its own interval — the settled
comparison is −0.218 ± 0.118. Pooled across all 288 scored sets the MAE is
0.2682 with a bias of **+0.1797**: the engine expects the athlete to lift about
18% less than they do, systematically.

For scale, the same engine on synthetic data scored MAE 0.0397 and tied
mean-of-last-five. **The real-data MAE is roughly eight times larger.**

**A structural difference was claimed here, and it was overstated.** The
original entry reported that only 21 of 288 scored sets (7%) had twenty or more
prior observations, and that 3 of 31 exercises reached twenty. **Both figures
counted scored *sessions*, not capacity updates**, and the engine updates
capacity once per *eligible set* — 797 updates against 288 scored sets.
Re-measured with the estimator's own counter:

| | as first reported | actually |
|---|---:|---:|
| exercises reaching 20 | 3/31 | **14/31** |
| median per exercise | 8 | **19** |
| total | 288 | **797** |

The engine has roughly 2.8× the evidence the entry credited it with. Sparsity
still hurts confidence and new exercises, but it is **not** the decisive
failure, and the "almost the entire run is warm-up" framing was wrong. This was
the thirteenth measurement error of the class D19 exists to catch, found by an
external audit rather than internally — the register's own prediction that a
further one existed was correct.

**That is a decomposition, not an excuse, and it is not sufficient.** The engine
loses on the settled subset too, by a wider margin than on the pooled one. Nor
does the bias decay the way pure warm-up would: by experience it runs +0.16 /
+0.26 / +0.13 rather than falling monotonically. It does decay by calendar time
— +0.226, +0.183, +0.123, +0.072 across four blocks — which is consistent with
capacity maturing but does not distinguish that from anything else changing over
twenty months.

**Candidate explanations, none of them checked** (D19 — a plausible explanation
is not a check, and this is exactly the moment the rule exists for):

- the warm-up regime, per above, which is measured but insufficient;
- the athlete's RPE reporting habits differing from the Zourdos conversion the
  engine assumes — 862 of 976 sets carry an RPE and every one is inverted
  through a population curve;
- 114 unrated sets imputed at the athlete's recent reserve (D18);
- recalled body mass on bodyweight exercises (LIM-30);
- genuine misspecification of the fatigue-to-performance model on a real person.

Each is testable. **Every test consumes the holdout further**, because a model
change made after seeing these numbers is exactly what `BUILD_PLAN.md` L3.12
means by spending the resource. The seal records one scoring opening; a second
would have to be reported as a weaker claim.

**What this does not overturn.** The synthetic results stand as what they always
claimed to be — evidence that the engine recovers known latent structure under
noise, which is a question only a simulator can pose. This is the different
question, and the answer so far is that internal coherence has not transferred.

### LIM-32 — Confidence behaved correctly on real data
**Status:** `closed` · **Found:** L3.12

Recorded because it is the one part of the system the cold run vindicated, and
a register that only collects failures misrepresents the thing it describes.

- Withholding wearables cost **−0.2083** on 83 blank nights, against a
  synthetic-data figure of −0.2819. `DATA.md` §19.8 asks that missing data
  reduce confidence rather than fabricate fatigue, and it does.
- **5 of 286** capacity readings before twenty sessions of an exercise said
  `high`, against 88.5% before the L3.6 maturity component existed. LIM-C3's fix
  holds on real data.
- The binding reason distributed sensibly — wearable completeness 389, dose
  quality 180, baseline maturity 41 — rather than collapsing onto one term.

Confidence is not a probability (LIM-12) and this does not make it one. But the
index falls where evidence is thin, on a real record, which is what it was built
to do.

## Found by the pre-Checkpoint-3 audit

Eight open or mitigated, one closed. Found by `tools/layer3_audit.py`, which re-derives every
`DATA.md` §19 metric from the written dataset and a fresh engine run rather
than trusting `rhome_eval`. None is an arithmetic error — the harness computes
what it says it computes, to 1e-9. All seven are errors in *what is being
measured*, which is the class this project keeps finding.

### LIM-16 — Four scenarios exist only inside the sealed holdout
**Status:** `open` · **Found:** L3 audit

| scenario | days | window |
|---|---|---|
| S5 chronic sleep compression | 545–558 | holdout only |
| S10 PR window | 590–599 | holdout only |
| S11 random bad day | 612, 638 | holdout only |
| S12 missed-session block | 660–669 | holdout only |

`DATA.md` §19 names three of these as acceptance criteria — §19.5's
missed-block confidence rule (S12), and §19.7's bad-day and PR-window rules
(S11, S10). None can be evaluated on development data, so each is verified
against a constructed substitute: S12 by a 60-day-plus-14-blank-day toy, S11 by
a hand-scaled session, S10 not at all.

There is no natural analogue either: the **longest training-free stretch in the
entire 520-day development window is three days**, against S12's ten.

`DATA.md` §15 requires that "scenario families should appear in both windows";
§14's recommended chronology places all four after day 530. The generator
followed §14 and broke §15, and nothing recorded the conflict. `S3_deload` at
515–529 also straddles the boundary.

**Fix:** a development-window instance of each, which requires regenerating the
dataset — so it is a v0.2.0 decision, not a patch.

### LIM-17 — Each of the five guardrails has a live evasion
**Status:** `open` · **Found:** L3 audit, by attempting the violation

| # | Guardrail | What got through |
|---|---|---|
| 1 | Import boundary | `importlib.import_module("rhome_sim.…")`; `__import__`; `Path("…") / "hidden"`; `Path("data") / "real"`. The markers require a slash (`"hidden/"`, `"data/real"`) that this codebase's own pathlib style never produces. |
| 1 | Sealed real data | `real_oura/` and `spotr_data/` hold the *originals* the sealed copies were made from. Neither is in `data/real_manifest.json` nor matched by `_SEALED_MARKERS`. |
| 2 | Frozen projections | Re-freezing is caught; **freezing after the session is not**. `frozen_at_h` is stored and hashed and never compared to anything. The ordering rests on statement order in `RhomeEngine.process_day`, though `performance.py` states it is enforced. |
| 3 | Parameter registry | 21 of 105 parameters are "proved read" only by an f-string *inside their own `register()` call* — `phi_stimulus_*`, `phi_fatigue_*`, `phi_neuromuscular_*`, `steps_local_*`. No live drift, because the registry and the arithmetic share one dict; but the check reports 105/105 when its real coverage is 84/105. This is D17's failure recurring inside the fix for D17. |
| 4 | Deterministic seeding | The static scan catches `np.random.normal(…)` and nothing else — not `np.random.default_rng()` unseeded, not `import numpy.random as nr`, not `random.Random()`. What actually protects the project is the behavioural regeneration test, which covers `rhome_sim` only. |
| 5 | Conformance map | **No test enforces it.** `conftest.py` *writes* `build_log/conformance.md`; nothing asserts on it. A clause registered with no test was planted and the suite still reported 842 passed while coverage fell to 99%. Markers are also collected at *collection* time, so a skipped or failing test still counts as covering its clause. |

D3 requires guardrails to be tested against planted violations. They are — but
each test plants the one spelling its author had in mind. D15's rule that a
guardrail must assert its own *scope* is met by none of them.

**The holdout seal has the same shape.** `run_engine(days, Window.HOLDOUT,
seal=HoldoutSeal())` runs all 210 holdout days, records nothing, and the run's
`caveat` reads `"holdout unopened"`. The guard tests `seal is None`, not that
the seal came from `open_holdout()`.

### LIM-18 — The committed dataset no longer regenerates from its seed
**Status:** `closed` · **Found:** L3 audit · **Closed:** L3.9

`tools/layer1_audit.py` was red at 52/53 and had been since L2.1. `INDEX.md`
marked the Layer 1 audit passed; nobody had re-run it.

One file of twelve differed: `metadata/raw_dirty.csv`. Every `observable/` and
`hidden/` table reproduced byte-for-byte, so **no Layer 3 number was
affected**. The cause was clean: `rhome_sim/missingness.py` last changed in
commit `7bbcbda` ("L2.1"), when the parser's bounds were corrected; the dataset
was written at L1.8 and never regenerated.

**Closed at L3.9**, by the regeneration that added the library pin. Exactly the
two predicted files changed — the stale dirty-row fixture and the config — and
every observable and hidden table came back byte-identical, which is the
measurement that closes it. `tools/layer1_audit.py` now reports **53/53**.

The artefact is versioned **0.1.1** rather than left at 0.1.0. The evaluated
data is byte-identical, so every Layer 3 result carries over unchanged, but two
different byte-sequences must not share one version string — that is the
failure the version exists to prevent.

**What the stale fixture had been hiding.** It documented two defect classes
the parser no longer has: a pounds-without-a-unit-change repair, and a
plausibility check that rejected `140 kg x 20 reps at RPE 10`. Both were lost
when the bounds were rewritten at L2.1, and the ingest module documents the RPE
floor correction at length while saying nothing about either. **That row is now
accepted as a working set and feeds capacity estimation.** Whether the
plausibility check should return is a separate question, recorded as [LIM-25].

### LIM-29 — The athlete's logger cannot mark a warm-up
**Status:** `closed` · **Found:** L3.11 · **Closed:** L3.11, same day

Spotr's `set_wdf` takes exactly one value, `Dropset`. There is no warm-up
marker, so a logged warm-up would arrive carrying full dose and inflate every
fatigue state at L3.12 — evenly, and therefore invisibly.

**Closed by the athlete: they have never logged a warm-up.** Spotr can record
them; they simply never have. There are no warm-up rows to misread, so the
concern does not arise.

Worth stating what this does *not* mean. Warm-ups happened — they are just
absent from the record. The model treats an unlogged warm-up exactly as it
treats a logged one, which is as carrying no dose, so no bias is introduced
either way. The real consequence is narrower and lives elsewhere: the athlete's
log is **entirely working sets**, so the set-type machinery built at L2.1 goes
almost wholly unexercised on real data, and only `Dropset` will test it.

Recorded as closed on the athlete's own account rather than on a measurement,
because verifying it means reading loads and repetitions. L3.12 will corroborate
it for free: a log with no warm-ups has no light leading sets to find.

### LIM-30 — Body mass is recalled, not measured, and absent before August 2025
**Status:** `mitigated` · **Found:** L3.11 · **Mitigated:** L3.11

Neither source carries body mass. `health_data` records `hrv`, `resting_hr`,
`sleep_hours`, `readiness_score` and `active_calories`; Oura's trends export
carries none; the only figure anywhere is `user.weight_in_pounds`, a single
current value. The athlete has never tracked it.

**Mitigated with four recalled anchors**, committed to
`data/real_body_mass.json` and labelled as recollection everywhere they appear:

| date | kg | the athlete's words |
|---|---:|---|
| 2025-08-15 | 61.0 | "August" |
| 2026-01-01 | 63.0 | "December/January" |
| 2026-04-20 | 66.0 | "mid/end April" |
| 2026-08-24 | 65.5 | "now" |

Two decisions keep this honest.

**Linear between anchors, nothing outside.** Extrapolating past the first or
last would invent a trend where there is not even a recollection. **241 days of
the Oura record precede the first anchor** — 17 December 2024 to 15 August 2025
— and on those days body mass stays unknown, so bodyweight exercises contribute
dose and no performance observation. That is what the engine already does with
an unknown body mass, and it is the correct answer.

**No synthetic fluctuation.** Real scale readings carry about a kilogram of
water and gut content, and `BodyMassTracker` smooths them with a seven-day
median for that reason. Adding invented noise would make recalled figures look
measured, and the smoother would then dutifully remove variation that never
existed. A straight line between two recalled points is the honest shape of a
recalled quantity. A test asserts the daily delta is constant between anchors,
so noise cannot be added later without failing.

**What it still costs.** Body mass enters `effective_load` as
`bodyweight_fraction × mass + external`, so on a pull-up at
`bodyweight_fraction ≈ 1.0` an error of 1 kg on 65 kg is ~1.5% of load, carried
straight into observed performance and hence capacity. The anchors are recalled
to the nearest kilogram or so, and the interpolation between them is a straight
line through what was probably not a straight process. **Every capacity figure
for `Pull-Up`, `Chest Dip (Weighted)` and `Decline Push-Up` at L3.12 therefore
carries a few per cent of uncertainty that is not the model's**, and the
scorecard must say so rather than reporting them beside barbell lifts as though
they were equally well founded.

**Fix:** a weight-tracking feature is planned for the product, which collects the
data live and makes this a warm start rather than a reconstruction. Until then
the anchors stand and are marked.

### LIM-28 — The matcher's candidate list can omit the obvious answer
**Status:** `open` · **Found:** L3.10, during the athlete's review

`tools/propose_exercise_mapping.py` offers the four highest-scoring library
names as candidates. For a query whose *plain* form exists in the library, the
plain form can lose to four decorated variants of itself: "Barbell Back Squat"
was offered `paused_back_squat`, `barbell_jump_squat`, `barbell_split_squat` and
`competition_back_squat`, while `high_bar_back_squat` and `low_bar_back_squat`
appeared nowhere.

The athlete correctly chose *derive* from what was shown, which would have
replaced curated coefficients on their heaviest systemic lift with values
inferred from muscle tags, and docked dose-quality confidence on every set of
it. Caught by asking before freezing.

**Why it matters beyond the one row.** A candidate list that never contains the
obvious answer is worse than a low-confidence one, because the reviewer cannot
distinguish "the library lacks this" from "the matcher did not offer it". The
derive escape exists for the first case and silently absorbed the second.

**Fix:** the candidate list should be diverse rather than merely top-scoring —
include the shortest or least-qualified id sharing the query's core tokens,
alongside the highest scorers. Not applied: the review is complete and reworking
the matcher now would invalidate a frozen artefact for no gain. It matters when
the mapping is next rebuilt, which is when the library changes.

### LIM-27 — SQLite's read-only mode writes inside the sealed directory
**Status:** `mitigated` · **Found:** L3.10 · **Mitigated:** same stage

The L3.10 extractor opened the sealed Spotr archive with `mode=ro` in a SQLite
URI. The archive is in WAL journal mode, so SQLite created `-shm` and `-wal`
sidecar files **inside `data/real/`** on open. `tools/seal_real_data.py verify`
reported the seal broken immediately: *0 missing, 2 added, 0 changed*.

No harm was done — the `-wal` was zero bytes and the archive's own digest was
unchanged — and the guard caught it within seconds of the mistake being made.
That is the seal working rather than failing, and it is recorded here because
the *reasoning* that produced the mistake was sound: read-only ought to mean
read-only, and it does not.

**Mitigated** by copying the archive to a temporary file and querying the copy,
so SQLite never opens the sealed file. A test forbids `mode=ro` in the
extractor's executable code and requires the copy.

**Not closed, because it generalises.** Any future tool touching `data/real/` —
L3.11's adapter above all — must copy first. Nothing enforces that beyond this
one file: Guardrail 1's sealed-data markers check for path *references*, not for
whether an opened handle can write. A check that `data/real/` contains exactly
the three manifest files, run after any tool that touches it, would close this.

### LIM-26 — The D16 fold understates fatigue on 302 library rows
**Status:** `open` · **Found:** L3.9

D16 folds twelve finer muscle labels into the sixteen model groups. Loading the
athlete's library for the first time showed a consequence nobody had
anticipated: in **302 of the 1 074 rows** the fold collapses two labels onto one
group *across tiers*. `bent_over_barbell_row` names `posterior_delts` as a
secondary mover and `rotator_cuff` as a stabiliser; both become
`posterior_delts`.

| labels colliding | rows |
|---|---:|
| `posterior_delts` + `rotator_cuff` | 103 |
| `abs` + `obliques` | 59 |
| `abs` + `deep_core` | 51 |
| `traps` + `upper_back` | 47 |
| `hip_flexors` + `quads` | 26 |

Resolved by keeping the **highest tier**, so a mover is never demoted because a
finer label for the same group appeared below it.

**The cost, stated rather than hidden.** Taking the maximum rather than the sum
means such a row contributes the secondary coefficient (0.50) instead of
secondary plus stabiliser (0.50 + 0.20) — a small understatement of fatigue on
28% of the library. The alternative is worse: summing would count one
anatomical structure twice because the library named it twice, and the fold is
the reason it was named twice.

Inert on v0 — zero collisions there, asserted by a test, because if it ever
becomes non-zero the dataset every Layer 3 number was measured against has
silently changed.

**Fix:** none available inside a sixteen-group taxonomy; it is the price of
D16, now measured. It would disappear if the finer labels became model groups,
which D16 rejected for reasons that still hold.

### LIM-25 — The parser lost two defect classes at L2.1 without recording it
**Status:** `open` · **Found:** L3 audit, isolated at L3.9

Regenerating the dataset at L3.9 revealed what the stale `raw_dirty.csv` had
been preserving: the pre-L2.1 parser rejected `140 kg x 20 reps at RPE 10` as
"physiologically impossible" and repaired `220 kg` on a bench press as a
pounds-for-kilograms error. The current parser has only absolute bounds — load
under 500 kg, repetitions under 100 — so both rows now pass.

The consequence is concrete: a set that is internally contradictory, in that
its load and its repetition count cannot both be true of the same athlete, is
accepted, transformed and used to update capacity.

`DATA.md` §17 asks for the `raw_dirty` fixture precisely to pin the parser's
contract, and the fixture drifted out of the suite's view because nothing read
the written copy. The live fixture in `rhome_sim.missingness` was updated to
match the weaker parser rather than the parser being questioned.

**Not fixed here.** Restoring a plausibility check means deciding what is
implausible using the athlete's own history, which is exactly the class of
judgement `rhome_engine.ingest` currently refuses to make — its bounds "reject
the physically impossible only; anything requiring the athlete's history
belongs where capacity is known". That is a defensible line and the fix has to
respect it, so this is a design question rather than a patch.

### LIM-19 — Set timestamps do not exist, on either side
**Status:** `open` · **Found:** L3 audit

`DATA.md` §18: *"Set timestamps are explicit and spread realistically across
the session, not collapsed onto the session start."* Neither side does this,
and §5.3's schema for `sets.csv` defines no timestamp column, so the clause
cannot be satisfied by the written dataset as specified.

| | session span |
|---|---:|
| logged (`workouts.csv` duration, median) | **138 min** |
| engine (sets at 0.02 h apart, median 21 sets) | **25 min** |
| simulator (`Physiology.apply_set` never advances time) | **0 min** |

The two sides are wrong in opposite directions. At a 30 h half-life, 138
minutes is about 4.6% of decay — small, but it lands directly on the §19.4
bands, which are read "24 h after the most recent session", and on every
within-session fatigue correction.

### LIM-20 — The latent pairing is right in days and 8.5 hours out
**Status:** `open` · **Found:** L3 audit

`LATENT_OFFSET_DAYS = 1` is correct and dominant — re-derived, offset 1 scores
+0.949/+0.956/+0.973 against +0.447/+0.277/+0.387 at offset 0 and
+0.518/+0.296/+0.441 at offset 2. But the instants it pairs are not the same
instant. The engine's day-N state is captured at `WAKE_H + 16.0` = **23:30**;
the simulator's `state_on_waking` is at **08:00**. The pairing therefore
compares states **8.5 hours apart, across the whole overnight recovery**, and
`run.py`'s comment says they "line up".

No integer offset closes it, because the engine never emits a waking-time
state. Every §19.1 correlation and RMSE is measured across that gap, and the
fitted scale alignment absorbs part of it into its multiplier.

**Fix:** have the engine emit a state at the next waking as well as at the
close of day, and pair on that. Cheap, and it would make the alignment mean
something narrower.

### LIM-21 — The §19.4 bands describe the engine, not the simulator
**Status:** `mitigated` — D21 option 2 executed in `DATA.md` v0.9.0; engine
absolute-calibration gap remains open · **Found:** L3 audit ·
Interacts with [LIM-2] and [LIM-8]

`DATA.md` §19.4 says the bands "are checked against the simulator's own
suppression". Measured on both sides:

| case | engine | simulator | band |
|---|---:|---:|---|
| fresh, after a deload week | 1.36% | 1.07% | 0–1.5% ✅ |
| one ordinary hard session | 5.87% | 6.00% | 4–6% ✅ |
| one failure-heavy session | 7.51% ⚠️ | 9.26% ❌ | 5–7% |
| ordinary training week | 7.34% | 8.18% ❌ | 6–8% |
| within a failure-heavy block | 9.37% | 13.16% ❌ | 8–10% |
| peak of an overload block | 14.97% | **25.67%** ❌ | 13–16% |

The engine is in band 5 of 6 (LIM-8 covers the one miss). **The simulator is in
band 2 of 6**, and at the overload peak sits 9.7 points above the top.

So "5 of 6 in band" is the engine agreeing with a target derived from the
engine's own λ values. The consequence for L5.3 is concrete: fixing LIM-2 moves
the engine *toward* the simulator and therefore *out of* these bands, so a
correct improvement will present as a failed acceptance criterion.

**Settled in advance by D21.** The bands do not gate L5.3, which is judged on
its own four criteria. When suppression leaves a band, one of three named
options is chosen with its reason stated *before* the new figures are read:
re-derive λ, revise the bands and version `DATA.md`, or question the
simulator's own curve — whose non-linearity constants are D8 simulator
invention, carry no evidence grade and have never been checked against
anything. The pre-registration is the point: chosen afterwards, "adjust the
bands" is indistinguishable from fudging.

One further protocol note: §19.4's table header reads "evaluated 24 h after the
most recent session" and applies to every row, but the fresh case places its
newest session at 48 h.

**D21 executed at L3.14.** The simulator-centred Grade-C bands are now
0--1.5%, 5--7%, 8--10%, 7--9%, 12--14% and 24--27%. The simulator is inside all
six. The repaired engine reads 1.11%, 5.44%, 6.94%, 6.82%, 8.68% and 14.14%:
inside two and below the simulator on every accumulated case. The bands were
not widened to fit it. This is now a visible open calibration gap rather than
an acceptance target that rewards the linear engine.

### LIM-22 — `MODEL.tex` bounds a set and concludes about a session
**Status:** `closed` — derivation corrected and product limit approved ·
**Found:** L3 audit · **Corrected:** `MODEL.tex` v0.5, `DATA.md` v0.8.0

`DATA.md` §19.7 requires one anomalously poor session to move a settled
capacity estimate by less than 1%. `MODEL.tex` §Estimation of underlying
capacity explains why it does:

> The clip at $c=0.10$ bounds the influence of any single **set** to a 0.6%
> movement in capacity at the base rate, **so one anomalously poor session** —
> scenario S11 — produces a large negative residual without depressing capacity.

The first clause is correct: $e^{\alpha c}-1 = 0.602\%$ at $\alpha=0.06$. The
second does not follow from it. A session is not a set — the engine updates
once per *eligible* set, which that same section specifies — and a real session
carries two to five, one of which may be an anchor test at $\alpha=0.20$.

So the derivation is right and the conclusion drawn from it is wrong, and
everything downstream inherited the error: §19.7's 1% threshold, and the test
that checked it by applying exactly one `update_capacity` call.

**Measured on the real log**, at 28 prior observations, across 18 sessions and
three exercises:

| | |
|---|---:|
| median displacement | **2.1%** |
| worst | **3.3%** |
| after 90 days | under 0.2% |
| per-set bound | 0.602% |
| closed-form session bound, 4 sets at base rate | 2.43% |
| closed-form session bound, 2 sets with an anchor | 3.92% |

**A second consequence, unnoticed until now.** Any innovation beyond the clip
is clipped to the same value, so a 14% miss and a 40% miss move capacity
*identically*. The engine's response to a bad session does not depend on how
bad the session was. It depends on how many eligible sets it held and whether
one was an anchor.

That also means the old stand-in's choice of a 40% miss was never doing
anything — scenario S11's own magnitude is a median 13.9% shortfall, and the
test's severity was decorative.

**What was done.** `MODEL.tex` v0.5 replaces the invalid inference with the
derivation carried through — a session of $n$ eligible sets is bounded by
$n\,\alpha_{\max}c$ — and adds a paragraph stating that the clip saturates, so
the estimator cannot see how bad a session was. `DATA.md` v0.7.0 re-derives
§19.7 from that bound and records the measured session-level figures in place
of the stand-in's.

**This is a derivation fix, not a widened band.** The distinction matters
because §19.4 forbids the latter and D21 was written to hold that line. The 1%
was never an independent acceptance criterion the engine failed: it was
`MODEL.tex`'s per-*set* figure restated as a per-*session* threshold, and the
profile beside it (3.3% / 1.0% / 0.6%) was measured by applying a single
update. Correcting arithmetic is not the same act as moving a target to fit a
result.

**The product judgement is now resolved.** On 24 August 2026 the athlete
approved v0 non-inferiority as the hard floor: median immediate displacement no
greater than 2.1%, worst no greater than 3.3%, and ninety-day residue below
0.5%. `DATA.md` v0.8.0 scores that gate before accuracy and the evaluation code
refuses to rank a fragile candidate, however low its MAE. A more responsive
estimator therefore needs a per-session bound or an equivalent two-timescale
mechanism; that implementation remains LIM-34, not an open part of LIM-22.

`single_bad_day_displacement` — the instrument written to measure exactly this
"by running the engine twice over the same log", and called by nothing — now
works and is called by the test suite and the audit.

### LIM-23 — A deload rebound is attributed to new capacity, not to lost fatigue
**Status:** `open` · **Found:** L3 audit · Consequence of [LIM-2]

`DATA.md` §19.7 requires post-deload performance gains to be "attributed
principally to reduced fatigue rather than to a sudden capacity increase,
verified by decomposing the projected change".

Projected performance is $\bar P_e(1-s)$, so the change across a deload
factors exactly, in log space, into a capacity part and a fatigue part. The
decomposition is exact to 1e-9, and it says the opposite of the requirement:

| across an S3 deload | |
|---|---:|
| attributed to capacity | **+0.0116** |
| attributed to reduced fatigue | +0.0034 |
| ratio | **3.4×** |
| capacity movement across matched ordinary gaps | +0.0035 |
| **excess attributable to the deload** | **+0.0080 ± 0.0025** |

The control is the substance. Capacity rises across any three weeks of
training, so "capacity rose across the deload" proves nothing — this is the
trap L3.4 fell into three times on this same metric. Only the excess over a
matched ordinary stretch is attributable to the deload, and it is significant.

**The mechanism is legible and is [LIM-2].** The engine removes the fatigue it
*believes* was acting before an observation updates capacity. Because it
accumulates fatigue linearly it understates how much fatigue the deload
removed, so the part of the rebound it cannot explain by freshness is absorbed
as capacity instead. The engine expresses roughly 70% of the true contrast
elsewhere; here the missing 30% has to go somewhere, and it goes into capacity.

**Product consequence, stated plainly:** after a deload the app will tend to
tell the athlete they have got stronger, when what has actually happened is
that they have got fresher. That is the specific false and encouraging claim
§19.7 exists to prevent.

**Fix:** expected to follow from L5.3. Whether it does is a concrete,
falsifiable prediction and should be added to L5.3's acceptance criteria: if
non-linear accumulation is the cause, this ratio must invert. If it does not,
the cause is something else and this is a defect in its own right.

**The prediction failed at L3.14.** The admissible curvature improves the
post-/pre-deload ordering ratio from 0.564 to 0.678, but attribution moves the
wrong way: capacity is now **4.0×** the freshness contribution, against 3.4×
before, and deload excess over matched ordinary gaps is
**+0.0124 ± 0.0045**. Curvature fixes a relative contrast without fixing what
the estimator calls the rebound. LIM-23 therefore remains an independent
defect rather than being closed with LIM-2.

### LIM-24 — `DATA.md` §19.7 was never in the conformance map
**Status:** `mitigated` · **Found:** L3 audit · **Mitigated:** same day

Seven of the eight subsections of `DATA.md` §19 carried registered conformance
clauses. §19.7 — the capacity-estimator tests, five separate requirements —
carried none. Coverage read **100% throughout**, because coverage is measured
against the register and nobody had asked whether the register was complete.

This is D15's rule — a guardrail must be shown to cover everything it claims —
applied to the map rather than to a test, and it is the fourth appearance of
the same shape: correct on what it examined, silent about what it never
reached.

Registering the five clauses immediately exposed **two failing acceptance
criteria** — [LIM-22] and [LIM-23] — that had been unmeasured since L2.4.

Four of the five now have tests. The fifth is [LIM-22], which is pinned to its
measured behaviour rather than to §19.7's threshold until the decision there is
taken.

**What is not fixed:** the register is still only checked against itself.
Nothing verifies that every testable clause of the specification has a clause
id, so a whole section can go missing again. Guardrail 5's other failure —
[LIM-17], that no test asserts on coverage at all — compounds it.

### LIM-35 — An index row with a wordy status is invisible to the integrity tests
**Status:** `open` · **Found:** L6.2 · **Cost:** the checkpoint gate can pass
over such a stage, which is the failure it was built to catch

`tests/test_build_log_integrity.py` parses `INDEX.md` with

```
ROW = re.compile(r"^\|\s*(L\d+\.\d+|—)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|")
```

The status group is `(\S+)` followed immediately by a pipe, so a cell reading
`⚠️ simulator only` or `✅ authored` does not match and **the whole row is
skipped silently**. It is not reported as malformed; it simply does not exist
as far as the tests are concerned.

Two rows are currently affected. `L6.1` was caught only because a
`L6.1_ios_logger.md` file existed and the orphan test noticed the missing
row — the row was there all along. `L5.1` is still unparsed and escapes
notice only because no `L5.1_*.md` file exists.

The consequence is the one that matters: `test_no_checkpoint_passes_over_an_unbuilt_stage`
walks the same rows. A stage marked `⬜ not yet` rather than `⬜` is not
counted as pending, so a checkpoint after it passes. That is precisely the
Checkpoint 0 / L0.4 failure this test was written for, reachable through the
formatting of a status cell.

**The shape, for the fifth time:** correct on what it examined, silent about
what it never reached ([LIM-24], [LIM-17]).

**What would fix it:** parse the status cell as everything up to the next pipe
and match on its leading marker, and fail loudly on a row that begins with a
stage id but does not parse — an unparseable row is evidence of a problem, not
an absence of one. Not done here because it changes the semantics of a
guardrail test, which deserves its own stage rather than a fix folded into an
ingest adapter.

### LIM-36 — No working method exists to validate latent fatigue on real data
**Status:** `open` · **Found:** L3.15 · **Cost:** no readiness readout, and no
instrument capable of telling us whether the muscle ordering is right

**The paired directional design is void.** Run on synthetic data, where the
engine reconstructs latent local fatigue at +0.941 cross-sectionally, it scores
**49.0% on n = 4228** against a ceiling of 54.6% that would sit ~6 SE from
chance. It fails to detect a model known to be nearly correct, so the real-data
result below refutes nothing. See `tools/directional_fatigue_control.py`.

**The signal-to-noise finding survives and is the important one:** observed
performance noise is 4.9x larger on the real athlete than in the simulator,
predicted contrast 1.6x smaller — the fatigue signal is **7.8x weaker relative
to noise in reality**. Every synthetic criterion has been calibrated in
conditions much quieter than reality.

Paired within-session on the 99 historical sessions, the engine ordered which
of two muscles underperformed at **71/143 = 49.7%** (p = 1.0000). No baseline
cleared chance either. The instrument was verified: a predictor fed the answer
scores 143/143, its inverse 0/143.

**That null is uninformative and must not be read as a refutation.** With
observed = effect + independent noise, a *perfect* predictor of an effect the
size the engine predicts scores

| | |
|---|---:|
| sd of predicted pair gap | 0.0060 |
| sd of observed pair gap | 0.3243 |
| perfect-predictor score | **50.6%** |
| distance from chance at n = 143 | 0.14 SE — not detectable |

The engine scored 49.7% and a flawless model would have scored 50.6%. The test
cannot separate them.

**What is established is the size.** Predicted within-pair contrast is **1.8%**
of the observed variation; median predicted gap 0.0032 against median observed
0.179; only 10 of 143 pairs carry a predicted gap above 1%. A perfect model
would need to be **18× larger** to reach 60% on this measurement. Whatever its
direction, a signal this faint cannot drive a display.

**Where the contrast is lost.** The state itself is not flat — local fatigue
spans a median 0.748 across the sixteen muscles at training time. Three
downstream compressions were measured: the performance-weight vector averages
over a median of **6** muscles with only **0.556** of its weight on the primary
movers (bench press puts 0.385 on chest); `λ_local = 0.065` scales the result
again, giving a median suppression of 0.0240 against a clip of 0.25 that is
never approached; and all sixteen muscles share one half-life ([LIM-37]).

**Note the separability:** raising λ_local changes the effect *size* without
altering a single directional call, since `sign(k·x) = sign(x)`. Size and
direction are independent levers and only size has been measured.

**What would answer the direction question:** a higher-contrast comparison —
a muscle trained within 24 h against one untrained for five days — where the
effect is not swamped by ordinary variation. Buildable on the same 99 sessions.

**Contrast with the synthetic result.** The same quantity correlates +0.966
with the simulator's true latent fatigue. Both hold: the engine reconstructs
the fatigue its own generator produced, and on a real athlete predicts
contrasts too small to be checked by this method.

> **Qualified at L3.17.** That +0.966 is real but its usual companion figure
> is not: the +0.520 counter it was reported against had no muscle
> attribution. A counter given the authored muscle map reaches +0.955, so the
> engine's per-muscle advantage on synthetic data is +0.010, not +0.446. See
> [LIM-40].

### LIM-37 — Sixteen muscles share one fatigue half-life, against the specification
**Status:** `open` · **Found:** L3.15 · **Cost:** muscles cannot differ by
recovery rate, only by dose received and time elapsed

`MODEL.tex` §576 defines the local-fatigue decay "where $h_m$ is a
muscle-specific half-life", and the parameter table §1261 gives "Local fatigue
half-life & 24--42 h, mean 30 h".

The implementation reads a single scalar:

```python
# state.py:99
self._local_half_life = ENGINE_PARAMETERS.value("local_half_life_h")   # 30.0
...
for muscle in Muscle:                       # all sixteen
    decay_with_constant_input(previous, rate, self._local_half_life, dt, rho)
```

The **mean of the specified range** is applied to every muscle. A calf and a
spinal erector recover at identical rates, which the specification explicitly
does not say.

This is a specification/implementation divergence rather than a tuning choice,
and it was not caught because no test asserts the plural form — Guardrail 3
verifies that registered values match `MODEL.tex`, and `local_half_life_h`
does match a number that appears there. It is the same shape as [LIM-24] and
[LIM-C4]: correct about what it checked, silent about what it never reached.

**Note the interaction with [LIM-13]:** sixteen per-muscle half-lives are
listed there as "thin from one person's record at any length". Deriving them
from this athlete is not currently possible; adopting differentiated priors
from the literature is, and is the cheaper first move.

### LIM-38 — Novelty inflation fires for movements the athlete already knew
**Status:** `open` · **Found:** L3.15 addendum, raised by the athlete ·
**Cost:** fictitious local-fatigue inflation on 42.4% of the real log

The athlete's Oura history starts 17 December 2024; training logging did not
begin until 29 October 2025 (day 316 of the joined calendar) — 316 days later,
not because he began training then, but because that is when the log began.
He has several years of prior training history the log does not capture.

The long quiet gap itself is harmless: at a ~30 h local half-life, fatigue
decays to zero within about two weeks and stays there regardless of the cause.
**Novelty does not decay away the same way** — `novelty_for` (`state.py:280`)
is keyed to the engine's own exposure count for an exercise id, which starts
at zero at day 0 of whatever calendar it is given. So every exercise's first
*logged* appearance is scored as a true first exposure and inflates local
fatigue by up to 25% (`novelty_cap = 1.25`, decaying over
`novelty_decay_exposures = 4.0` sets) — a mechanism that is correct for a
genuine beginner and fictitious for this athlete.

Measured directly (`tools/novelty_seeding_check.py`), by capturing every
`novelty_for` call the engine actually made, in order:

| | |
|---|---:|
| working sets with materially inflated novelty (>1.02) | **414 / 976 = 42.4%** |
| sets inflated more than 10% | 191 / 976 = 19.6% |
| sets scored as a true first exposure (novelty = 1.25) | **55** — one per distinct exercise |
| mean novelty, first 200 chronological sets vs last 200 | 1.090 vs 1.049 |
| equivalent extra full-novelty-set dose injected, summed | ≈ 48 sets |

Concentrated early, as expected, but not negligible: over 40% of the entire
log is touched.

**What is not affected.** Capacity estimation starts fresh per exercise
regardless of true history, which is correct — the log genuinely carries no
capacity evidence before its own start (the already-known, already-mitigated
[LIM-4]). `adaptation` was checked and is tracked in state and traces but does
not feed into `expected_suppression`, so it is cosmetic.

**Not yet fixed.** The natural fix is to seed each exercise's exposure count
as "familiar" at the start of real-data ingestion — a change to the ingest
adapter (`rhome_eval.spotr` / `rhome_eval.rhome_logger`), not to the model or
its parameters. Included in the L3.15 external diagnostic
(`DIAGNOSTIC_FOR_REVIEW.md`, Note 0 / H6) because it is a genuine confound
inside exactly the data that diagnostic analyses.

### LIM-39 — A model version churns faster than the model changes
**Status:** `open` · **Found:** L3.16 · **Cost:** freeze dates reset for edits
that cannot move a prediction

`rhome_eval.version` digests the engine's sources whole rather than parsing
them, so a comment or docstring edit anywhere in `src/rhome_engine/` or
`src/rhome_core/` produces a new version digest and a new freeze date, even
though no prediction can have changed.

This is deliberate and is the safe direction to be wrong in: a spurious
"different version" costs a re-freeze, a spurious "same version" costs a false
claim about data a model has already seen. The alternative — digesting parsed
behaviour and ignoring comments — puts a judgement about what matters inside
the mechanism that exists to remove judgement.

**The cost is real, though.** Under a prospective regime the freeze date
decides how many sessions count as an exam, so a documentation pass inside
those paths silently shortens the next evaluation window. One carve-out already
exists for exactly this reason, and this limitation is what remains after it:
`src/rhome_core/conformance.py` is excluded, because registering a conformance
clause is not a model change and every stage that adds coverage would otherwise
forfeit its freeze date. That exclusion is guarded by a test scanning the
engine's own source for an import of anything excluded.

**What would fix it.** Either a second digest over parsed module contents with
docstrings and comments stripped, reported alongside the literal one so a
reviewer can see "source moved, behaviour did not"; or a convention that
documentation-only edits inside engine paths are committed separately and the
freeze re-taken deliberately. Neither is worth building until a freeze has
actually been forfeited this way.

### LIM-40 — The engine's per-muscle advantage over a competent competitor is +0.010
**Status:** `open` · **Found:** L3.17 · **Cost:** the project's most-quoted
result means far less than it appeared to

For two stages the per-muscle latent claim read **+0.966 engine against +0.520
for a decaying set counter**. The counter in that comparison was a single
global accumulator with no muscle attribution, compared against each of the
sixteen in turn — so the 0.446 gap measured the absence of a lookup table
rather than the presence of a model.

Given the exercise-to-muscle map from the library and nothing else — no
repetitions, no effort, no proximity to failure, no novelty, no wearables, no
recovery multiplier, no within-session amplification — a decaying counter
scores:

| | longitudinal | cross-sectional | per-day cross-sectional |
|---|---:|---:|---:|
| engine | +0.965 | +0.941 | +0.928 |
| c_F-weighted counter | **+0.955** | **+0.934** | **+0.929** |
| primary-muscle counter | +0.902 | +0.857 | +0.843 |

Best per-muscle advantage anywhere is +0.018 (upper_back, glutes); on abs it
is +0.000. On the per-day cross-sectional measure the counter is marginally
ahead. The counter holds +0.92 to +0.935 across a 24–48 h half-life sweep, so
this is not a knife-edge tuning artefact.

**The same pattern in the other claims.** Ranking: 6/6 orderings correct, but
a counter with the library's authored columns gets 5 of them, leaving one
earned — the volume-matched failure-vs-non-failure case, where a set counter
must tie by construction. Calibration: engine 2/6 in band against the
counter's 1/6, which is the only place in the re-audit the engine leads, and
both trail the simulator's 6/6.

**What this is not.** It is not evidence the engine is wrong, and it does not
retract a measurement. Every engine figure reproduces exactly. What is
retracted is the *comparison*, and with it the claim that the per-muscle body
map has been shown to earn its place.

**The last candidate was tested and fell.** Neuromuscular peak timing was
expected to survive: the unattributed counter reached only 44.6% there against
the engine's 81.5%, and L3.2 argued that neuromuscular strain depends on
relative intensity, which no set counter has. Measured rather than assumed
(D19), a counter weighted by compoundness reaches 86.9% and one weighted by
compoundness times squared relative intensity reaches **88.5%** — seven points
above the engine.

| channel, peak within a day | engine | counter, sets only | counter, authored |
|---|---:|---:|---:|
| local fatigue | **91.5%** | 86.2% | 89.2% |
| neuromuscular | 81.5% | 44.6% | **88.5%** |
| systemic | **81.5%** | 80.0% | 80.0% |

So calibration bands (2/6 against 1/6) are the only place in the whole
re-audit where the engine leads a competent competitor.

**What would close it.** A demonstration that the engine beats an attributed
counter on something that matters. Nothing measured so far qualifies. The
remaining untested ground is recovery *kinetics under conditions a counter
cannot represent* — muscle-specific or protocol-specific recovery rates, which
[LIM-37] records the engine does not currently have either, since all sixteen
muscles share one half-life.

## Structural, and accepted

These are not defects to be fixed. They are consequences of choices made
deliberately, recorded so nobody re-discovers them as problems.

### LIM-10 — The model is load-blind in its dose channels
Dose depends only on repetitions, effort and exercise; absolute load enters the
performance channel alone. Chosen deliberately — 60 kg for a new lifter can cost
what 160 kg costs an advanced one. Verified at every audit.

### LIM-11 — Sixteen muscle groups, some of which absorb finer ones
Per D16, the athlete's library labels fold into sixteen model groups. Neck work
reads as upper-back fatigue and tibialis work as calf fatigue. Low-volume and
low-systemic, so the error is small, but it is an error rather than physiology.

### LIM-12 — Confidence is not a probability
It is an index of evidence sufficiency. `RESEARCH.md` §17 forbids presenting it
as the probability that an estimate is correct, and the claim-boundary checker
enforces the boundary on generated text.

### LIM-14 — The holdout was opened twice
**Status:** `open` · **Found:** L3.8

The seal records two openings 56 seconds apart: the tool was run once to read
the result and once to capture it to a file. Same frozen engine, same seed, same
alignment, no model change between, identical output — but the record says two
and the record is not being edited. Quietly correcting it because this second
look was innocent is exactly what the mechanism exists to prevent.

Every holdout figure in this project therefore carries the weaker-claim mark.
`tools/holdout_run.py` now writes and prints in one invocation so it cannot
recur, and a genuinely fresh synthetic holdout is available from a different
seed if a clean single-opening result is ever needed.

### LIM-13 — Everything so far is one athlete, synthetic
**Note added L3.8:** the holdout tests generalisation across *time and training
blocks* — it is the same simulated athlete, later. It says nothing about
generalisation across *people*.
Every number in this project describes one simulated athlete with one training
style. External validity is untested. The real cold run at L3.12 is a sample of
one; other users would be the first real test of generality.

---

## Closed

### LIM-C5 — The capacity target carried the simulator's per-set random shock
**Found:** L3 audit · **Closed:** L3 audit, same day, with the measurement below

`rhome_eval.run.latent_series` built "true neutral capacity" as
`true_expressible_capacity / fatigue_factor`. The simulator's chain is
capacity → fatigue → **stochastic shock** → load, and `RealisedSet` records
`performance_shock` as its own field, so that expression left the shock in the
target. `tests/test_session_driver.py` carried the same expression, so the
defect existed in two places and neither checked the other.

**The check that found it, and the check that now guards it,** is a hard floor
rather than a threshold: a quantity called *neutral capacity* cannot change
between the first and last set of one afternoon, so any within-day spread at
all means the target contains something that is not capacity.

| target | median within-day spread | p90 | max |
|---|---:|---:|---:|
| before (`cap / fatigue_factor`) | **5.12%** | 10.59% | 24.31% |
| after (`cap / (fatigue_factor × shock)`) | **0.0058%** | 0.0119% | 0.0198% |

0.0058% is the six-decimal-place rounding floor of the written CSV. Nothing
else remains.

**What the correction moved.** The `DATA.md` §19.2 capacity correlation was
*understated*:

| | before | after |
|---|---:|---:|
| mean r across 27 exercises | +0.690 | **+0.973** |
| worst exercise | lateral_raise +0.305 | calf_raise +0.939 |
| mean \|error\| after alignment | 4.43% | 4.32% |
| deload rebound, expressed | 0.424 | **0.564** |
| deload rebound, sign agreement | 34/49 | **40/49** |
| §19.3 six-case mean contrast | 67% | **70%** |

The mean error barely moved because the shock is roughly symmetric: it destroys
a correlation without moving a mean. Every check in place looked at a mean,
which is why five stages and an audit passed over it.

**It closed two questions the build log had left open**, both flagged and
neither resolved:

- L3.3: *"Capacity correlation is lower on the main lifts… likely a range
  effect… not verified, and L3.7 should check it is not something worse."* It
  was something else, and the stated pattern was not in the data — the two
  worst exercises were `lateral_raise` and `leg_curl`, both isolation. After
  the fix the spread is +0.939 to +0.990 and the main-lift/accessory
  distinction disappears entirely.
- L3.4: *"The deload rebound agrees on sign in 34 of 49 pairs… it is not known
  whether those are noise or a subset with something in common. L3.7 should
  look."* Six of the fifteen were this.

**Guarded by two tests**, both of which were shown to reject the old expression
before being kept (D3): `test_the_capacity_target_is_constant_within_a_day`
asserts the within-day spread is under 0.1% across 2127 multi-set cells and
fails vacuously below 500; `test_expressible_keeps_the_fatigue_factor_and_drops_only_the_shock`
asserts the other half, because dividing the fatigue factor out of `expressible`
as well would reproduce L3.4's second measurement error. The audit checks the
same identity in both directions — the target must match an independent
shock-free rebuild *and* must not match the pre-fix expression — so a
coincidence cannot pass.

**Direction of the error, stated plainly.** This one made the engine look
*worse* than it is, unlike the eleven before it. That is a reason for more
scepticism, not less, so what settled it was the floor argument rather than the
improvement: the spread collapsing to the rounding limit is not an
interpretation.


### LIM-C1 — Unrated working sets were discarded
**Closed:** Layer 2 audit → D18. Imputed at the athlete's own recent reserve and
marked low confidence. Day 45 read 0.9971 confidence while losing three of
fifteen sets; it now reads 0.9269 against neighbours of 0.9726 and 0.9555.

### LIM-C2 — Latent correlations were computed on a mis-aligned pairing
**Closed:** L3.1 → D19. The engine's day-N state is the close of day N and the
simulator's is on waking. Local fatigue read +0.450 where it is +0.949.

### LIM-C3 — Capacity confidence read `high` before the engine was competitive
**Closed:** L3.6. 88.5% of readings in an exercise's first ten sessions said
`high`; now none do.

### LIM-C4 — Guardrail 3 verified values the code never read
**Closed:** L2.7 → D17. Five parameters were shadowed by literals. Verification
now runs in both directions across all 105.
