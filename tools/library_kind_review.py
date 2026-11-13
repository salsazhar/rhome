"""Propose kinds and bodyweight fractions for the athlete-authored library (L3.9).

Fifty-seven exercises in `exercise_library_v1.csv` are `reps_only` and carry no
`bodyweight_fraction`, so the library will not load: `DATA.md` §5.4.1 defines
`reps_only` as "body mass via `bodyweight_fraction`", and an exercise claiming
that kind while withholding the fraction is claiming a load it has not stated.

Three groups, and only one of them is a judgement.

**Bands (32).** Reps are recorded and no body mass is moved. The fraction is
0.0 — stated rather than omitted, per D17: a zero encoded by leaving a field
blank is unfalsifiable, because nothing can ever disagree with it. Stated, it is
a claim that a band row contributes dose and no performance observation, which
is exactly right: the band's tension is nowhere in the log.

**Isometric holds (14).** §5.4.1 names "Plank" as the worked example of
`time_only` — "Recorded, excluded ... no repetitions, so no reps-to-failure and
no relative intensity". A dead hang and a Copenhagen plank are the same case.
Reclassifying them applies the specification rather than overriding the author,
and it is a *kind* correction, not a coefficient one. They leave the dose model,
which is the documented v0 boundary.

**Repetition work against partial body mass (11).** These genuinely need a
fraction and it is a lever-arm judgement the tool should not make silently. The
proposal follows the two precedents already in the v0 library —
`hanging_leg_raise` at 0.55 and `ab_wheel_rollout` at 0.60 — and every row is
printed for review rather than applied.

    python3 tools/library_kind_review.py            # report
    python3 tools/library_kind_review.py --write    # write v1.1
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SOURCE = ROOT / "data" / "exercises" / "exercise_library_v1.csv"
TARGET = ROOT / "data" / "exercises" / "exercise_library_v1_1.csv"

#: Reps are recorded; no body mass is moved. Fraction stated as 0.0, not left
#: blank (D17). Dose yes, performance observation no.
BANDS = 0.0

#: §5.4.1's own example of `time_only`: no repetitions, so no reps-to-failure
#: and therefore no relative intensity. Leaves the dose model in v0.
ISOMETRIC: tuple[str, ...] = (
    "dead_hang", "towel_dead_hang", "fat_grip_dead_hang",
    "front_plank", "long_lever_plank", "rkc_plank",
    "side_plank", "star_side_plank", "copenhagen_side_plank",
    "copenhagen_plank", "short_lever_copenhagen_plank", "long_lever_copenhagen_plank",
    "bear_plank", "wall_sit",
)

#: Repetition work moving part of the athlete's body mass. Each value is a
#: lever-arm judgement, anchored on the two precedents already in the v0
#: library, and each is flagged for the athlete rather than applied silently.
PROPOSED_FRACTION: dict[str, tuple[float, str]] = {
    "ring_fly": (0.55, "torso supported on rings; lean angle sets the load, mid-range assumed"),
    "suspension_trainer_fly": (0.55, "as ring_fly"),
    "suspension_trainer_leg_curl": (0.45, "hips and legs raised, shoulders grounded"),
    "trx_body_saw": (0.50, "forearm-supported plank translated; roughly half the body"),
    "dragon_flag": (0.85, "near the whole body pivoting at the shoulders"),
    "negative_dragon_flag": (0.85, "same lever, eccentric only"),
    "hanging_windshield_wiper": (0.55, "matches hanging_leg_raise, the v0 precedent"),
    "dead_bug": (0.25, "contralateral limbs only, torso grounded"),
    "bird_dog": (0.25, "as dead_bug"),
    "bear_plank_serratus_press": (0.45, "quadruped press, most mass on the hands"),
    "bear_crawl": (0.50, "locomotion; arguably distance_time, flagged"),
}


def classify(row: dict) -> tuple[str, str, float | None, str]:
    """Return (group, kind, fraction, reason) for one row."""
    exercise_id = row["exercise_id"]
    if exercise_id in ISOMETRIC:
        return ("isometric", "time_only", None,
                "§5.4.1: no repetitions, so no reps-to-failure and no relative intensity")
    if exercise_id in PROPOSED_FRACTION:
        fraction, reason = PROPOSED_FRACTION[exercise_id]
        return ("partial body mass", "reps_only", fraction, reason)
    if "band" in exercise_id or "banded" in exercise_id:
        return ("band", "reps_only", BANDS,
                "elastic resistance; no body mass moved, so the fraction is zero")
    return ("UNCLASSIFIED", row["exercise_kind"], None, "no rule matched")


def main(write: bool) -> int:
    rows = list(csv.DictReader(SOURCE.open(encoding="utf-8")))
    fieldnames = list(rows[0])
    needing = [
        r for r in rows
        if r["exercise_kind"] == "reps_only" and not r["bodyweight_fraction"].strip()
    ]

    groups: dict[str, list] = {}
    for row in needing:
        group, kind, fraction, reason = classify(row)
        groups.setdefault(group, []).append((row["exercise_id"], kind, fraction, reason))

    print(f"\n{len(needing)} of {len(rows)} exercises are reps_only with no bodyweight_fraction\n")
    for group in ("band", "isometric", "partial body mass", "UNCLASSIFIED"):
        entries = groups.get(group, [])
        if not entries:
            continue
        flag = "  <-- NEEDS THE ATHLETE'S REVIEW" if group == "partial body mass" else ""
        print(f"--- {group}: {len(entries)}{flag}")
        for exercise_id, kind, fraction, reason in entries:
            shown = "—" if fraction is None else f"{fraction:.2f}"
            print(f"    {exercise_id:40s} {kind:12s} {shown:>5s}  {reason}")
        print()

    unclassified = groups.get("UNCLASSIFIED", [])
    if unclassified:
        print(f"FAIL: {len(unclassified)} exercises matched no rule")
        return 1

    if not write:
        print("Report only. Pass --write to produce exercise_library_v1_1.csv")
        return 0

    changed = 0
    for row in rows:
        if row["exercise_kind"] != "reps_only" or row["bodyweight_fraction"].strip():
            continue
        _, kind, fraction, _ = classify(row)
        row["exercise_kind"] = kind
        row["bodyweight_fraction"] = "" if fraction is None else f"{fraction:.2f}"
        changed += 1

    with TARGET.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {TARGET.relative_to(ROOT)} — {changed} rows amended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--write" in sys.argv))
