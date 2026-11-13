"""Decompose the real-data failure (post-L3.12 diagnosis).

The cold run measured a failure. This asks where it comes from, by taking the
residual apart rather than reasoning about it.

    residual = log(observed) - log(capacity) - log(1 - suppression)

Three terms, three ways to be wrong: capacity too low, suppression too high, or
observed itself mismeasured. Each is separable from the run, and each has a
signature that distinguishes it from the others.

**D19 governs everything here.** Every section reports a measurement, and the
interpretation stays out of the tool. A section that could be explained three
ways says so rather than picking one, and the sections are ordered so the
cheapest discriminators come first.

**D22 applies.** This is development analysis on data that is no longer held
out. Nothing measured here can validate a fix.
"""
from __future__ import annotations

import math
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rhome_core.exercises import library_path, load_library  # noqa: E402
from rhome_core.intensity import relative_intensity  # noqa: E402
from rhome_engine.parameters import ENGINE_PARAMETERS  # noqa: E402
from rhome_engine.performance import expected_suppression  # noqa: E402
from rhome_engine.session import RhomeEngine  # noqa: E402
from rhome_eval.cold_run import assemble  # noqa: E402

REPORT = ROOT / "build_log" / "real_diagnosis.txt"
lines: list[str] = []


def say(text: str = "") -> None:
    lines.append(text)
    print(text)


def head(title: str) -> None:
    say()
    say("-" * 78)
    say(title)
    say("-" * 78)


