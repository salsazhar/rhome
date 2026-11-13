"""Confidence and trace integrity as a suite (``DATA.md`` §19.5–19.6, L3.6).

The properties were tested as they were built. This runs them as an evaluation
over the whole window, and measures whether the capacity-maturity component
added here fixed the thing it was added for.
"""

from __future__ import annotations

import pytest

from rhome_engine.confidence import Band, ConfidenceEngine
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_eval.confidence_metrics import (
    NOT_YET_COMPETITIVE,
    score_confidence,
    score_traces,
)
from rhome_eval.run import evaluate
from rhome_eval.window import Window


@pytest.fixture(scope="module")
def run():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    return evaluate(_days(), Window.DEVELOPMENT)


@pytest.fixture(scope="module")
def confidence(run):
    return score_confidence(run)


@pytest.fixture(scope="module")
def traces(run):
    return score_traces(run)


# --- the component added at this stage ---------------------------------------

@pytest.mark.spec("MODEL:capacity-maturity")
def test_capacity_confidence_no_longer_reads_high_before_the_engine_is_competitive(
    confidence,
):
    """The defect this component was added to fix.

    Before it, 88.5% of readings in an exercise's first ten sessions said
    ``high`` while the engine was losing to a median-of-the-last-three
    baseline. Its only observation term counted the last 28 days — a recency
    check — and said nothing about whether the engine had ever seen enough of
    the exercise to have an opinion.
    """
    first_band = confidence.experience[0]
    assert first_band.lower == 1
    assert first_band.bands.get(Band.HIGH.value, 0) == 0, (
        f"{first_band.bands.get(Band.HIGH.value)} readings claim high "
        f"confidence in an exercise's first ten sessions"
    )
    assert first_band.mean_confidence < 0.65
    assert confidence.high_before_competitive < 0.35


@pytest.mark.spec("MODEL:capacity-maturity")
def test_capacity_confidence_rises_with_experience(confidence):
    means = [b.mean_confidence for b in confidence.experience]
    assert means == sorted(means)
    assert means[-1] > 0.85
    fractions = [b.high_fraction for b in confidence.experience]
    assert fractions == sorted(fractions)


@pytest.mark.spec("MODEL:capacity-maturity")
def test_maturity_counts_sessions_not_sets():
    """The ablation counted one observation per exercise per session.

    Counting every eligible set instead saturates after about nine sessions,
    which is inside the period the component exists to flag.
    """
    engine = ConfidenceEngine()
    for index in range(4):
        engine.observe_performance("bench_press", index * 0.02, session_key="d0001")
    assert engine.capacity_maturity("bench_press").value == pytest.approx(
        ENGINE_PARAMETERS.value("confidence_maturity_floor")
        + ENGINE_PARAMETERS.value("confidence_maturity_span") / 25
    )

    for day in range(1, 30):
        engine.observe_performance("bench_press", day * 24.0, session_key=f"d{day:04d}")
    assert engine.capacity_maturity("bench_press").value == pytest.approx(1.0)


def test_a_new_exercise_is_weak_evidence_not_no_evidence():
    """The floor is deliberate: an unfamiliar lift still tells you something."""
    engine = ConfidenceEngine()
    floor = ENGINE_PARAMETERS.value("confidence_maturity_floor")
    assert engine.capacity_maturity("never_seen").value == pytest.approx(floor)
    assert 0.3 < floor < 0.6


def test_a_saturated_component_does_not_report_itself_as_binding(confidence):
    """Ties break toward the earlier component, so ordering is not cosmetic.

    With maturity placed first it won every tie and was reported as the binding
    reason on settled exercises, where nothing was binding at all.
    """
    settled = confidence.experience[-1]
    assert settled.binding.get("capacity maturity", 0) < settled.n * 0.2


# --- §19.5, as a suite --------------------------------------------------------

@pytest.mark.spec("DATA:confidence-suite")
def test_the_binding_reason_is_the_lowest_component_on_every_day(confidence):
    assert confidence.binding_always_lowest
    assert confidence.days == len(Window.DEVELOPMENT.days)


@pytest.mark.spec("DATA:confidence-suite")
def test_baseline_maturity_binds_while_the_windows_fill(confidence):
    assert confidence.early_bound_by_maturity > 0.9


@pytest.mark.spec("DATA:confidence-suite")
def test_a_night_without_wearable_data_costs_confidence(confidence):
    assert confidence.wearable_gap_days > 0
    assert confidence.wearable_gap_penalty > 0.05, (
        "a fully missing night should cost measurably more than a complete one"
    )


# --- §19.6, as a suite --------------------------------------------------------

@pytest.mark.spec("DATA:trace-suite")
def test_every_trace_decomposes_exactly(traces):
    assert traces.traces > 5000
    assert traces.worst_share_error < 1e-9
    assert traces.worst_reconstruction_error < 1e-9


@pytest.mark.spec("DATA:trace-suite")
def test_no_driver_string_crosses_a_claim_boundary(traces):
    assert traces.distinct_drivers > 1000
    assert traces.boundary_violations == ()


@pytest.mark.spec("DATA:trace-suite")
def test_every_trace_discloses_its_evidence_grades(traces):
    assert traces.graded_parameters > 20
    assert sum(traces.grade_counts.values()) == traces.graded_parameters
    assert traces.grade_counts.get("C", 0) > traces.grade_counts.get("A", 0), (
        "the disclosure is the point: most of this rests on engineering priors"
    )


def test_the_reports_carry_the_window_caveat(confidence, traces):
    assert "development" in confidence.caveat
    assert "development" in traces.caveat


def test_the_competitive_threshold_is_the_measured_one():
    assert NOT_YET_COMPETITIVE == 20
