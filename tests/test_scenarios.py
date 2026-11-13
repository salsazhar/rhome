"""Scenario engine (``DATA.md`` §13, §14, §15).

Each scenario carries a documented intended effect on the latent state. These
tests assert those effects actually occur, rather than assuming that setting a
dial produced the behaviour it was meant to.
"""

from __future__ import annotations

import statistics as st

import pytest

from rhome_core.muscles import Muscle
from rhome_sim.generate import simulate
from rhome_sim.scenarios import (
    SCENARIO_SCHEDULE,
    DayModifiers,
    Scenario,
    ScenarioEngine,
    ScenarioWindow,
)

SEED = 20260822


@pytest.fixture(scope="module")
def run():
    return simulate(SEED)


@pytest.fixture(scope="module")
def engine():
    return ScenarioEngine()


def _window(scenario: Scenario, index: int = 0) -> ScenarioWindow:
    return ScenarioEngine().windows_for(scenario)[index]


def _mean_local_fatigue(days) -> float:
    values = [
        st.mean(d.state_on_waking.local_fatigue(m) for m in Muscle) for d in days
    ]
    return st.mean(values)


def _ordinary_days(run, near: int, span: int = 25):
    """Ordinary days on either side of a scenario, for comparison."""
    return [
        d for d in run.days
        if abs(d.day_index - near) <= span
        and d.scenario_labels == (Scenario.ORDINARY.value,)
    ]


# --- library completeness (DATA.md §13, §15) -------------------------------

@pytest.mark.spec("DATA:scenario-library-complete")
def test_every_scenario_family_is_present(engine):
    missing = set(Scenario) - engine.scenarios_present()
    assert not missing, f"absent from the schedule: {sorted(m.value for m in missing)}"


@pytest.mark.spec("DATA:scenarios-in-both-windows")
def test_scenario_families_appear_in_both_windows(engine):
    development = {w.scenario for w in engine.schedule if w.first_day <= 519}
    holdout = {w.scenario for w in engine.schedule if w.first_day > 519}
    assert len(development) >= 6 and len(holdout) >= 5
    assert development & holdout, "the holdout shares no family with development"


@pytest.mark.spec("DATA:scenarios-in-both-windows")
def test_repeated_families_differ_between_windows(engine):
    """§15: the holdout must not be a replay of the development window."""
    for scenario in (Scenario.HIGH_VOLUME, Scenario.DELOAD, Scenario.TRAVEL):
        windows = engine.windows_for(scenario)
        assert len(windows) >= 2
        signatures = {(w.duration_days, w.modifiers) for w in windows}
        assert len(signatures) > 1, f"{scenario.value} is identical in both windows"


def test_most_days_are_ordinary_training(run):
    """Scenarios are episodes against a baseline, not the baseline itself."""
    ordinary = sum(1 for d in run.days if d.scenario_labels == (Scenario.ORDINARY.value,))
    assert 0.55 <= ordinary / len(run.days) <= 0.80


def test_every_scheduled_window_has_a_stated_intended_effect():
    for window in SCENARIO_SCHEDULE:
        assert len(window.intended_effect) > 40, (
            f"{window.scenario.value} has no meaningful stated effect"
        )


# --- documented effects (DATA.md §13) --------------------------------------

