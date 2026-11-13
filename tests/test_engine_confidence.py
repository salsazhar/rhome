"""Per-channel confidence (``MODEL.tex`` §Confidence, ``DATA.md`` §19.5).

Confidence is deterministic, which makes it testable in a way most of the
engine is not: every criterion in §19.5 is a statement about which direction a
number moves, and each has a test here that moves it.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import replace

import pytest

from rhome_core.exercises import CoefficientSource, load_library
from rhome_core.intensity import IntensityConfidence
from rhome_core.muscles import Muscle
from rhome_engine.confidence import Band, ConfidenceEngine, ConfidenceReport
from rhome_engine.dose import SetDose
from rhome_engine.performance import CapacityModel, _ExerciseCapacity
from rhome_engine.recovery import RecoveryContext, RecoveryReading
from rhome_engine.session import DayInput, RhomeEngine

LIBRARY = load_library()
BENCH = LIBRARY["bench_press"]
FULL = RecoveryReading(58.0, 52.0, 450.0, 0.90, 0.0)
BLANK = RecoveryReading()


def _context(explanation: float = 1.0, rms: float = 0.0) -> RecoveryContext:
    return RecoveryContext(rho=1.0, explanation_confidence=explanation, unexplained_rms=rms)


def _dose(
    confidence: IntensityConfidence = IntensityConfidence.HIGH, fatigue: float = 1.0
) -> SetDose:
    return SetDose(
        local_fatigue={Muscle.CHEST: fatigue},
        intensity_confidence=confidence,
        eligible_for_performance=True,
    )


def _mature(engine: ConfidenceEngine, days: int = 60, reading: RecoveryReading = FULL) -> None:
    for _ in range(days):
        engine.observe_day(_context(), reading.channels_present)


# --- components -------------------------------------------------------------

def test_no_wearable_data_floors_confidence_rather_than_zeroing_it():
    """The fatigue model runs on training data, so absent wearables cost 40%.

    Zeroing it would say the engine knows nothing, which is false: it still
    has every set the athlete logged.
    """
    engine = ConfidenceEngine()
    _mature(engine, 60, BLANK)
    assert engine.wearable_completeness().value == pytest.approx(0.60)

    complete = ConfidenceEngine()
    _mature(complete, 60, FULL)
    assert complete.wearable_completeness().value == pytest.approx(1.0)


def test_wearable_confidence_recovers_when_the_data_return():
    engine = ConfidenceEngine()
    _mature(engine, 60, FULL)
    for _ in range(7):
        engine.observe_day(_context(), BLANK.channels_present)
    withheld = engine.wearable_completeness().value
    assert withheld == pytest.approx(0.60)

    for _ in range(7):
        engine.observe_day(_context(), FULL.channels_present)
    assert engine.wearable_completeness().value == pytest.approx(1.0)


def test_confidence_rises_over_the_first_42_days_and_maturity_is_what_binds():
    """``DATA.md`` §19.5, fourth criterion, including the binding reason."""
    engine = ConfidenceEngine()
    capacity = CapacityModel()
    values = []
    for day in range(43):
        engine.observe_day(_context(), FULL.channels_present)
        engine.observe_set(_dose(), BENCH, day * 24.0)
        report = engine.report(capacity, day * 24.0)
        values.append(report.fatigue.value)
        if day < 41:
            assert report.fatigue.binding_reason.name == "baseline maturity"

    assert values == sorted(values), "confidence must not fall as baselines fill"
    assert values[0] < values[-1]
    assert engine.baseline_maturity().value == pytest.approx(1.0)


def test_dose_quality_weights_a_set_by_what_survives_of_it():
    """A set whose influence has decayed must not hold down present confidence."""
    engine = ConfidenceEngine()
    engine.observe_set(_dose(IntensityConfidence.LOW), BENCH, 0.0)
    assert engine.dose_quality().value == pytest.approx(0.60)

    # Six weeks later that set is nearly gone; a good set now dominates.
    engine.observe_set(_dose(IntensityConfidence.HIGH), BENCH, 42 * 24.0)
    assert engine.dose_quality().value > 0.99


def test_a_set_that_contributed_nothing_does_not_degrade_dose_quality():
    """Warm-ups carry no dose, so they carry no weight in dose quality.

    Counting them at a default weight of one put 1 848 unrated warm-up sets
    into the average at the lowest quality grade, and pinned dose confidence at
    0.69 across the whole record for sets that never touched a state variable.
    """
    engine = ConfidenceEngine()
    engine.observe_set(_dose(IntensityConfidence.HIGH), BENCH, 0.0)
    before = engine.dose_quality().value

    warmup = SetDose(local_fatigue={}, intensity_confidence=None)
    for index in range(20):
        engine.observe_set(warmup, BENCH, index * 0.02)
    assert engine.dose_quality().value == pytest.approx(before)


def test_a_derived_coefficient_costs_dose_quality():
    engine = ConfidenceEngine()
    engine.observe_set(_dose(), BENCH, 0.0)
    curated = engine.dose_quality().value

    # The v0 library is entirely curated, so the athlete-created case is
    # constructed rather than looked up. It is the case L5.1 makes common.
    derived_exercise = replace(BENCH, coefficient_source=CoefficientSource.DERIVED)
    other = ConfidenceEngine()
    other.observe_set(_dose(), derived_exercise, 0.0)
    assert other.dose_quality().value < curated


def test_capacity_confidence_falls_for_an_exercise_left_alone():
    """``DATA.md`` §19.5, third criterion.

    One week is forgiven, then staleness decays with a three-week constant.
    """
    engine = ConfidenceEngine()
    capacity = CapacityModel()
    for index in range(8):
        engine.observe_performance("bench_press", index * 48.0)
    now = 8 * 48.0

    # Staleness is measured from the last observation, not from the last time
    # anyone asked. The final set landed at hour 336.
    last = 7 * 48.0
    fresh = engine.observation_density("bench_press", now).value
    week = engine.observation_density("bench_press", last + 168.0).value
    fortnight = engine.observation_density("bench_press", last + 336.0).value
    month = engine.observation_density("bench_press", last + 720.0).value

    assert fresh == pytest.approx(1.0)
    assert week == pytest.approx(1.0), "the first week of rest is forgiven"
    assert fortnight < week
    assert month < 0.45
    assert "not trained for" in engine.observation_density("bench_press", last + 720.0).detail


def test_fit_confidence_falls_when_results_scatter():
    # Reach through to the residual store rather than simulating twenty
    # sessions: this test is about the mapping from spread to confidence.
    engine = ConfidenceEngine()
    tight, loose = CapacityModel(), CapacityModel()
    tight._state["bench_press"] = _ExerciseCapacity(capacity=100.0)
    loose._state["bench_press"] = _ExerciseCapacity(capacity=100.0)
    tight._residuals_by_exercise["bench_press"] = deque(maxlen=20)
    loose._residuals_by_exercise["bench_press"] = deque(maxlen=20)
    for index in range(20):
        sign = 1 if index % 2 else -1
        tight._residuals_by_exercise["bench_press"].append(sign * 0.01)
        loose._residuals_by_exercise["bench_press"].append(sign * 0.20)

    assert engine.fit_quality("bench_press", tight).value == pytest.approx(1.0)
    assert engine.fit_quality("bench_press", loose).value < 0.4001
    assert engine.fit_quality("bench_press", loose).value >= 0.40


def test_a_single_bad_session_does_not_read_as_a_badly_tracked_exercise():
    """Fit quality uses a robust spread, so one anomaly is not a verdict."""
    engine = ConfidenceEngine()
    model = CapacityModel()
    model._state["bench_press"] = _ExerciseCapacity(capacity=100.0)
    model._residuals_by_exercise["bench_press"] = deque(maxlen=20)
    for index in range(19):
        model._residuals_by_exercise["bench_press"].append(
            0.01 * (1 if index % 2 else -1)
        )
    model._residuals_by_exercise["bench_press"].append(-0.45)

    assert engine.fit_quality("bench_press", model).value > 0.9


def test_persistent_autonomic_surprise_lowers_confidence():
    engine = ConfidenceEngine()
    _mature(engine)
    assert engine.explanation().value == pytest.approx(1.0)

    for _ in range(14):
        engine.observe_day(_context(explanation=0.65, rms=2.3), FULL.channels_present)
    component = engine.explanation()
    assert component.value == pytest.approx(0.65)
    assert "2.3" in component.detail


# --- composition and display -------------------------------------------------

def test_the_binding_reason_is_always_the_lowest_component():
    """``DATA.md`` §19.5, fifth criterion."""
    engine = ConfidenceEngine()
    capacity = CapacityModel()
    for day in range(30):
        engine.observe_day(_context(explanation=0.8), (day % 3) * 2)
        engine.observe_set(_dose(IntensityConfidence.MEDIUM), BENCH, day * 24.0)
        report = engine.report(capacity, day * 24.0)
        for channel in (report.fatigue, report.neuromuscular, report.systemic):
            lowest = min(c.value for c in channel.components)
            assert channel.binding_reason.value == pytest.approx(lowest)
            assert channel.binding_reason.detail in channel.label


def test_the_three_display_bands_follow_the_documented_thresholds():
    engine = ConfidenceEngine()
    capacity = CapacityModel()
    _mature(engine)
    engine.observe_set(_dose(), BENCH, 0.0)
    report = engine.report(capacity, 0.0)
    assert report.fatigue.band is Band.HIGH

    from rhome_engine.confidence import Component, Confidence

    assert Confidence(0.75, (Component("x", 0.75, ""),)).band is Band.HIGH
    assert Confidence(0.7499, (Component("x", 0.7, ""),)).band is Band.MODERATE
    assert Confidence(0.50, (Component("x", 0.5, ""),)).band is Band.MODERATE
    assert Confidence(0.4999, (Component("x", 0.4, ""),)).band is Band.LIMITED


def test_projection_confidence_falls_with_horizon_at_the_documented_rate():
    engine = ConfidenceEngine()
    capacity = CapacityModel()
    _mature(engine)
    engine.observe_set(_dose(), BENCH, 0.0)
    report = engine.report(capacity, 0.0)

    now = report.fatigue.value
    assert report.projection(0.0).value == pytest.approx(now)
    assert report.projection(72.0).value / now == pytest.approx(0.80, abs=0.01)
    assert report.projection(168.0).value / now == pytest.approx(0.65, abs=0.05)
    assert report.projection(240.0).value / now == pytest.approx(0.50, abs=0.02)
    horizon = next(
        c for c in report.projection(72.0).components if c.name == "projection horizon"
    )
    assert "projected 3 days ahead" in horizon.detail

    with pytest.raises(ValueError):
        report.projection(-1.0)


# --- the counter-intuitive one ----------------------------------------------

@pytest.mark.spec("DATA:confidence-survives-missed-training")
def test_fatigue_confidence_holds_through_a_missed_session_block():
    """``DATA.md`` §19.5, second criterion — scenario S12.

    The intuitive design is wrong here. A fortnight away from the gym leaves
    the fatigue states *more* certain, not less: they have decayed toward zero
    and there is nothing left to be uncertain about. So C_F carries no
    training-recency term, and dose quality — a ratio of two sums that decay
    together — is unchanged by the absence.

    Capacity confidence is where the absence belongs, and it falls.
    """
    engine = ConfidenceEngine()
    capacity = CapacityModel()

    for day in range(60):
        engine.observe_day(_context(), FULL.channels_present)
        engine.observe_set(_dose(), BENCH, day * 24.0)
        engine.observe_performance("bench_press", day * 24.0)
    before = engine.report(capacity, 59 * 24.0)

    for day in range(60, 74):
        engine.observe_day(_context(), FULL.channels_present)
    after = engine.report(capacity, 73 * 24.0)

    assert after.fatigue.value == pytest.approx(before.fatigue.value, abs=1e-9)
    assert after.capacity["bench_press"].value < before.capacity["bench_press"].value


@pytest.mark.spec("DATA:confidence-tracks-wearable-gaps")
def test_confidence_over_the_real_development_window():
    """The criteria above, on the dataset rather than on constructed input."""
    from test_session_driver import DATASET, _days  # noqa: PLC0415

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")

    engine = RhomeEngine(LIBRARY)
    results = engine.run(_days()[:520])

    # §19.5 expects baseline maturity to bind while the 42-day windows fill.
    # It does on all but two days, both of which contain sets whose effort the
    # athlete did not record: an imputed set is marked down, and on a day with
    # three of them dose quality legitimately becomes the weaker term.
    early = [r for r in results[:41]]
    bound_by_maturity = [
        r for r in early if r.confidence.fatigue.binding_reason.name == "baseline maturity"
    ]
    assert len(bound_by_maturity) >= 38, f"only {len(bound_by_maturity)} of 41"
    for result in early:
        if result.confidence.fatigue.binding_reason.name != "baseline maturity":
            assert any(dose.effort_imputed for _, dose in result.doses)
    assert early[0].confidence.fatigue.value < early[-1].confidence.fatigue.value

    mature = [r.confidence.fatigue for r in results[60:]]
    assert min(c.value for c in mature) > 0.5
    assert all(c.band is not Band.LIMITED for c in mature)

    # Nights the athlete did not wear the ring show up as the binding reason.
    gaps = [c for c in mature if c.binding_reason.name == "wearable completeness"]
    assert gaps, "the dataset contains missing nights; they should bind somewhere"

    # Fit quality separates the exercises the engine tracks well from the rest,
    # and it lands on the isolation movements — which is where the simulator
    # puts its larger performance noise, unseen by the engine.
    final = results[-1].confidence.capacity
    fits = {
        exercise_id: next(c.value for c in conf.components if c.name == "fit quality")
        for exercise_id, conf in final.items()
    }
    worst = min(fits, key=fits.get)
    assert LIBRARY[worst].compoundness < 0.5, (
        f"worst-fitting exercise {worst} should be an isolation movement"
    )


@pytest.mark.spec("MODEL:unrated-set-imputed")
def test_confidence_falls_on_a_day_whose_sets_went_unrated():
    """The Layer 2 audit's one finding, kept as a standing test.

    Before the fix, day 45 lost three of fifteen working sets to missing effort
    ratings and reported confidence of 0.9971 — *higher* than either
    neighbouring day. Each link in the chain was defensible: an unrated set
    could not be transformed, a set with no dose had no weight in dose quality,
    and the day therefore looked like a shorter session that was well recorded.

    The distinction against the missed-session case matters. Not training is
    informative about fatigue and confidence rightly holds. Training and not
    recording it is the opposite: the work happened, the fatigue is real, and
    the model does not know.
    """
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")

    engine = RhomeEngine(LIBRARY)
    results = engine.run(_days()[:520])

    affected = [
        r for r in results[1:-1]
        if sum(1 for _, dose in r.doses if dose.effort_imputed) >= 2
    ]
    assert affected, "the dataset should contain days with unrated working sets"

    for result in affected:
        dose_quality = next(
            component for component in result.confidence.fatigue.components
            if component.name == "dose quality"
        )
        assert dose_quality.value < 1.0, (
            f"day {result.day_index} imputed effort but its dose-quality "
            f"component remained {dose_quality.value:.4f}"
        )


@pytest.mark.spec("MODEL:unrated-set-imputed")
def test_an_imputed_set_still_contributes_its_fatigue():
    """The point of imputing rather than discarding."""
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")

    engine = RhomeEngine(LIBRARY)
    results = engine.run(_days()[:520])
    imputed = [dose for r in results for _, dose in r.doses if dose.effort_imputed]

    assert len(imputed) > 50
    assert all(dose.local_fatigue for dose in imputed)
    assert all(not dose.eligible_for_performance for dose in imputed)
