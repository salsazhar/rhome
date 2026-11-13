"""Robustness under perturbation (``DATA.md`` §19.8, L3.7).

Six requirements, each measured by running the engine over the development
window twice — once with one thing changed — and comparing. A robustness claim
tested on a constructed toy is a claim about arithmetic; tested by perturbing a
real 520-day record it is a claim about the engine.
"""

from __future__ import annotations

import pytest

from rhome_core.muscles import Muscle
from rhome_eval.robustness import (
    LOWER,
    PerturbationDidNothing,
    bad_hrv_night,
    bad_session,
    compare_steps_to_a_session,
    first_day_with,
    first_day_with_wearables,
    high_step_days,
    run_perturbed,
    systematic_overperformance,
    upper_lower_parity,
    withhold_wearables,
)


@pytest.fixture(scope="module")
def days():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    return _days()


# --- the guard on the instrument ----------------------------------------------

def test_a_perturbation_that_changes_nothing_is_refused(days):
    """A perturbation that silently does nothing reports robustness.

    The bad-HRV test first targeted day 300, which is one of eight nights with
    no wearable data at all — so there was no HRV to halve, the runs were
    identical, and the result read as a perfect 0.000% shift at every horizon.
    """
    with pytest.raises(PerturbationDidNothing):
        run_perturbed(days, lambda day: day)


# --- §19.8, one requirement at a time -----------------------------------------

@pytest.mark.spec("DATA:robustness-suite")
def test_one_bad_hrv_night_does_not_dominate_state(days):
    target = first_day_with_wearables(days)
    run = run_perturbed(days, bad_hrv_night(target))

    assert run.perturbed_results[target].recovery.rho < run.clean_results[target].recovery.rho
    same_day = run.fatigue_shift(target)
    assert 0.0 < same_day < 0.08, f"{same_day:+.2%} on the day"
    assert abs(run.fatigue_shift(target + 14)) < 0.02
    assert abs(run.fatigue_shift(target + 60)) < 0.005


@pytest.mark.spec("DATA:robustness-suite")
def test_one_bad_session_does_not_permanently_depress_capacity(days):
    target = first_day_with(days, "bench_press", after=300)
    run = run_perturbed(days, bad_session(target, "bench_press"))

    immediate = run.capacity_shift_at("bench_press", target)
    assert -0.05 < immediate < -0.005, f"{immediate:+.2%} — the miss should register"

    later = run.capacity_shift_at("bench_press", min(target + 120, 519))
    assert abs(later) < abs(immediate) / 2, "the displacement must decay"
    assert abs(later) < 0.01


@pytest.mark.spec("DATA:robustness-suite")
def test_repeated_systematic_residuals_do_move_capacity(days):
    """Bounded influence must not mean frozen."""
    run = run_perturbed(days, systematic_overperformance(300, "bench_press", 1.10))

    early = run.capacity_shift_at("bench_press", 307)
    late = run.capacity_shift_at("bench_press", 500)
    assert early < 0.03, "one week should not deliver the whole shift"
    assert late > 0.08, f"a sustained 10% should be tracked; got {late:+.2%}"
    assert late < 0.12, "and not overshot"


@pytest.mark.spec("DATA:robustness-suite")
def test_missing_wearables_cost_confidence_rather_than_fabricating_fatigue(days):
    run = run_perturbed(days, withhold_wearables(300, 14))

    assert run.confidence_shift(307) < -0.2, "confidence must fall, and visibly"
    # The estimate moves toward neutral. For this athlete that means slightly
    # *less* fatigue, because their recovery context usually sits below one —
    # so the failure mode is fabricated freshness, not fabricated fatigue.
    shift = run.fatigue_shift(307)
    assert -0.15 < shift < 0.05, f"{shift:+.2%}"
    assert abs(run.fatigue_shift(340)) < 0.05, "and it must not persist past the gap"


@pytest.mark.spec("DATA:robustness-suite")
def test_high_step_counts_are_not_resistance_volume(days):
    """"Modestly" needs a reference, and it has to be commensurable.

    Comparing seven days of walking against one inserted session, as relative
    shifts on an already-elevated state, reported walking at 5.4× a squat
    session. Per day, from a clean state, against the same five sets:
    """
    comparison = compare_steps_to_a_session(days)
    assert comparison.amplitude > 1.0, "25,000 steps should be well above baseline"
    assert comparison.systemic_ratio < 0.35, (
        f"a day of heavy walking reads as {comparison.systemic_ratio:.2f} of a "
        f"hard squat session systemically"
    )
    assert comparison.local_ratio < 0.15, "and much less than that locally"
    assert comparison.steps_systemic > 0, "but not zero — walking does cost something"


@pytest.mark.spec("DATA:robustness-suite")
def test_high_steps_load_the_lower_body_and_not_the_upper(days):
    run = run_perturbed(days, high_step_days(300, 7))
    read = 306
    assert run.fatigue_shift(read, LOWER) > run.fatigue_shift(read) > 0
    assert abs(run.state_shift(read, "neuromuscular")) < 0.02, (
        "walking should barely touch neuromuscular strain"
    )


@pytest.mark.spec("DATA:robustness-suite")
def test_upper_lower_parity_is_stable_across_blocks(days):
    """Preserved, not equal to one.

    Lower-body muscles carry more fatigue per muscle because compound lifts
    load several at once; a ratio of 1.0 would mean the model had stopped
    telling a squat day from a bench day. A first version scored distance from
    1.0 with a ±0.5 tolerance and passed on every block while measuring
    nothing — the ratio sits near 0.69 and never approaches the bound.
    """
    run = run_perturbed(days, high_step_days(300, 7))
    parity = upper_lower_parity(run.clean_results)

    assert parity.blocks >= 15
    assert 0.4 < parity.median_ratio < 0.9
    assert parity.spread < 0.10, f"the ratio wanders: sd {parity.spread:.3f}"
    assert abs(parity.drift) < 0.05, (
        f"first half to second half drift of {parity.drift:+.3f} would mean "
        f"parity was not preserved across the record"
    )
    assert parity.max_deviation < 0.20
