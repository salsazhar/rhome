"""Missing and malformed data (``DATA.md`` §17)."""

from __future__ import annotations

from collections import Counter, defaultdict

import pytest

from rhome_sim.generate import simulate
from rhome_sim.missingness import (
    MISSABLE_FIELDS,
    SIM_MISSINGNESS,
    MissingnessModel,
    raw_dirty_rows,
)
from rhome_sim.scenarios import Scenario

SEEDS = range(4)


@pytest.fixture(scope="module")
def runs():
    return [simulate(seed) for seed in SEEDS]


# --- rates (DATA.md §17) ---------------------------------------------------

@pytest.mark.spec("DATA:missingness-rates")
def test_wearable_missingness_rates_match_the_specification(runs):
    for run in runs:
        counts = Counter(d.wearable_missingness for d in run.days)
        total = len(run.days)
        partial = 100 * counts["partial"] / total
        full = 100 * counts["full"] / total
        assert 2.5 <= partial <= 5.5, f"partial nights {partial:.1f}%, spec 3-5%"
        assert 0.7 <= full <= 2.5, f"full nights {full:.1f}%, spec 1-2%"


@pytest.mark.spec("DATA:missingness-rates")
def test_a_full_night_loses_every_wearable_field(runs):
    for day in runs[0].days:
        if day.wearable_missingness == "full":
            for field in MISSABLE_FIELDS:
                assert getattr(day.wearable, field) is None
            assert day.wearable.body_mass_kg is None


@pytest.mark.spec("DATA:missingness-rates")
def test_a_partial_night_loses_exactly_one_field(runs):
    seen = set()
    for day in runs[0].days:
        if day.wearable_missingness == "partial":
            missing = [f for f in MISSABLE_FIELDS if getattr(day.wearable, f) is None]
            assert len(missing) == 1, f"day {day.day_index} lost {missing}"
            seen.update(missing)
    assert len(seen) >= 4, "partial losses should not always hit the same metric"


def test_steps_survive_a_night_the_ring_was_not_worn(runs):
    """Steps come from the phone, not the ring."""
    for day in runs[0].days:
        assert day.wearable.steps is not None


@pytest.mark.spec("DATA:missingness-rates")
def test_body_mass_and_effort_are_sometimes_absent(runs):
    run = runs[0]
    mass_missing = sum(1 for d in run.days if d.wearable.body_mass_kg is None)
    assert 0.05 <= mass_missing / len(run.days) <= 0.30

    # Warm-ups deliberately carry no effort rating, so only dose-bearing sets
    # count toward the documented missing-effort rate.
    sets = [s for s in run.sets if s.set_type in ("working", "backoff")]
    no_effort = sum(1 for s in sets if s.logged_rir is None)
    assert 0.005 <= no_effort / len(sets) <= 0.05
    for performed in sets:
        if performed.logged_rir is None:
            assert performed.logged_rpe is None, "effort must be absent, not half-absent"


def test_body_mass_gaps_come_in_blocks_not_scattered_days(runs):
    """Someone who stops weighing themselves stops for a while.

    Scattered single days would be recoverable by interpolation, which is not
    the problem real data poses.
    """
    missing = [d.wearable.body_mass_kg is None for d in runs[0].days]
    runs_of_gaps, current = [], 0
    for absent in missing:
        if absent:
            current += 1
        elif current:
            runs_of_gaps.append(current)
            current = 0
    if current:
        runs_of_gaps.append(current)

    assert runs_of_gaps, "body mass is never missing"
    assert max(runs_of_gaps) >= 3, "no multi-day gap; every absence is isolated"


# --- the property that matters (DATA.md §17) -------------------------------

@pytest.mark.spec("DATA:missingness-not-concentrated")
def test_missingness_is_not_concentrated_in_adverse_scenarios(runs):
    """If gaps clustered on bad days, absence would itself signal the athlete's
    state, and an engine could learn to read a missing night as a warning. That
    signal would be invented by the generator and would not survive real data.
    """
    total = defaultdict(int)
    missing = defaultdict(int)
    for run in runs:
        for day in run.days:
            for label in day.scenario_labels:
                total[label] += 1
                if day.wearable_missingness != "none":
                    missing[label] += 1

    ordinary_rate = missing[Scenario.ORDINARY.value] / total[Scenario.ORDINARY.value]

    adverse = (
        Scenario.ILLNESS.value,
        Scenario.SLEEP_RESTRICTION.value,
        Scenario.SLEEP_COMPRESSION.value,
        Scenario.FAILURE_HEAVY.value,
    )
    adverse_missing = sum(missing[a] for a in adverse)
    adverse_total = sum(total[a] for a in adverse)
    adverse_rate = adverse_missing / adverse_total

    assert adverse_rate < ordinary_rate * 2.0, (
        f"adverse days miss data at {adverse_rate:.1%} against {ordinary_rate:.1%} "
        f"on ordinary days; absence would carry information about state"
    )


