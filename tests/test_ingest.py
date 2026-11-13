"""Reading observable data (``DATA.md`` §5, §17)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rhome_core.exercises import load_library
from rhome_engine.ingest import _MAX_RIR, _MIN_RPE, load_sets, parse_sets
from rhome_sim.missingness import raw_dirty_rows

LIBRARY = load_library()
DATASET = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "athlete_a"

BASE = {
    "workout_id": "w_0001", "exercise_id": "bench_press", "set_number": 1,
    "set_type": "working", "external_load_kg": 100.0, "reps": 5,
    "rpe": 8.0, "rir": None, "is_pr": False,
}


def _parse(**overrides):
    return parse_sets([{**BASE, **overrides}], LIBRARY)


# --- the clean dataset -----------------------------------------------------

@pytest.mark.skipif(not (DATASET / "observable" / "sets.csv").exists(),
                    reason="dataset not generated")
def test_the_generated_dataset_parses_without_a_single_complaint():
    """A parser that rejects the clean dataset has a bound of its own invention.

    An earlier version used an RPE floor of 4 and threw away 29 legitimate
    sets, because ``MODEL.tex`` clips logged reserve to [0, 8] and the
    corresponding RPE range therefore reaches down to 2.
    """
    result = load_sets(DATASET / "observable" / "sets.csv", LIBRARY)
    assert result.sets
    assert result.rejected == [], f"rejected {len(result.rejected)} clean rows"
    assert result.repaired == [], f"repaired {len(result.repaired)} clean rows"


def test_the_effort_bounds_are_derived_from_the_documented_reserve_range():
    assert _MIN_RPE == pytest.approx(10.0 - _MAX_RIR)
    assert _MAX_RIR == 8.0


# --- the malformed fixture (DATA.md §17) -----------------------------------

@pytest.mark.spec("DATA:parser-rejects-and-repairs")
def test_every_fixture_row_is_handled_as_the_fixture_specifies():
    rows = raw_dirty_rows()
    result = parse_sets([r.fields for r in rows], LIBRARY)

    outcomes: dict[int, set[str]] = {}
    for issue in result.issues:
        outcomes.setdefault(issue.row_number, set()).add(issue.outcome)

    failures = []
    for number, row in enumerate(rows, start=2):
        got = outcomes.get(number, set())
        if row.expected == "reject" and "rejected" not in got:
            failures.append(f"{row.defect}: expected rejection, got {got or 'acceptance'}")
        if row.expected == "repair":
            if "rejected" in got:
                failures.append(f"{row.defect}: rejected, but is repairable")
            elif "repaired" not in got:
                failures.append(f"{row.defect}: accepted unchanged, needed repair")
    assert not failures, "\n".join(failures)


@pytest.mark.spec("DATA:parser-rejects-and-repairs")
def test_every_rejection_states_a_reason():
    result = parse_sets([r.fields for r in raw_dirty_rows()], LIBRARY)
    for issue in result.issues:
        assert issue.reason and len(issue.reason) > 8
        assert issue.outcome in ("rejected", "repaired")


def test_a_repaired_row_still_reaches_the_output():
    """Repair means corrected and kept, not quietly discarded."""
    result = _parse(reps="5.0")
    assert result.repaired
    assert len(result.sets) == 1
    assert result.sets[0].reps == 5


def test_a_rejected_row_does_not_reach_the_output():
    result = _parse(external_load_kg=-20.0)
    assert result.rejected
    assert result.sets == []


# --- individual defects ----------------------------------------------------

@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"external_load_kg": -20.0}, "negative load"),
        ({"external_load_kg": 900.0}, "beyond any human capacity"),
        ({"external_load_kg": "heavy"}, "not numeric"),
        ({"reps": 0}, "at least one repetition"),
        ({"reps": -3}, "at least one repetition"),
        ({"reps": 300}, "beyond any plausible set"),
        ({"reps": 5.5}, "fractional repetitions"),
        ({"rpe": 12.0}, "outside the working range"),
        ({"rpe": 1.0}, "outside the working range"),
        ({"rpe": None, "rir": -1.0}, "outside the plausible range"),
        ({"exercise_id": "nonexistent_lift"}, "unknown exercise"),
        ({"set_type": "superset"}, "unknown set type"),
        ({"workout_id": ""}, "missing workout identifier"),
    ],
)
def test_unrecoverable_defects_are_rejected_by_name(overrides, fragment):
    result = _parse(**overrides)
    assert result.sets == []
    assert any(fragment in i.reason for i in result.rejected), (
        f"expected a rejection mentioning {fragment!r}, got "
        f"{[i.reason for i in result.issues]}"
    )


def test_contradicting_effort_fields_resolve_to_the_primary_one():
    """``DATA.md`` §5.3 makes RIR primary, so it wins over a disagreeing RPE."""
    result = _parse(rpe=8.0, rir=4.0)
    assert len(result.sets) == 1
    assert result.sets[0].repetitions_in_reserve() == 4.0
    assert any("authoritative" in i.reason for i in result.repaired)


def test_agreeing_effort_fields_are_not_treated_as_a_defect():
    result = _parse(rpe=8.0, rir=2.0)
    assert result.sets and not result.issues


def test_categorical_fields_are_normalised():
    result = _parse(set_type="  Working ")
    assert result.sets[0].set_type == "working"
    assert any("normalised" in i.reason for i in result.repaired)


def test_duplicate_set_numbers_are_reassigned():
    rows = [dict(BASE, set_number=1), dict(BASE, set_number=1)]
    result = parse_sets(rows, LIBRARY)
    assert [s.set_number for s in result.sets] == [1, 2]
    assert any("set number" in i.reason for i in result.repaired)


def test_assisted_exercises_may_carry_negative_load():
    """Negative external load is assistance, and is legitimate for that kind."""
    result = _parse(exercise_id="bench_press", external_load_kg=-20.0)
    assert result.sets == []  # bench press is not assisted


def test_a_set_may_be_logged_without_any_effort_rating():
    """§17 requires some sets to carry none; the parser must accept them."""
    result = _parse(rpe=None, rir=None)
    assert len(result.sets) == 1
    assert result.sets[0].repetitions_in_reserve() is None
    assert not result.rejected


# --- boundary conditions ---------------------------------------------------

@pytest.mark.parametrize("rpe", [2.0, 10.0])
def test_the_documented_rpe_extremes_are_accepted(rpe):
    assert _parse(rpe=rpe).sets


@pytest.mark.parametrize("rir", [0.0, 8.0])
def test_the_documented_reserve_extremes_are_accepted(rir):
    assert _parse(rpe=None, rir=rir).sets


def test_an_empty_input_produces_an_empty_result():
    result = parse_sets([], LIBRARY)
    assert result.sets == [] and result.issues == []
