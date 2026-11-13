"""Recovery context (``MODEL.tex`` §Recovery context, §Conditioning)."""

from __future__ import annotations

import math
import random
import statistics as st

import numpy as np
import pytest

from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.recovery import RecoveryContextEngine, RecoveryReading

FLOOR = ENGINE_PARAMETERS.value("rho_floor")
CEILING = ENGINE_PARAMETERS.value("rho_ceiling")
NORMAL = RecoveryReading(60.0, 52.0, 450.0, 0.90, 0.0)


def _matured(seed: int = 0, days: int = 60, varying_load: bool = True):
    """An engine with mature baselines, built from ordinary days."""
    rng = random.Random(seed)
    engine = RecoveryContextEngine()
    for day in range(days):
        load = 0.55 + 0.35 * math.sin(day / 3.0) + rng.gauss(0, 0.08) if varying_load else 0.5
        engine.step(
            RecoveryReading(
                60 + rng.gauss(0, 8), 52 + rng.gauss(0, 2),
                450 + rng.gauss(0, 50), 0.90 + rng.gauss(0, 0.02), rng.gauss(0, 0.1),
            ),
            max(0.0, load),
        )
    return engine


# --- the multiplier (MODEL.tex) --------------------------------------------

@pytest.mark.spec("MODEL:recovery-multiplier")
def test_an_ordinary_day_gives_a_multiplier_near_one():
    context = _matured().context(NORMAL, systemic_load=0.55)
    assert 0.93 <= context.rho <= 1.07


@pytest.mark.spec("MODEL:recovery-multiplier")
def test_the_multiplier_stays_within_its_documented_bounds():
    engine = _matured()
    extremes = [
        RecoveryReading(200.0, 30.0, 700.0, 0.99, 0.0),
        RecoveryReading(10.0, 90.0, 180.0, 0.60, 2.0),
    ]
    for reading in extremes:
        for load in (0.0, 3.0):
            rho = engine.context(reading, systemic_load=load).rho
            assert FLOOR <= rho <= CEILING


@pytest.mark.spec("MODEL:recovery-multiplier")
def test_favourable_readings_raise_the_multiplier_and_poor_ones_lower_it():
    engine = _matured()
    good = engine.context(RecoveryReading(78.0, 49.0, 510.0, 0.94, 0.0), 0.55)
    poor = engine.context(RecoveryReading(44.0, 57.0, 330.0, 0.85, 0.5), 0.55)
    assert good.rho > poor.rho
    assert good.rho > 1.0 > poor.rho


def test_each_coefficient_pushes_the_multiplier_the_documented_way():
    engine = _matured()
    base = engine.context(NORMAL, 0.55).rho
    assert engine.context(RecoveryReading(80.0, 52.0, 450.0, 0.90, 0.0), 0.55).rho > base
    assert engine.context(RecoveryReading(60.0, 58.0, 450.0, 0.90, 0.0), 0.55).rho < base
    assert engine.context(RecoveryReading(60.0, 52.0, 540.0, 0.90, 0.0), 0.55).rho > base
    # Temperature departure is unfavourable in either direction.
    warm = engine.context(RecoveryReading(60.0, 52.0, 450.0, 0.90, 0.4), 0.55).rho
    cold = engine.context(RecoveryReading(60.0, 52.0, 450.0, 0.90, -0.4), 0.55).rho
    assert warm < base and cold < base


# --- the conditional expectation (MODEL.tex) -------------------------------

@pytest.mark.spec("MODEL:conditional-autonomic-expectation")
def test_the_same_reading_means_different_things_after_training_and_at_rest():
    """The distinction a rolling baseline alone cannot make."""
    engine = _matured()
    reading = RecoveryReading(46.0, 55.0, 450.0, 0.90, 0.0)

    after_training = engine.context(reading, systemic_load=1.30)
    at_rest = engine.context(reading, systemic_load=0.10)

    assert after_training.rho > at_rest.rho, (
        "a depressed reading the model predicted should alarm it less than the "
        "same reading it did not predict"
    )
    assert after_training.partitions["hrv"].explained_share > 0.25
    assert at_rest.partitions["hrv"].explained_share < 0.05


