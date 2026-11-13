"""Dry pass over the athlete's own history (L3.12, first half).

**This opens the seal.** It reads every load, repetition and date in the
archive, and no honest framing makes that free. What it does not do is *score*
anything: it prints how the data parsed and whether the engine completed, and
nothing about what the engine concluded.

That distinction is the entire point. `BUILD_PLAN.md` L3.12 says the resource is
consumed by *"any model change made after looking at them"* — not by looking.
Fixing a date parser after seeing that 300 rows failed to parse conditions
nothing about the model. Fixing a coefficient after seeing a residual is the act
that spends the holdout, and this tool is built so that it cannot happen here:
no metric is computed, so none can be reacted to.

If this pass finds a parsing defect, the fix is made and the pass re-run. Those
are recorded as ``dry`` openings and they cost nothing but honesty about the
count. The scoring pass happens once, afterwards, when the plumbing is known to
work.

    python3 tools/real_dry_pass.py
"""
from __future__ import annotations

import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rhome_core.exercises import library_path, load_library  # noqa: E402
from rhome_engine.session import RhomeEngine  # noqa: E402
from rhome_eval.cold_run import assemble  # noqa: E402

REASON = (
    "L3.12 dry pass: verify the adapter survives contact with the real archive "
    "before the scoring run. Structure only — no metric is computed."
)


def main() -> int:
    inputs = assemble(REASON, kind="dry")
    report = inputs.report

    print("\n" + "=" * 78)
    print("DRY PASS — the athlete's own history, read but not scored")
    print("=" * 78)
    print(f"\nprovenance : {inputs.provenance}")
    print(f"seal       : {inputs.seal.note()}")

    print("\n--- ingestion")
    print(f"  calendar span      {report.first_day} to {report.last_day}")
    print(f"  days               {report.days}")
    print(f"  sessions           {report.sessions}")
    print(f"  sets read          {report.sets_read}")
    print(f"  sets kept          {report.sets_kept}")
    if report.skipped:
        for reason, count in sorted(report.skipped.items()):
            print(f"    skipped: {reason:34s} {count}")
    if report.derived_exercises:
        print(f"  names sent to derivation: {sorted(report.derived_exercises)}")

    print("\n--- wearable")
    print(f"  Oura nights        {report.oura_nights}")
    print(f"  days without one   {report.days_without_wearable}")
    print(f"  days without mass  {report.days_without_body_mass}")

    print("\n--- shape of the log")
    types = Counter(s.set_type for d in inputs.days for s in d.sets)
    effort = Counter(
        "rpe" if s.rpe is not None else "rir" if s.rir is not None else "unrated"
        for d in inputs.days for s in d.sets
    )
    per_session = [len(d.sets) for d in inputs.days if d.sets]
    print(f"  set types          {dict(types)}")
    print(f"  effort recorded    {dict(effort)}")
    if per_session:
        print(f"  sets per session   min {min(per_session)}, "
              f"median {sorted(per_session)[len(per_session) // 2]}, "
              f"max {max(per_session)}")
    exercises = {s.exercise_id for d in inputs.days for s in d.sets}
    print(f"  distinct exercises {len(exercises)}")

    print("\n--- engine")
    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    engine = RhomeEngine(library)
    try:
        results = engine.run(inputs.days)
    except Exception:  # noqa: BLE001 - the whole point is to surface anything
        print("  FAILED — the engine did not complete:\n")
        traceback.print_exc()
        print("\nFix the defect and re-run. This was a dry opening; no metric "
              "was computed, so nothing about the model has been conditioned "
              "on these data.")
        return 1

    observations = sum(len(r.observations) for r in results)
    projections = sum(len(r.projections) for r in results)
    traces = sum(len(r.traces) for r in results)
    print(f"  completed          {len(results)} days")
    print(f"  frozen projections {projections}")
    print(f"  scored sets        {observations}")
    print(f"  traces built       {traces}")

    print("\n" + "-" * 78)
    ok = observations > 0 and len(results) == len(inputs.days)
    print("READY FOR THE SCORING PASS" if ok else "NOT READY — see above")
    print("No residual, capacity or score was computed. Nothing here says how "
          "well the engine did.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