def main() -> int:
    inputs = assemble(
        "Post-L3.12 diagnosis: decompose the cold-run residual. The holdout was "
        "already spent by the scoring run; D22 reclassifies this data as a "
        "development set.",
        kind="dry",
    )
    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    engine = RhomeEngine(library)
    results = engine.run(inputs.days)

    say("=" * 78)
    say("REAL-DATA DIAGNOSIS — where the residual comes from")
    say("=" * 78)
    say(f"\n{inputs.provenance}")
    say("Development analysis (D22). Nothing here can validate a fix.")

    observations = [(r, o) for r in results for o in r.observations]
    residuals = [o.log_residual for _, o in observations]
    say(f"\nn = {len(observations)} scored sets, "
        f"bias {st.fmean(residuals):+.4f}, MAE {st.fmean(abs(v) for v in residuals):.4f}")

    # === 1. is the bias person-level or exercise-level? =====================
    head("1. IS THE BIAS PERSON-LEVEL OR EXERCISE-LEVEL?")
    say("If every exercise is biased the same way, one pooled parameter fixes all")
    say("of them and Layer 4's partial pooling is the answer. If they scatter,")
    say("pooling cannot help and the fault is per-exercise or structural.\n")
    by_exercise: dict[str, list[float]] = defaultdict(list)
    for _, o in observations:
        by_exercise[o.exercise_id].append(o.log_residual)
    scored = {k: v for k, v in by_exercise.items() if len(v) >= 5}
    means = {k: st.fmean(v) for k, v in scored.items()}
    say(f"  exercises with >=5 scored sets : {len(scored)}")
    say(f"  mean of per-exercise biases    : {st.fmean(means.values()):+.4f}")
    say(f"  spread (sd) across exercises   : {st.pstdev(list(means.values())):.4f}")
    say(f"  share biased in the same direction: "
        f"{sum(1 for v in means.values() if v > 0)}/{len(means)} positive")
    say("\n  most biased:")
    for eid, mean in sorted(means.items(), key=lambda kv: -abs(kv[1]))[:6]:
        say(f"    {eid:34s} {mean:+.4f}   n={len(scored[eid])}")
    say("  least biased:")
    for eid, mean in sorted(means.items(), key=lambda kv: abs(kv[1]))[:4]:
        say(f"    {eid:34s} {mean:+.4f}   n={len(scored[eid])}")

    # === 2. how much does suppression move the prediction? =================
    head("2. HOW MUCH WORK IS SUPPRESSION DOING?")
    say("The engine predicts capacity x (1 - suppression). 'Last observation'")
    say("predicts the previous result and applies no suppression at all. If the")
    say("athlete's session-to-session variation is smaller than the suppression")
    say("the engine applies, then suppression is adding error, not removing it.\n")
    suppressions = [
        rec.suppression for r in results for rec in r.projections.values()
    ]
    say(f"  suppression at projection time (n={len(suppressions)})")
    q = sorted(suppressions)
    say(f"    median {st.median(q):.2%}   p90 {q[9 * len(q) // 10]:.2%}   "
        f"max {max(q):.2%}")

    consecutive: list[float] = []
    seen: dict[str, float] = {}
    for _, o in observations:
        if o.exercise_id in seen and seen[o.exercise_id] > 0:
            consecutive.append(math.log(o.observed / seen[o.exercise_id]))
        seen[o.exercise_id] = o.observed
    if consecutive:
        say(f"\n  session-to-session change in observed performance (n={len(consecutive)})")
        say(f"    mean {st.fmean(consecutive):+.4f}   "
            f"mean |change| {st.fmean(abs(v) for v in consecutive):.4f}   "
            f"sd {st.pstdev(consecutive):.4f}")
        say(f"\n  mean suppression applied     {st.fmean(suppressions):.4f}")
        say(f"  mean absolute real movement  {st.fmean(abs(v) for v in consecutive):.4f}")

    # === 3. is capacity lagging, and is the clip why? ======================
    head("3. IS CAPACITY LAGGING, AND IS THE HUBER CLIP WHY?")
    say("The clip is k times each exercise-context's robust session scale. If an")
    say("innovation exceeds it on most updates, capacity is rate-limited and")
    say("cannot track a moving target however wrong it is.\n")

    bound = free = 0
    innovations: list[float] = []
    clips: list[float] = []
    probe = RhomeEngine(library)
    for day in inputs.days:
        result = probe.process_day(day)
        for o in result.observations:
            before = o.capacity_before
            if before and before > 0 and o.observed > 0:
                base_id = o.base_exercise_id or o.exercise_id.split("::", 1)[0]
                context = (
                    o.exercise_id.split("::", 1)[1]
                    if "::" in o.exercise_id else None
                )
                clip = probe.capacity.huber_clip(library[base_id], context)
                innovation = math.log(o.observed) - math.log(before)
                innovations.append(innovation)
                clips.append(clip)
                if abs(innovation) > clip:
                    bound += 1
                else:
                    free += 1
    if innovations:
        say(f"  updates where the clip binds : {bound}/{bound + free} "
            f"({bound / (bound + free):.1%})")
        say(f"  median |innovation|          : {st.median([abs(v) for v in innovations]):.4f}"
            f"   (median clip {st.median(clips):.4f})")
        say(f"  mean innovation              : {st.fmean(innovations):+.4f}")

    # === 4. within a session, does the correction hold? ====================
    head("4. WITHIN A SESSION, DOES THE FATIGUE CORRECTION HOLD?")
    say("Capacity learns from every eligible set, each corrected by dividing out")
    say("the fatigue acting at that moment. If the correction is right, the first")
    say("and last set of a session should imply the same capacity. If the last")
    say("still implies less, later sets drag capacity below what the scored set")
    say("(always the first) supports, and the next projection comes in low.\n")

    raw_drop: list[float] = []
    corrected_drop: list[float] = []
    state_engine = RhomeEngine(library)
    for day in inputs.days:
        result = state_engine.process_day(day)
        by_ex: dict[str, list] = defaultdict(list)
        for logged, dose in result.doses:
            if dose.eligible_for_performance and dose.relative_intensity:
                by_ex[logged.exercise_id].append((logged, dose))
        for eid, items in by_ex.items():
            if len(items) < 2:
                continue
            exercise = library[eid]
            first_obs = items[0][0].load_kg / items[0][1].relative_intensity
            last_obs = items[-1][0].load_kg / items[-1][1].relative_intensity
            if first_obs <= 0 or last_obs <= 0:
                continue
            raw_drop.append(math.log(last_obs / first_obs))
            # The suppression the engine believes is acting at the close of the
            # session, applied to the last set. An upper bound on the within-
            # session correction available to it.
            supp, _ = expected_suppression(exercise, result.state)
            corrected_drop.append(math.log((last_obs / max(1e-9, 1 - supp)) / first_obs))
    if raw_drop:
        say(f"  sessions with >=2 scored sets : {len(raw_drop)}")
        say(f"  last vs first, raw            : {st.median(raw_drop):+.4f} median "
            f"({math.exp(st.median(raw_drop)) - 1:+.2%})")
        say(f"  last vs first, fatigue-corrected: {st.median(corrected_drop):+.4f} median "
            f"({math.exp(st.median(corrected_drop)) - 1:+.2%})")
        say(f"\n  If the corrected figure is still materially negative, the engine's")
        say(f"  suppression does not account for what happens inside a session.")

    # === 5. what is the athlete actually logging? ==========================
    head("5. WHAT IS THE ATHLETE ACTUALLY LOGGING?")
    say("The Nuzzo inversion turns effort into relative intensity. If the logged")
    say("effort is not what the curve assumes, every capacity estimate inherits")
    say("the error, and no amount of pooling or clipping fixes it.\n")
    rpes = [s.rpe for d in inputs.days for s in d.sets if s.rpe is not None]
    reps = [s.reps for d in inputs.days for s in d.sets]
    say(f"  RPE recorded on {len(rpes)} of {sum(len(d.sets) for d in inputs.days)} sets")
    say(f"  RPE distribution : {dict(sorted(Counter(rpes).items()))}")
    say(f"  reps distribution: {dict(sorted(Counter(reps).items())[:14])}")
    intensities = []
    for day in inputs.days:
        for s in day.sets:
            rir = s.repetitions_in_reserve()
            if rir is not None:
                try:
                    value, _ = relative_intensity(
                        s.reps, rir, library[s.exercise_id].nuzzo_curve.value
                    )
                    intensities.append(value)
                except Exception:  # noqa: BLE001
                    pass
    if intensities:
        say(f"\n  implied relative intensity (n={len(intensities)})")
        iq = sorted(intensities)
        say(f"    median {st.median(iq):.3f}   p10 {iq[len(iq)//10]:.3f}   "
            f"p90 {iq[9*len(iq)//10]:.3f}")

    # === 6. how sparse is the evidence, really? ============================
    head("6. HOW SPARSE IS THE EVIDENCE?")
    per_ex = Counter(o.exercise_id for _, o in observations)
    say(f"  scored sets per exercise: median {st.median(per_ex.values()):.0f}, "
        f"max {max(per_ex.values())}")
    say(f"  exercises reaching 20 scored sets: "
        f"{sum(1 for v in per_ex.values() if v >= 20)}/{len(per_ex)}")
    gaps = []
    last_day: dict[str, int] = {}
    for r, o in observations:
        if o.exercise_id in last_day:
            gaps.append(r.day_index - last_day[o.exercise_id])
        last_day[o.exercise_id] = r.day_index
    if gaps:
        say(f"  days between sessions of the same exercise: median {st.median(gaps):.0f}, "
            f"mean {st.fmean(gaps):.1f}")
        half_life = ENGINE_PARAMETERS.value("local_half_life_h") / 24.0
        say(f"  local fatigue half-life is {half_life:.1f} days, so by the next")
        say(f"  session of an exercise the fatigue it caused has decayed to about "
            f"{0.5 ** (st.median(gaps) / half_life):.1%}")

    say()
    say("=" * 78)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written to {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