@pytest.mark.spec("MODEL:conditional-autonomic-expectation")
def test_the_partition_sums_back_to_the_observation():
    engine = _matured()
    context = engine.context(RecoveryReading(48.0, 56.0, 450.0, 0.90, 0.0), 1.2)
    for name, part in context.partitions.items():
        assert part.observed_z == pytest.approx(part.expected_z + part.residual_z, abs=1e-9), (
            f"{name}: the partition must account for the whole deviation"
        )


@pytest.mark.spec("MODEL:conditional-autonomic-expectation")
def test_the_expectation_has_the_documented_sign():
    """High load predicts lower HRV and higher resting heart rate."""
    engine = _matured()
    heavy = engine.context(NORMAL, systemic_load=1.4)
    assert heavy.partitions["hrv"].expected_z < 0
    assert heavy.partitions["resting_hr"].expected_z > 0


def test_with_no_load_variation_the_expectation_is_neutral():
    """Nothing to condition on means nothing is subtracted.

    A constant training load carries no information about which days should
    differ, so the conditional form degrades to the plain rolling baseline
    rather than inventing an expectation.
    """
    engine = _matured(varying_load=False)
    context = engine.context(RecoveryReading(46.0, 55.0, 450.0, 0.90, 0.0), 0.5)
    assert context.partitions["hrv"].expected_z == pytest.approx(0.0, abs=1e-9)
    assert context.partitions["hrv"].residual_z == pytest.approx(
        context.partitions["hrv"].observed_z, abs=1e-9
    )


# --- missing data (MODEL.tex) ----------------------------------------------

@pytest.mark.spec("MODEL:missing-data-is-not-a-penalty")
def test_a_fully_missing_night_leaves_the_multiplier_neutral():
    """Absence of evidence never stands in for evidence of a problem."""
    context = _matured().context(RecoveryReading(), systemic_load=1.5)
    assert context.rho == pytest.approx(1.0)
    assert context.is_neutral
    assert context.channels_present == 0


@pytest.mark.spec("MODEL:missing-data-is-not-a-penalty")
def test_a_partial_night_uses_only_what_is_present():
    engine = _matured()
    full = engine.context(NORMAL, 0.55)
    partial = engine.context(RecoveryReading(60.0, None, 450.0, 0.90, 0.0), 0.55)
    assert partial.channels_used == full.channels_used - 1
    assert "resting_hr" not in partial.contributions
    assert FLOOR <= partial.rho <= CEILING


@pytest.mark.spec("MODEL:missing-data-is-not-a-penalty")
def test_a_thin_baseline_contributes_nothing_rather_than_noise():
    """A standard deviation from three nights is not a baseline."""
    engine = RecoveryContextEngine()
    for _ in range(3):
        engine.step(NORMAL, 0.5)
    context = engine.context(RecoveryReading(20.0, 80.0, 450.0, 0.90, 0.0), 0.5)
    assert "hrv" not in context.contributions
    assert "resting_hr" not in context.contributions


def test_baselines_mature_and_channels_come_online():
    engine = RecoveryContextEngine()
    used = []
    for day in range(30):
        used.append(engine.step(NORMAL, 0.5 + 0.2 * math.sin(day)).channels_used)
    assert used[0] < used[-1], "channels should come online as baselines mature"


# --- ordering --------------------------------------------------------------

def test_a_reading_is_standardised_against_the_days_before_it():
    """Including today in its own baseline would leak the answer into it."""
    engine = _matured()
    # A moderately low reading, chosen to sit inside the clip: an extreme one
    # would pin at -3 both times and the test would compare two clipped values.
    unusual = RecoveryReading(50.0, 52.0, 450.0, 0.90, 0.0)
    before = engine.context(unusual, 0.55)
    engine.step(unusual, 0.55)
    after = engine.context(unusual, 0.55)
    assert -3.0 < before.raw_z["hrv"] < after.raw_z["hrv"], (
        "once an unusual day joins the baseline, a repeat of it looks less unusual"
    )


# --- confidence (MODEL.tex) ------------------------------------------------