@pytest.mark.spec("DATA:missingness-not-concentrated")
def test_most_missing_nights_fall_on_ordinary_days(runs):
    ordinary = sum(
        1 for run in runs for d in run.days
        if d.wearable_missingness != "none"
        and d.scenario_labels == (Scenario.ORDINARY.value,)
    )
    all_missing = sum(
        1 for run in runs for d in run.days if d.wearable_missingness != "none"
    )
    assert ordinary / all_missing > 0.50, (
        "fewer than half of all gaps fall on ordinary days"
    )


def test_travel_raises_the_gap_rate_but_only_mildly(runs):
    """A real association, deliberately weak."""
    travel_total = travel_missing = 0
    for run in runs:
        for day in run.days:
            if Scenario.TRAVEL.value in day.scenario_labels:
                travel_total += 1
                travel_missing += day.wearable_missingness != "none"
    rate = travel_missing / travel_total
    assert 0.02 < rate < 0.25, f"travel gap rate {rate:.1%}"
    assert SIM_MISSINGNESS.travel_multiplier < 3.0, (
        "a strong travel association would let absence signal circumstance"
    )


# --- malformed fixture (DATA.md §17) ---------------------------------------

@pytest.mark.spec("DATA:raw-dirty-fixture")
def test_the_dirty_fixture_covers_both_rejection_and_repair():
    rows = raw_dirty_rows()
    assert len(rows) >= 12
    outcomes = Counter(r.expected for r in rows)
    assert outcomes["reject"] >= 6 and outcomes["repair"] >= 4, (
        "the fixture must distinguish unrecoverable defects from repairable ones"
    )
    assert all(r.defect for r in rows)
    assert len({r.defect for r in rows}) == len(rows), "duplicate defect descriptions"


@pytest.mark.spec("DATA:raw-dirty-fixture")
def test_the_dirty_fixture_is_not_part_of_the_generated_dataset(runs):
    """§17 keeps it separate so the clean data stays clean."""
    from rhome_core.exercises import ExerciseKind, load_library

    library = load_library()
    run = runs[0]
    for performed in run.sets:
        exercise = library[performed.exercise_id]
        assert performed.reps >= 1
        if exercise.exercise_kind is ExerciseKind.ASSISTED_REPS:
            pass  # negative external load is assistance, and is legitimate
        elif exercise.exercise_kind is ExerciseKind.REPS_ONLY:
            # Bodyweight movements carry no added load until they need one.
            assert performed.load_kg >= 0
        else:
            assert performed.load_kg > 0
        if performed.logged_rpe is not None:
            assert 2.0 <= performed.logged_rpe <= 10.0


def test_every_dirty_row_carries_the_full_schema():
    """A parser must fail on the defect, not on an absent column."""
    expected = set(raw_dirty_rows()[0].fields)
    for row in raw_dirty_rows():
        assert set(row.fields) == expected, f"{row.defect} has a different shape"


# --- determinism -----------------------------------------------------------

@pytest.mark.guardrail(4)
def test_missingness_is_deterministic():
    first = [(d.day_index, d.wearable_missingness) for d in simulate(3, n_days=200).days]
    second = [(d.day_index, d.wearable_missingness) for d in simulate(3, n_days=200).days]
    assert first == second


def test_missingness_model_rejects_nothing_when_rates_are_zero():
    import numpy as np
    from rhome_sim.missingness import MissingnessConstants

    model = MissingnessModel(
        np.random.default_rng(0),
        MissingnessConstants(
            partial_night_probability=0.0,
            full_night_probability=0.0,
            bodyweight_gap_start_probability=0.0,
            bodyweight_skip_probability=0.0,
            missing_effort_probability=0.0,
        ),
    )
    run = simulate(0, n_days=30)
    reading = run.days[0].wearable
    result, label = model.apply_to_wearable(reading)
    assert label == "none" and result == reading
    assert not model.effort_is_missing()
