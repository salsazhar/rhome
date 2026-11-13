"""Validate an exercise library CSV.

For authoring a library independently of the build. Checks the same schema the
engine enforces, reports muscle coverage, and measures how well the derivation
reproduces the hand-assigned coefficients.

    python3 tools/validate_library.py path/to/library.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhome_core.derivation import derive_compoundness, derive_systemic_cost  # noqa: E402
from rhome_core.exercises import load_library  # noqa: E402
from rhome_core.muscles import REGION_OF, Muscle, Region  # noqa: E402

BANDS_KAPPA = {"isolation": (0.15, 0.30), "machine compound": (0.45, 0.65),
               "upper free-weight compound": (0.65, 0.85), "lower free-weight compound": (0.80, 1.00)}


def main(path: Path) -> int:
    try:
        library = load_library(path)
    except (ValueError, FileNotFoundError, KeyError) as error:
        print(f"✗ SCHEMA ERROR\n  {error}")
        return 1

    print(f"✓ schema valid — {len(library)} exercises\n")

    problems: list[str] = []

    covered = library.covered_muscles()
    missing = set(Muscle) - covered
    primary: set[Muscle] = set()
    for exercise in library:
        primary |= set(exercise.primary_muscles)
    never_primary = set(Muscle) - primary

    print("MUSCLE COVERAGE")
    print(f"  loaded at any tier : {len(covered)}/16")
    print(f"  primary somewhere  : {len(primary)}/16")
    if missing:
        problems.append(f"never loaded: {sorted(m.value for m in missing)}")
        print(f"  ✗ never loaded     : {sorted(m.value for m in missing)}")
    if never_primary:
        problems.append(f"never primary: {sorted(m.value for m in never_primary)}")
        print(f"  ✗ never primary    : {sorted(m.value for m in never_primary)}")
        print("    (a group only ever loaded indirectly cannot be trained on purpose)")

    counts = {r: len(library.by_region(r)) for r in Region}
    print("\nREGION BALANCE")
    for region, count in counts.items():
        print(f"  {region.value:6s} {count:3d}")
    if counts[Region.LOWER]:
        ratio = counts[Region.UPPER] / counts[Region.LOWER]
        if not 0.6 <= ratio <= 1.7:
            problems.append(f"upper/lower ratio {ratio:.2f} makes DATA.md §3.2 parity hard")
            print(f"  ✗ ratio {ratio:.2f} — parity within ±10% may be unachievable")

    within, outliers = 0, []
    for exercise in library:
        dk = derive_compoundness(
            exercise.equipment, exercise.movement_pattern, len(exercise.primary_muscles)
        )
        db = derive_systemic_cost(
            exercise.stimulus_contributions, exercise.equipment, exercise.movement_pattern
        )
        ek, eb = abs(dk - exercise.compoundness), abs(db - exercise.systemic_cost)
        if ek <= 0.15 and eb <= 0.15:
            within += 1
        else:
            outliers.append((exercise.exercise_id, exercise.compoundness, dk, exercise.systemic_cost, db))

    print(f"\nDERIVATION AGREEMENT  {within}/{len(library)} = {within/len(library):.0%} within ±0.15")
    if outliers:
        print("  exercises the derivation does not reproduce:")
        for eid, k, dk, b, db in outliers:
            print(f"    {eid:28s} κ {k:.2f}→{dk:.2f}   b {b:.2f}→{db:.2f}")
        print("  (not necessarily wrong — the curated value wins. Worth a look if unexpected.)")

    print()
    if problems:
        print("✗ " + f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"    {problem}")
        return 1
    print("✓ all checks passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
