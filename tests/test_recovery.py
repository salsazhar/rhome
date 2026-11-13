"""Recovery physiology and wearable generation (``DATA.md`` §11, §16.2).

The properties here decide whether the engine's recovery-context model is
genuinely tested. Wearable data that was a clean readout of training load would
make the engine's job trivial and its caution pointless.
"""

from __future__ import annotations

import statistics as st

import numpy as np
import pytest

from rhome_core.seeding import RootSeed
from rhome_sim.athlete import sample_athlete
from rhome_sim.recovery import SIM_RECOVERY, RecoveryModel

SEED = 20260822
ATHLETE = sample_athlete(SEED)


def _model(seed: int = SEED) -> RecoveryModel:
    return RecoveryModel(ATHLETE, RootSeed(seed).stream("sim.recovery"))


def _run(model: RecoveryModel, loads: list[float]):
    return [model.step(i, systemic_load=load) for i, load in enumerate(loads)]


@pytest.fixture(scope="module")
def two_years():
    model = _model()
    loads = [0.45 + 0.35 * float(np.sin(i / 3.0)) for i in range(730)]
    days = _run(model, loads)
    readings = [model.observe(day, body_mass_kg=80.0) for day in days]
    return days, readings


# --- documented distributions (DATA.md §11) --------------------------------

@pytest.mark.spec("DATA:recovery-variables-correlated")
def test_sleep_matches_the_documented_distribution(two_years):
    _, readings = two_years
    hours = [r.total_sleep_min / 60.0 for r in readings]
    assert st.mean(hours) == pytest.approx(7.5, abs=0.25)
    # Asserted at the documented range, not a looser one. The fixture applies
    # no scenario overrides, so every night here is an ordinary night, which is
    # what §11.2's figure describes; a record including deliberate restriction
    # blocks carries more variance and is measured separately in the audit.
    spread = st.pstdev(hours)
    assert 0.6 <= spread <= 0.9, f"night-to-night SD {spread:.2f} h, §11.2 asks 0.6-0.9"


@pytest.mark.spec("DATA:recovery-variables-correlated")
def test_autonomic_channels_centre_on_their_personal_baselines(two_years):
    _, readings = two_years
    assert st.mean([r.hrv_rmssd_ms for r in readings]) == pytest.approx(60.0, abs=4.0)
    assert st.mean([r.resting_hr_bpm for r in readings]) == pytest.approx(52.0, abs=1.5)


def test_sleep_is_serially_correlated(two_years):
    """DATA.md §11.2: a bad night modestly raises the chance of another."""
    days, _ = two_years
    hours = [d.true_sleep_h for d in days]
    lag1 = float(np.corrcoef(hours[:-1], hours[1:])[0, 1])
    assert 0.1 < lag1 < 0.8, f"lag-1 autocorrelation {lag1:.2f}"


@pytest.mark.spec("DATA:recovery-variables-correlated")
def test_hrv_and_resting_hr_are_only_partially_anti_correlated(two_years):
    """DATA.md §18: noisy and only partially anti-correlated."""
    _, readings = two_years
    r = float(np.corrcoef(
        [x.hrv_rmssd_ms for x in readings], [x.resting_hr_bpm for x in readings]
    )[0, 1])
    assert -0.85 < r < -0.15, f"correlation {r:+.2f} is too strong or too weak"


@pytest.mark.spec("DATA:sleep-stage-invariant")
def test_sleep_stages_never_exceed_total_sleep(two_years):
    _, readings = two_years
    for reading in readings:
        assert reading.rem_sleep_min + reading.deep_sleep_min <= reading.total_sleep_min
        assert reading.rem_sleep_min > 0 and reading.deep_sleep_min > 0


def test_observations_stay_within_plausible_bounds(two_years):
    _, readings = two_years
    for reading in readings:
        assert 120.0 <= reading.total_sleep_min <= 720.0
        assert 0.60 <= reading.sleep_efficiency <= 1.0
        assert reading.hrv_rmssd_ms > 0
        assert 35.0 <= reading.resting_hr_bpm <= 90.0
        assert reading.steps >= 0


# --- HRV must not be a training-load readout -------------------------------

