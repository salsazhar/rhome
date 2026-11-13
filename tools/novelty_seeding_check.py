"""Does the engine mistake an experienced lifter's first logged set for their first-ever set? (L3.15 addendum)

Raised by the athlete: the 614-day calendar the engine processes spans from
Oura's first night (17 Dec 2024) to the last training day (22 Aug 2026), but
training was not logged until day 316 (29 Oct 2025) — the athlete trained for
years before that, only the *log* is new.

The long quiet gap costs nothing: fatigue decays to zero within about two weeks
at a 30 h half-life and stays there regardless of what caused the silence.

**But novelty does not decay away** — it is keyed to the engine's own memory of
an exercise, which begins at day 0 of the calendar it is given. Every
exercise's first appearance in the log is therefore scored as a true first
exposure and inflates local fatigue by up to 25%, decaying over ~4 sets
(``novelty_cap = 1.25``, ``novelty_decay_exposures = 4.0``). For an experienced
lifter whose *log* started mid-career, that inflation is fictitious on every
exercise's opening sets.

This measures how much of the real log that touches, by capturing every
``novelty_for`` call the engine actually made, in the order it made them.

**D22 applies.** Development analysis; validates nothing.
"""
from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rhome_core.exercises import library_path, load_library  # noqa: E402
from rhome_engine.session import RhomeEngine  # noqa: E402
from rhome_engine.state import StateEngine  # noqa: E402
from rhome_eval.cold_run import assemble  # noqa: E402


def main() -> int:
    captured: list[tuple[str, int, float]] = []
    original = StateEngine.novelty_for

    def patched(self, exercise_id):  # noqa: ANN001
        value = original(self, exercise_id)
        captured.append((exercise_id, self.exposure_count(exercise_id), value))
        return value

    StateEngine.novelty_for = patched
    try:
        inputs = assemble(
            "L3.15 addendum: does the pre-log training history create a "
            "fictitious novelty inflation? Development analysis (D22).",
            kind="dry",
        )
        library = load_library(library_path().parent / "exercise_library_v1_2.csv")
        RhomeEngine(library).run(inputs.days)
    finally:
        StateEngine.novelty_for = original

    values = [v for _, _, v in captured]
    n = len(values)
    print(f"{inputs.provenance}\n")
    print(f"working sets with a novelty lookup:        {n}")
    print(f"materially inflated (novelty > 1.02):       {sum(1 for v in values if v > 1.02)} "
          f"({sum(1 for v in values if v > 1.02) / n:.1%})")
    print(f"inflated more than 10% (novelty > 1.10):    {sum(1 for v in values if v > 1.10)} "
          f"({sum(1 for v in values if v > 1.10) / n:.1%})")
    print(f"scored as a true first exposure (>1.245):   {sum(1 for v in values if v > 1.245)}")
    print(f"\nmean novelty, all sets:                    {st.fmean(values):.4f}")
    print(f"mean novelty, first 200 chronological sets: {st.fmean(values[:200]):.4f}")
    print(f"mean novelty, last 200 chronological sets:  {st.fmean(values[-200:]):.4f}")

    first_exposures = {eid for eid, exp, _ in captured if exp == 0}
    print(f"\ndistinct exercises given a fictitious first exposure: {len(first_exposures)}")

    excess = sum(v - 1.0 for v in values)
    print(f"sum of (novelty − 1) across all sets: {excess:.2f}")
    print("  — equivalent local-fatigue dose to roughly "
          f"{excess:.0f} extra full-novelty sets, injected by log timing alone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