@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s1_high_volume_raises_fatigue_while_adaptation_continues(run):
    window = _window(Scenario.HIGH_VOLUME)
    block = run.days_in(window.first_day + 7, window.last_day)
    before = _ordinary_days(run, window.first_day - 12, span=12)

    assert _mean_local_fatigue(block) > _mean_local_fatigue(before) * 1.10
    assert st.mean(d.state_on_waking.systemic for d in block) > st.mean(
        d.state_on_waking.systemic for d in before
    )
    adaptation_start = run.days[window.first_day].state_on_waking.adaptation
    adaptation_end = run.days[window.last_day].state_on_waking.adaptation
    assert st.mean(adaptation_end.values()) > st.mean(adaptation_start.values()), (
        "adaptation must keep rising through an accumulation block"
    )


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s2_failure_heavy_costs_more_fatigue_than_its_volume_implies(run):
    """The disproportion is the point (``RESEARCH.md`` §9.1)."""
    window = _window(Scenario.FAILURE_HEAVY)
    block = run.days_in(window.first_day + 3, window.last_day + 2)
    before = _ordinary_days(run, window.first_day - 15, span=15)

    block_sets = sum(len(d.sets) for d in run.days_in(window.first_day, window.last_day))
    before_sets = sum(len(d.sets) for d in before)
    block_per_day = block_sets / window.duration_days
    before_per_day = before_sets / max(1, len(before))

    fatigue_ratio = _mean_local_fatigue(block) / _mean_local_fatigue(before)
    volume_ratio = block_per_day / before_per_day
    assert fatigue_ratio > volume_ratio, (
        f"fatigue rose {fatigue_ratio:.2f}x on {volume_ratio:.2f}x the volume; "
        f"failure work must cost more than its set count implies"
    )


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s2_sets_are_taken_closer_to_failure(run):
    window = _window(Scenario.FAILURE_HEAVY)
    block = [s for d in run.days_in(window.first_day, window.last_day) for s in d.sets]
    ordinary = [s for d in _ordinary_days(run, window.first_day - 20, 20) for s in d.sets]
    assert st.mean(s.true_rir for s in block) < st.mean(s.true_rir for s in ordinary)


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s3_deload_drops_fatigue_while_adaptation_persists(run):
    """The separation that makes deloads work."""
    window = _window(Scenario.DELOAD, 1)
    start_state = run.days[window.first_day].state_on_waking
    end_state = run.days[window.last_day].state_on_waking

    fatigue_start = st.mean(start_state.local_fatigue(m) for m in Muscle)
    fatigue_end = st.mean(end_state.local_fatigue(m) for m in Muscle)
    adaptation_start = st.mean(start_state.adaptation.values())
    adaptation_end = st.mean(end_state.adaptation.values())

    assert fatigue_end < fatigue_start * 0.75, (
        f"fatigue only fell to {fatigue_end / fatigue_start:.0%} across a deload"
    )
    assert adaptation_end > adaptation_start * 0.80, (
        f"adaptation fell to {adaptation_end / adaptation_start:.0%}; it should persist"
    )


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s3_deload_cuts_volume_within_the_documented_range(run):
    window = _window(Scenario.DELOAD, 1)
    block = run.days_in(window.first_day, window.last_day)
    before = _ordinary_days(run, window.first_day - 20, 20)
    block_sets = st.mean(len(d.sets) for d in block if d.sets)
    before_sets = st.mean(len(d.sets) for d in before if d.sets)
    reduction = 1 - block_sets / before_sets
    assert 0.30 <= reduction <= 0.70, f"deload cut volume by {reduction:.0%}"


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s4_sleep_restriction_shortens_sleep_and_slows_recovery(run):
    window = _window(Scenario.SLEEP_RESTRICTION)
    block = run.days_in(window.first_day, window.last_day)
    before = _ordinary_days(run, window.first_day - 20, 20)

    assert st.mean(d.latent.true_sleep_h for d in block) < 6.2
    assert st.mean(d.latent.recovery_propensity for d in block) < st.mean(
        d.latent.recovery_propensity for d in before
    )


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s5_chronic_compression_is_milder_than_acute_restriction(run):
    acute = run.days_in(*[_window(Scenario.SLEEP_RESTRICTION).first_day,
                          _window(Scenario.SLEEP_RESTRICTION).last_day])
    chronic = run.days_in(_window(Scenario.SLEEP_COMPRESSION).first_day,
                          _window(Scenario.SLEEP_COMPRESSION).last_day)
    assert st.mean(d.latent.true_sleep_h for d in chronic) > st.mean(
        d.latent.true_sleep_h for d in acute
    ), "compression must be milder than restriction"
    assert st.mean(d.latent.true_sleep_h for d in chronic) < 7.0
    assert len(chronic) > len(acute), "but it must last longer"


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s6_travel_raises_steps_without_being_a_training_session(run):
    window = _window(Scenario.TRAVEL)
    block = run.days_in(window.first_day, window.last_day)
    before = _ordinary_days(run, window.first_day - 20, 20)

    assert st.mean(d.wearable.steps for d in block) > 18000
    assert st.mean(d.wearable.steps for d in block) > 1.6 * st.mean(
        d.wearable.steps for d in before
    )
    # Steps are background activity, not resistance volume.
    assert st.mean(len(d.sets) for d in block) < st.mean(len(d.sets) for d in before) * 1.3


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s7_illness_moves_several_signals_together(run):
    """``DATA.md`` §13 S7: model confidence should see concordant signals."""
    window = _window(Scenario.ILLNESS)
    block = run.days_in(window.first_day, window.last_day)
    before = _ordinary_days(run, window.first_day - 25, 25)

    assert st.mean(d.wearable.temperature_deviation_c for d in block) > 0.4
    assert st.mean(d.wearable.resting_hr_bpm for d in block) > st.mean(
        d.wearable.resting_hr_bpm for d in before
    )
    assert st.mean(d.latent.true_sleep_h for d in block) < st.mean(
        d.latent.true_sleep_h for d in before
    )
    assert st.mean(d.latent.recovery_propensity for d in block) < st.mean(
        d.latent.recovery_propensity for d in before
    )


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s8_novelty_forces_substitutions(run):
    window = _window(Scenario.NOVELTY)
    block = run.days_in(window.first_day, window.last_day)
    assert window.modifiers.force_substitution
    assert any(d.sets for d in block), "the novelty block must contain training"


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s9_plateau_flattens_underlying_capacity(run):
    """The engine must not hallucinate continuous linear progression."""
    window = _window(Scenario.PLATEAU)
    modifiers = window.modifiers
    assert modifiers.adaptation_multiplier < 0.2, "plateau must suppress adaptation"

    plateau_days = run.days_in(window.first_day, window.last_day)
    assert len(plateau_days) >= 28, "a plateau needs to last long enough to detect"


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s10_pr_window_combines_low_fatigue_with_good_recovery(run):
    window = _window(Scenario.PR_WINDOW)
    block = run.days_in(window.first_day + 3, window.last_day)
    before = _ordinary_days(run, window.first_day - 20, 20)

    assert _mean_local_fatigue(block) < _mean_local_fatigue(before)
    assert st.mean(d.latent.recovery_propensity for d in block) > st.mean(
        d.latent.recovery_propensity for d in before
    )


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s11_bad_day_is_a_performance_shock_with_normal_recovery(run):
    """A conspicuous negative residual that the wearables do not explain."""
    window = _window(Scenario.BAD_DAY)
    day = run.days[window.first_day]
    assert day.sets, "the bad day must contain a session"

    shocks = [s.performance_shock for s in day.sets]
    assert max(shocks) < 0.97, f"session shock {max(shocks):.3f} is not a bad day"

    ordinary = _ordinary_days(run, window.first_day, 25)
    assert day.latent.recovery_propensity > 0.85 * st.mean(
        d.latent.recovery_propensity for d in ordinary
    ), "recovery context should look ordinary; the cause is unobservable"