@pytest.mark.spec("DATA:hrv-not-a-load-readout")
def test_high_load_shifts_hrv_downward_in_distribution():
    """The effect must be real, or the engine has nothing to learn."""
    high, low = [], []
    for seed in range(120):
        model = _model(3000 + seed)
        days = _run(model, [1.2 if i % 3 == 0 else 0.1 for i in range(90)])
        high += [days[i].true_log_rmssd_deviation for i in range(3, 90, 3)]
        low += [days[i].true_log_rmssd_deviation for i in range(4, 89, 3)]
    spread = st.pstdev(high + low)
    effect = (st.mean(low) - st.mean(high)) / spread
    assert effect > 0.10, f"load effect only {effect:.2f} sd; too weak to learn"


@pytest.mark.spec("DATA:hrv-not-a-load-readout")
def test_a_hard_day_does_not_force_hrv_downward():
    """``DATA.md`` §11.3, stated almost verbatim.

    An engine that treats one low reading as proof of under-recovery must be
    punished by this data, so a substantial minority of high-load days have to
    carry a perfectly normal reading.
    """
    above = total = 0
    for seed in range(120):
        model = _model(4000 + seed)
        days = _run(model, [1.2 if i % 3 == 0 else 0.1 for i in range(90)])
        for i in range(3, 90, 3):
            total += 1
            above += days[i].true_log_rmssd_deviation > 0
    fraction = above / total
    assert fraction > 0.20, (
        f"only {fraction:.0%} of hard days carry an above-baseline reading; "
        f"HRV is behaving as a load readout"
    )
    assert fraction < 0.50, "and the effect must still exist"


@pytest.mark.spec("DATA:hrv-not-a-load-readout")
def test_deload_produces_autonomic_rebound_usually_but_not_always():
    """Scenario S3 depends on this, and its unreliability is deliberate."""
    rebounds = 0
    trials = 120
    for seed in range(trials):
        model = _model(5000 + seed)
        days = _run(model, [0.9] * 60 + [0.15] * 20)
        block = st.mean(d.true_log_rmssd_deviation for d in days[45:60])
        deload = st.mean(d.true_log_rmssd_deviation for d in days[70:80])
        rebounds += deload > block
    fraction = rebounds / trials
    assert fraction > 0.60, f"rebound visible in only {fraction:.0%} of runs"
    assert fraction < 0.98, (
        "rebound is never masked; the latent stress process is not doing its job"
    )


# --- the unobserved stress process -----------------------------------------

@pytest.mark.spec("DATA:latent-stress-unobserved")
def test_stress_moves_several_channels_together():
    """The engine sees three channels move in concert with no visible cause."""
    calm = _model(6001)
    calm_days = _run(calm, [0.45] * 200)

    stressed = _model(6001)
    stressed_days = [
        stressed.step(i, systemic_load=0.45, stress_shock=1.2 if 100 <= i < 130 else 0.0)
        for i in range(200)
    ]

    window = slice(105, 130)
    assert st.mean(d.true_sleep_h for d in stressed_days[window]) < st.mean(
        d.true_sleep_h for d in calm_days[window]
    )
    assert st.mean(d.true_log_rmssd_deviation for d in stressed_days[window]) < st.mean(
        d.true_log_rmssd_deviation for d in calm_days[window]
    )
    assert st.mean(d.true_resting_hr for d in stressed_days[window]) > st.mean(
        d.true_resting_hr for d in calm_days[window]
    )


@pytest.mark.spec("DATA:latent-stress-unobserved")
def test_stress_appears_in_no_observable_field(two_years):
    """It is latent by construction: nothing reports it."""
    _, readings = two_years
    assert not hasattr(readings[0], "stress")
    assert "stress" not in vars(readings[0])


def test_stress_is_persistent_not_white_noise(two_years):
    days, _ = two_years
    values = [d.stress for d in days]
    lag1 = float(np.corrcoef(values[:-1], values[1:])[0, 1])
    assert lag1 > 0.5, f"stress autocorrelation {lag1:.2f}; should persist across days"


# --- measurement error -----------------------------------------------------

@pytest.mark.spec("DATA:wearable-measurement-error")
def test_the_reading_is_not_the_latent_value(two_years):
    days, readings = two_years
    exact = sum(
        1
        for day, reading in zip(days, readings)
        if abs(reading.total_sleep_min - day.true_sleep_h * 60.0) < 1e-9
    )
    assert exact == 0, "measurement error is not being applied"


