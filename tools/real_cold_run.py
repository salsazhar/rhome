"""The real-data cold run (L3.12).

One athlete, one export, one run. Everything the project has built since L0.1
exists to make this measurement worth making, and the discipline around it is
the reason it means anything: the export was frozen before the engine was
finished, nothing read it but two bounded extractions, the exercise mapping was
reviewed and frozen before any result existed, and the result is recorded
whatever it is.

**What this dataset can answer** (`BUILD_PLAN.md` L3.12):

* one-step-ahead performance residuals and their bias — `DATA.md` §19.2 calls
  this the severe criterion, and it is the strongest test available here;
* whether confidence falls where evidence is thin;
* robustness to missing wearable nights and missed sessions.

**What it cannot.** Nobody knows this athlete's true hamstring fatigue, so there
is no latent state to score against and none is reported. Sixteen muscle-specific
half-lives from ninety-nine confounded sessions would be noise wearing a
decimal point, so none is estimated.

**Every figure carries its trivial competitor** (D20). Twice in this project a
headline number has meant something other than it appeared to, both times for
want of a baseline. On real data that risk is higher, not lower, because there
is no simulator to contradict a plausible story.

    python3 tools/real_cold_run.py --reason "..."
"""
from __future__ import annotations

import argparse
import math
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rhome_core.exercises import library_path, load_library  # noqa: E402
from rhome_engine.confidence import Band  # noqa: E402
from rhome_engine.session import RhomeEngine  # noqa: E402
from rhome_eval import metrics as m  # noqa: E402
from rhome_eval.baselines import Prediction, ablation_ladder  # noqa: E402
from rhome_eval.cold_run import assemble  # noqa: E402

RESULT = ROOT / "build_log" / "real_cold_run_result.txt"