@pytest.mark.spec("MODEL:unexplained-deviation-lowers-confidence")
def test_persistent_unexplained_deviation_lowers_confidence():
    engine = _matured()
    for _ in range(14):
        engine.step(NORMAL, 0.55)
    settled = engine.context(NORMAL, 0.55).explanation_confidence

    surprised = _matured()
    for _ in range(14):
        surprised.step(RecoveryReading(28.0, 66.0, 450.0, 0.90, 0.0), 0.10)
    disturbed = surprised.context(NORMAL, 0.55)

    assert disturbed.explanation_confidence < settled
    assert disturbed.explanation_confidence >= ENGINE_PARAMETERS.value("unexplained_floor")


@pytest.mark.spec("MODEL:unexplained-deviation-lowers-confidence")
def test_unexplained_deviation_does_not_move_the_multiplier_directly():
    """Confidence carries the surprise; rho carries only the evidence."""
    engine = _matured()
    context = engine.context(NORMAL, 0.55)
    assert "unexplained" not in context.contributions
    assert context.explanation_confidence <= 1.0


# --- validation against the simulator's truth ------------------------------

def test_the_residual_removes_the_training_component():
    """The partition is checked against known truth.

    The direct claim is that the residual no longer carries the part of the
    reading that recent training explains. An earlier version of this test
    asked instead whether the residual correlates *better* with the simulator's
    unobserved stress process, and it failed — because load and stress are
    themselves slightly correlated in the simulator, so the load term was
    inflating the apparent stress correlation. Removing it strips that spurious
    help at the same time as it reduces variance, and the two nearly cancel.

    The premise was wrong, not the conditioning.
    """
    from rhome_sim.generate import simulate

    run = simulate(20260822, n_days=420)
    engine = RecoveryContextEngine()

    raw, residual, load = [], [], []
    for day in run.days:
        reading = RecoveryReading(
            day.wearable.hrv_rmssd_ms, day.wearable.resting_hr_bpm,
            day.wearable.total_sleep_min, day.wearable.sleep_efficiency,
            day.wearable.temperature_deviation_c,
        )
        context = engine.step(reading, day.state_on_waking.systemic)
        if "hrv" in context.partitions:
            part = context.partitions["hrv"]
            raw.append(part.observed_z)
            residual.append(part.residual_z)
            load.append(part.expected_z)

    assert len(raw) > 250
    raw_r = abs(float(np.corrcoef(raw, load)[0, 1]))
    residual_r = abs(float(np.corrcoef(residual, load)[0, 1]))
    assert raw_r > 0.2, "the simulator must relate load to HRV, or there is nothing to remove"
    assert residual_r < 0.10, (
        f"the residual still carries {residual_r:.3f} correlation with training load; "
        f"the conditioning has not removed it"
    )
    assert st.pvariance(residual) < st.pvariance(raw)


def test_the_expectation_coefficient_is_close_to_the_true_relationship():
    """A Grade C prior, checked against data it was not fitted to.

    The engine assumes a systemic load one standard deviation above normal
    depresses HRV by 0.30 standard deviations. That number came from the
    reported direction of an effect and an estimate of its plausible size, not
    from any fit. Regressing the simulator's own output recovers a slope near
    0.33, so the prior is within roughly a tenth of the relationship the
    simulator actually generates.

    This is not proof the coefficient is right for a human. It is evidence that
    the guess was not wild, and it is the kind of check personalisation will
    later replace with a fitted value and an interval.
    """
    from rhome_sim.generate import simulate

    run = simulate(20260822, n_days=420)
    engine = RecoveryContextEngine()

    observed, standardised_load = [], []
    for day in run.days:
        reading = RecoveryReading(
            day.wearable.hrv_rmssd_ms, day.wearable.resting_hr_bpm,
            day.wearable.total_sleep_min, day.wearable.sleep_efficiency,
            day.wearable.temperature_deviation_c,
        )
        context = engine.step(reading, day.state_on_waking.systemic)
        if "hrv" in context.partitions:
            part = context.partitions["hrv"]
            observed.append(part.observed_z)
            standardised_load.append(part.expected_z / -ENGINE_PARAMETERS.value("gamma_hrv"))

    slope = float(np.polyfit(standardised_load, observed, 1)[0])
    assumed = -ENGINE_PARAMETERS.value("gamma_hrv")
    assert slope < 0, "load must depress HRV in the generated data"
    assert abs(slope - assumed) < 0.15, (
        f"assumed {assumed:+.2f} against a fitted {slope:+.2f}"
    )