@pytest.mark.spec("DATA:wearable-measurement-error")
def test_measurement_error_magnitudes_match_the_research_summary(two_years):
    """``RESEARCH.md`` §13.3, derived from Oura validation studies."""
    days, readings = two_years
    sleep_errors = [
        r.total_sleep_min - d.true_sleep_h * 60.0 for d, r in zip(days, readings)
    ]
    assert st.pstdev(sleep_errors) == pytest.approx(
        SIM_RECOVERY.sleep_measurement_sd_min, rel=0.35
    )
    assert abs(st.mean(sleep_errors)) < 4.0, "measurement error must be unbiased"

    rhr_errors = [r.resting_hr_bpm - d.true_resting_hr for d, r in zip(days, readings)]
    assert st.pstdev(rhr_errors) == pytest.approx(
        SIM_RECOVERY.rhr_measurement_sd, rel=0.35
    )


def test_body_mass_is_noisier_than_the_underlying_mass(two_years):
    _, readings = two_years
    masses = [r.body_mass_kg for r in readings]
    assert all(m is not None for m in masses)
    assert st.pstdev(masses) == pytest.approx(SIM_RECOVERY.body_mass_measurement_sd, rel=0.4)


def test_body_mass_is_omitted_when_not_supplied(two_years):
    days, _ = two_years
    model = _model()
    assert model.observe(days[0]).body_mass_kg is None


# --- recovery propensity ---------------------------------------------------

def test_true_recovery_range_exceeds_what_the_engine_can_express(two_years):
    """The engine clips its multiplier to [0.80, 1.15]; truth is wider.

    Another structural difference: at the extremes the engine cannot represent
    the athlete's actual recovery quality however well it is calibrated.
    """
    days, _ = two_years
    values = [d.recovery_propensity for d in days]
    assert min(values) < 0.80 or max(values) > 1.15, (
        "true recovery never leaves the engine's expressible range"
    )
    assert SIM_RECOVERY.propensity_floor < 0.80
    assert SIM_RECOVERY.propensity_ceiling > 1.15


def test_recovery_propensity_stays_positive_and_bounded(two_years):
    days, _ = two_years
    for day in days:
        assert SIM_RECOVERY.propensity_floor <= day.recovery_propensity <= SIM_RECOVERY.propensity_ceiling


def test_poor_sleep_lowers_recovery_propensity():
    model = _model(7001)
    normal = [model.step(i, systemic_load=0.45) for i in range(60)]
    model = _model(7001)
    restricted = [
        model.step(i, systemic_load=0.45, sleep_override_h=5.5) for i in range(60)
    ]
    assert st.mean(d.recovery_propensity for d in restricted) < st.mean(
        d.recovery_propensity for d in normal
    )


# --- scenario hooks --------------------------------------------------------

def test_sleep_override_drives_restriction_scenarios():
    model = _model(8001)
    days = [model.step(i, systemic_load=0.4, sleep_override_h=5.5) for i in range(40)]
    assert st.mean(d.true_sleep_h for d in days) == pytest.approx(5.5, abs=0.35)
    assert st.pstdev([d.true_sleep_h for d in days]) > 0.05, "override must stay noisy"


def test_temperature_offset_drives_illness_scenarios():
    model = _model(8002)
    days = [model.step(i, systemic_load=0.4, temperature_offset=0.7) for i in range(40)]
    assert st.mean(d.true_temperature_deviation for d in days) > 0.4
    assert st.mean(d.recovery_propensity for d in days) < 1.0


def test_steps_override_drives_travel_scenarios():
    model = _model(8003)
    days = [model.step(i, systemic_load=0.4, steps_override=21000) for i in range(20)]
    assert all(d.true_steps == 21000 for d in days)


# --- determinism -----------------------------------------------------------

@pytest.mark.guardrail(4)
def test_recovery_generation_is_deterministic():
    def run():
        model = _model()
        days = _run(model, [0.5] * 100)
        return [(d.true_sleep_h, d.true_log_rmssd_deviation) for d in days]

    assert run() == run()
