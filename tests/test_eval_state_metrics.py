"""State reconstruction scoring (``DATA.md`` §19.1, L3.2).

Two things are being tested: that the metrics compute what the section asks
for, and — following D20 — that each one is capable of failing. A metric whose
score is fixed by the shape of the data rather than by the model's skill is
worse than no metric, because it reports success either way.
"""

from __future__ import annotations

import pytest

from rhome_core.muscles import Muscle
from rhome_eval.run import CHANNELS, evaluate
from rhome_eval.state_metrics import (
    CROSSING_FRACTION,
    TIMING_WINDOW_DAYS,
    _high_load_days,
    _peak_and_crossing,
    score_states,
)
from rhome_eval.window import Window


@pytest.fixture(scope="module")
def days():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    return _days()


@pytest.fixture(scope="module")
def report(days):
    return score_states(evaluate(days, Window.DEVELOPMENT), days)


# --- the five measures §19.1 asks for ---------------------------------------

@pytest.mark.spec("DATA:state-reconstruction-scored")
def test_every_channel_is_scored_on_all_five_measures(report):
    assert {c.channel for c in report.channels} == set(CHANNELS)
    for score in report.channels:
        assert score.pearson is not None
        assert score.spearman is not None
        assert score.rmse is not None
        assert score.directional_accuracy is not None
        assert score.baseline_pearson is not None
    assert {t.channel for t in report.timing} == set(CHANNELS)


@pytest.mark.spec("DATA:state-reconstruction-scored")
def test_the_aggregate_channels_track_truth_but_barely_beat_a_counter(report):
    """Both halves of this matter, and reporting only the first misleads."""
    for score in report.channels:
        assert score.pearson > 0.90, f"{score.channel}: {score.pearson:+.3f}"
        assert score.directional_accuracy > 0.85
        assert score.advantage < 0.15, (
            f"{score.channel}: the engine leads a set counter by only "
            f"{score.advantage:+.3f}"
        )


@pytest.mark.spec("DATA:state-reconstruction-scored")
def test_per_muscle_is_where_the_engine_separates_from_a_counter(report):
    assert report.muscle_mean > 0.90
    assert report.muscle_baseline_mean < 0.70
    assert report.muscle_mean - report.muscle_baseline_mean > 0.30
    assert len(report.muscles) == len(list(Muscle))
    assert report.worst_muscle.pearson > 0.85


def test_rmse_uses_the_frozen_alignment(days):
    """Without it, RMSE measures the difference between two unit systems."""
    run = evaluate(days, Window.DEVELOPMENT)
    report = score_states(run, days)
    for score in report.channels:
        naive = [
            abs(a - b)
            for a, b in zip(run.estimated(score.channel), run.truth.channel(score.channel))
        ]
        assert score.rmse < sum(naive) / len(naive) * 3, (
            f"{score.channel}: aligned RMSE should be far smaller than the "
            f"unaligned difference between two arbitrary unit systems"
        )


# --- timing ------------------------------------------------------------------

@pytest.mark.spec("DATA:state-reconstruction-scored")
def test_peak_timing_is_measured_over_a_real_spread_not_a_fixed_answer(report):
    """The vacuous-metric check.

    If every session peaked on its own day in both series, peak error would be
    zero by construction and the metric would report success regardless of the
    model. Peaks in fact land across the whole window, because a second session
    inside it moves them.
    """
    for score in report.timing:
        assert score.sessions > 50
        assert len(set(score.peak_errors)) > 3, (
            f"{score.channel}: peak errors take only "
            f"{len(set(score.peak_errors))} distinct values; the metric may be "
            f"fixed by the data rather than measuring the model"
        )
        assert score.peak_within_a_day > 0.75


def test_timing_metrics_need_no_scale_alignment():
    """A peak is an index and a crossing is a fraction of a series' own peak."""
    series = [1.0, 5.0, 3.0, 2.0, 1.0, 0.5]
    scaled = [v * 1000.0 for v in series]
    assert _peak_and_crossing(series, 0) == _peak_and_crossing(scaled, 0)


def test_a_crossing_is_reported_only_when_it_happens():
    """Never falling below half is worth reporting, not papering over."""
    falls = [10.0, 8.0, 6.0, 4.0, 3.0, 2.0]
    assert _peak_and_crossing(falls, 0) == (0, 3)

    plateau = [10.0, 9.5, 9.4, 9.3, 9.2, 9.1]
    peak, crossing = _peak_and_crossing(plateau, 0)
    assert peak == 0 and crossing is None


def test_the_crossing_threshold_is_the_documented_one():
    assert CROSSING_FRACTION == 0.5
    assert TIMING_WINDOW_DAYS == 6


def test_high_load_days_are_chosen_from_the_observable_log(days):
    """Which sessions count as heavy must not be a judgement made with the
    answers in hand."""
    window_days = [d for d in days if d.day_index in Window.DEVELOPMENT.days]
    heavy = _high_load_days(window_days)
    assert 50 < len(heavy) < len(window_days) // 2
    for index in heavy:
        assert any(
            s.set_type in ("working", "backoff") for s in window_days[index].sets
        )


def test_the_counter_can_attempt_timing_and_is_beaten_on_strain(report):
    """A single accumulator has a series, so it can guess when a peak fell.

    It does respectably on local fatigue and systemic load, where the peak is
    simply the biggest session in the window. It collapses on neuromuscular
    strain, which depends on relative intensity — something a set count has no
    access to.
    """
    by_channel = {t.channel: t for t in report.timing}
    strain = by_channel["neuromuscular"]
    assert strain.baseline_peak_within_a_day is not None
    assert strain.peak_within_a_day - strain.baseline_peak_within_a_day > 0.25


# --- the open item from Checkpoint 2 -----------------------------------------

@pytest.mark.spec("DATA:state-reconstruction-scored")
def test_the_recovery_multiplier_clipping_is_measured(report):
    """Checkpoint 2 left this as a question; it is now a reported number."""
    assert 0.0 < report.rho_clipped_fraction < 0.20
    assert report.rho_longest_clipped_run >= 1
    assert report.rho_longest_clipped_run < 14, (
        "a fortnight pinned to a bound would mean the multiplier had stopped "
        "carrying information for a whole training block"
    )


def test_the_report_carries_the_window_caveat(report):
    assert "development" in report.caveat
    assert report.notes


def test_scoring_refuses_a_run_with_no_truth_attached(days):
    from rhome_eval.run import run_engine

    with pytest.raises(ValueError, match="no truth attached"):
        score_states(run_engine(days, Window.DEVELOPMENT), days)