#: Prior observations beyond which the engine is treated as settled, matching
#: the synthetic evaluation so the two are comparable.
SETTLED_AFTER = 20


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reason", required=True)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    inputs = assemble(args.reason, kind="dry" if args.dry else "scoring")
    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    results = RhomeEngine(library).run(inputs.days)

    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text)

    say("=" * 78)
    say("REAL-DATA COLD RUN — the athlete's own history")
    say("=" * 78)
    say()
    say(f"provenance : {inputs.provenance}")
    say(f"seal       : {inputs.seal.note()}")
    say(f"reason     : {args.reason}")
    say()
    say(f"span       : {inputs.report.first_day} to {inputs.report.last_day} "
        f"({inputs.report.days} days, {inputs.report.sessions} sessions)")
    say(f"ingestion  : {inputs.report.summary()}")

    # --- the severe criterion -------------------------------------------------
    residuals: list[float] = []
    days: list[int] = []
    experience: list[int] = []
    predictions: list[Prediction] = []
    seen: dict[str, int] = defaultdict(int)
    for result in results:
        for observation in result.observations:
            residuals.append(observation.log_residual)
            days.append(result.day_index)
            experience.append(seen[observation.exercise_id])
            predictions.append(
                Prediction(
                    exercise_id=observation.exercise_id,
                    day=result.day_index,
                    observed=observation.observed,
                    projected=observation.projected,
                    prior_observations=seen[observation.exercise_id],
                )
            )
            seen[observation.exercise_id] += 1

    say()
    say("-" * 78)
    say("ONE-STEP-AHEAD RESIDUALS  (DATA.md §19.2, the severe criterion)")
    say("-" * 78)
    if len(residuals) < 8:
        say(f"  n={len(residuals)} — too few scored sets to report anything.")
    else:
        say(f"  n = {len(residuals)} scored sets across "
            f"{len({p.exercise_id for p in predictions})} exercises")
        say(f"  MAE   {m.mae(residuals):.4f}")
        say(f"  RMSE  {math.sqrt(st.fmean([v * v for v in residuals])):.4f}")
        say(f"  bias  {m.bias(residuals):+.4f}")
        auto = m.autocorrelation(residuals)
        say(f"  lag-1 autocorrelation  {auto:+.4f}" if auto is not None else
            "  lag-1 autocorrelation  n/a")

    # --- D20: the trivial competitor -----------------------------------------
    say()
    say("-" * 78)
    say("ABLATION LADDER  (D20 — no score without its trivial competitor)")
    say("-" * 78)
    for label, minimum in (("all scored sets", 0), (f"{SETTLED_AFTER}+ prior", SETTLED_AFTER)):
        ladder = ablation_ladder(predictions, minimum_prior=minimum)
        if not ladder:
            say(f"\n  {label}: no set had enough history for every predictor.")
            continue
        say(f"\n  {label}  (n={ladder[0].n})")
        for rung in ladder:
            tail = ("" if rung.versus_engine is None
                    else f"  delta {rung.versus_engine:+.5f}+/-{rung.interval:.5f}")
            say(f"    {rung.name:22s} MAE {rung.mae:.4f}  "
                f"RMSE {rung.rmse:.4f}  bias {rung.bias:+.4f}  "
                f"{rung.verdict}{tail}")

    # --- bias, sliced before it is pooled ------------------------------------
    say()
    say("-" * 78)
    say("BIAS, SLICED  (a pooled zero can be two opposite biases meeting)")
    say("-" * 78)
    drift = m.drift_by_block(residuals, days, block_days=120)
    if drift:
        for start, count, mean in drift:
            say(f"  days {start:4d}-{start + 119:4d}   n={count:4d}   {mean:+.4f}")
    else:
        say("  too few sets per block to slice by time.")
    by_experience: dict[int, list[float]] = defaultdict(list)
    for residual, count in zip(residuals, experience):
        by_experience[min(count // 10, 4) * 10].append(residual)
    say()
    for start, values in sorted(by_experience.items()):
        if len(values) >= 8:
            say(f"  observations {start:2d}+   n={len(values):4d}   {st.fmean(values):+.4f}")

    # --- confidence ----------------------------------------------------------
    say()
    say("-" * 78)
    say("CONFIDENCE  (DATA.md §19.5 — does it fall where evidence is thin?)")
    say("-" * 78)
    bands = Counter(r.confidence.fatigue.band.value for r in results if r.confidence)
    say(f"  fatigue confidence bands   {dict(bands)}")
    binding = Counter(
        r.confidence.fatigue.binding_reason.name for r in results if r.confidence
    )
    say(f"  binding reason             {dict(binding.most_common(4))}")

    blank = [r for r in results if r.recovery.channels_present == 0 and r.confidence]
    full = [r for r in results if r.recovery.channels_present == 5 and r.confidence]
    if blank and full:
        gap = (st.fmean(r.confidence.fatigue.value for r in full)
               - st.fmean(r.confidence.fatigue.value for r in blank))
        say(f"  complete nights {st.fmean(r.confidence.fatigue.value for r in full):.4f} "
            f"vs blank {st.fmean(r.confidence.fatigue.value for r in blank):.4f} "
            f"-> {gap:+.4f} on {len(blank)} blank nights")

    early = [b for b in _experience_bands(results) if b[0] <= SETTLED_AFTER]
    high_early = sum(b[2].get(Band.HIGH.value, 0) for b in early)
    total_early = sum(b[1] for b in early)
    if total_early:
        say(f"  capacity readings before {SETTLED_AFTER} sessions of an exercise: "
            f"{high_early} of {total_early} say high")

    # --- what this run cannot say --------------------------------------------
    say()
    say("-" * 78)
    say("NOT REPORTED, DELIBERATELY")
    say("-" * 78)
    say("  Latent-state reconstruction. Nobody knows this athlete's true muscle")
    say("  fatigue, so there is nothing to score against and no correlation is")
    say("  computed. Every latent figure in this project is synthetic-only.")
    say("  Per-muscle half-lives. Sixteen parameters from 99 confounded sessions")
    say("  would be noise with a decimal point.")
    say(f"  The first 42 days of wearable data are consumed warming the rolling")
    say(f"  baselines; {inputs.report.days_without_body_mass} days carry no body")
    say("  mass at all, so bodyweight-exercise capacity rests on recalled anchors.")

    say()
    say("=" * 78)
    if args.dry:
        print("dry run: result not written")
    else:
        RESULT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"written to {RESULT.relative_to(ROOT)}")
    return 0


def _experience_bands(results):
    seen: dict[str, int] = defaultdict(int)
    buckets: dict[int, list] = defaultdict(list)
    for result in results:
        for observation in result.observations:
            seen[observation.exercise_id] += 1
            entry = result.confidence.capacity.get(observation.exercise_id)
            if entry is not None:
                buckets[min((seen[observation.exercise_id] - 1) // 10, 3) * 10].append(entry)
    return [
        (start, len(entries), Counter(e.band.value for e in entries))
        for start, entries in sorted(buckets.items())
    ]


if __name__ == "__main__":
    raise SystemExit(main())