@pytest.mark.spec("DATA:scenario-intended-effects")
def test_s12_missed_block_drops_fatigue_without_illness_signals(run):
    """The engine must tell absence of training from evidence of illness."""
    window = _window(Scenario.MISSED_BLOCK)
    block = run.days_in(window.first_day, window.last_day)
    before = _ordinary_days(run, window.first_day - 20, 20)

    assert all(not d.sets for d in block), "the missed block must contain no training"
    assert _mean_local_fatigue(block[-3:]) < _mean_local_fatigue(before) * 0.6

    # Nothing in the wearable data should suggest illness.
    assert st.mean(d.wearable.temperature_deviation_c for d in block) < 0.3
    assert st.mean(d.latent.recovery_propensity for d in block) > st.mean(
        d.latent.recovery_propensity for d in before
    ) * 0.95


# --- the manifest (DATA.md §6.3) -------------------------------------------

@pytest.mark.spec("DATA:manifest-is-simulator-only")
def test_manifest_records_every_window_with_its_intended_effect(engine):
    rows = engine.manifest_rows()
    assert len(rows) == len(engine.schedule)
    for row in rows:
        assert row["intended_effect"]
        assert row["window"] in ("development", "holdout")
        assert row["last_day"] >= row["first_day"]
    assert rows == sorted(rows, key=lambda r: r["first_day"])


@pytest.mark.spec("DATA:manifest-is-simulator-only")
@pytest.mark.guardrail(1)
def test_the_manifest_is_named_in_the_engines_forbidden_list():
    """``scenario_manifest`` is one of the markers Guardrail 1 scans for."""
    from rhome_core.architecture import _HIDDEN_MARKERS

    assert "scenario_manifest" in _HIDDEN_MARKERS


# --- composition and validation --------------------------------------------

def test_overlapping_scenarios_compose_rather_than_replace():
    combined = DayModifiers(volume_multiplier=1.3, rir_offset=-1.0).merged_with(
        DayModifiers(volume_multiplier=0.5, rir_offset=1.5, force_rest=True)
    )
    assert combined.volume_multiplier == pytest.approx(0.65)
    assert combined.rir_offset == pytest.approx(0.5)
    assert combined.force_rest


def test_a_day_with_no_scenario_is_unmodified(engine):
    assert engine.modifiers_for(5) == DayModifiers()
    assert engine.labels_for(5) == (Scenario.ORDINARY.value,)


def test_the_same_scenario_cannot_be_scheduled_over_overlapping_days():
    clash = (
        ScenarioWindow(Scenario.DELOAD, 10, 20, DayModifiers(), "a" * 50),
        ScenarioWindow(Scenario.DELOAD, 15, 25, DayModifiers(), "b" * 50),
    )
    with pytest.raises(ValueError, match="overlapping"):
        ScenarioEngine(clash)


def test_a_window_cannot_end_before_it_starts():
    with pytest.raises(ValueError, match="ends before"):
        ScenarioWindow(Scenario.DELOAD, 30, 10, DayModifiers(), "x" * 50)


# --- determinism -----------------------------------------------------------

@pytest.mark.guardrail(4)
def test_simulation_is_deterministic():
    first, second = simulate(5, n_days=120), simulate(5, n_days=120)
    assert [(d.day_index, len(d.sets), d.wearable.hrv_rmssd_ms) for d in first.days] == [
        (d.day_index, len(d.sets), d.wearable.hrv_rmssd_ms) for d in second.days
    ]
