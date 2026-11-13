"""Per-muscle reconstruction against a competent competitor (L3.17, D23).

`DATA.md` §19.1 now requires two things the project did not have: a
cross-sectional score between muscles within a day, and a trivial competitor
that shares the authored muscle map.

The reason is a measured failure. The per-muscle claim ran for two stages as
"+0.966 engine against +0.520 counter". That counter was one global
accumulator with no attribution, compared against each muscle in turn — so the
0.446 gap was measuring the absence of a lookup table. Hand a counter the
`c^F` column out of the library and it reaches +0.955 longitudinally and
+0.934 cross-sectionally, leaving an advantage of +0.010.

These tests hold the competitor honest in both directions: it must be strong
enough to be informative, and weak enough to still be trivial.
"""

from __future__ import annotations

import statistics as st

import pytest

from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_eval.run import LATENT_OFFSET_DAYS, evaluate
from rhome_eval.state_baselines import MUSCLE_BASELINES, MuscleBaseline
from rhome_eval.state_metrics import score_states
from rhome_eval.window import Window

from test_session_driver import DATASET, _days

pytestmark = pytest.mark.skipif(
    not (DATASET / "observable" / "sets.csv").exists(), reason="dataset not generated"
)


@pytest.fixture(scope="module")
def report():
    days = _days()
    return score_states(evaluate(days, Window.DEVELOPMENT), days)


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_the_attributed_counter_carries_no_inferred_information():
    """It may have the map. It may not have anything the engine works out.

    This is the D23 line, and it is checked by construction rather than by
    reading the docstring: the weight function is handed an exercise and
    nothing else — no set, no repetitions, no effort, no history — so there is
    nowhere for inferred information to enter.
    """
    library = load_library()
    exercise = next(iter(library.exercises.values()))

    for baseline in MUSCLE_BASELINES:
        weights = baseline.weights(exercise)
        assert weights, f"{baseline.name} produced no weights"
        assert set(weights) <= set(Muscle)
        # Identical for every performance of the exercise: no state, no effort.
        assert baseline.weights(exercise) == weights


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_the_attributed_counter_beats_the_unattributed_one_by_a_lot(report):
    """If it did not, D23 would be pedantry rather than a correction."""
    unattributed = report.muscle_baseline_mean
    attributed = report.muscle_attributed_baseline_mean

    assert unattributed == pytest.approx(0.520, abs=0.01), (
        "the historical +0.520 figure should still reproduce"
    )
    assert attributed > unattributed + 0.3, (
        f"attributed counter {attributed:+.3f} vs unattributed {unattributed:+.3f}; "
        "the whole point of D23 is that the map does most of the work"
    )


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_the_engine_is_reported_against_the_attributed_counter(report):
    """The advantage that gets quoted must be the one against a real competitor."""
    for score in report.muscles:
        assert score.attributed_baselines, f"{score.muscle.value} has no attributed competitor"
        assert score.attributed_advantage is not None

    advantage = report.muscle_mean - report.muscle_attributed_baseline_mean
    assert advantage < 0.1, (
        f"engine advantage over an attributed counter is {advantage:+.3f}; if this "
        "ever grows past 0.1 the finding has changed and the record must say so"
    )


@pytest.mark.spec("DATA:cross-sectional-muscle-reconstruction")
def test_the_cross_sectional_score_exists_and_is_not_the_longitudinal_one(report):
    """It was quoted at +0.941 in three build-log entries before any code
    computed it. This is that code, and it must not silently be a rename."""
    assert report.cross_sectional, "no cross-sectional scores produced"

    engine = report.engine_cross_sectional
    assert engine is not None
    assert engine.pooled == pytest.approx(0.941, abs=0.01), (
        f"cross-sectional pooled r is {engine.pooled:+.4f}; the figure carried "
        "in the diagnostic and three build-log entries is +0.941"
    )
    assert engine.pooled != pytest.approx(report.muscle_mean, abs=1e-6), (
        "cross-sectional and longitudinal scores are identical, which means the "
        "day means are not actually being removed"
    )


@pytest.mark.spec("DATA:cross-sectional-muscle-reconstruction")
def test_removing_day_means_is_what_makes_it_cross_sectional(report):
    """A predictor with no between-muscle information must score ~0 here.

    The guard against the metric being free: give every muscle the same series
    and the day-centred vector is identically zero, so no correlation can be
    formed. The unattributed counter is exactly that predictor, which is why
    it cannot appear in this table at all.
    """
    names = {score.name for score in report.cross_sectional}
    assert "engine" in names
    assert any("c_F" in name for name in names)

    flat = MuscleBaseline("flat", lambda ex: {muscle: 1.0 for muscle in Muscle})
    days = [d for d in _days() if d.day_index in Window.DEVELOPMENT.days]
    series = flat.series(days, load_library())

    for index in range(0, len(next(iter(series.values()))), 50):
        values = [series[muscle][index] for muscle in Muscle]
        assert st.pstdev(values) == pytest.approx(0.0, abs=1e-9), (
            "a predictor that treats every muscle alike must have zero "
            "between-muscle spread, or this metric is measuring something else"
        )


@pytest.mark.spec("DATA:cross-sectional-muscle-reconstruction")
def test_the_cross_sectional_series_pair_with_truth_the_same_way(report):
    """The 1-day offset is the error that cost +0.941 once already.

    Computed without it by hand during L3.17, the cross-sectional figure read
    +0.279. Reproducing the published number is what caught it, so the pairing
    is asserted rather than assumed.
    """
    engine = report.engine_cross_sectional
    assert LATENT_OFFSET_DAYS == 1
    assert engine.days > 500, "too few paired days for the development window"
    assert engine.per_day_mean is not None
    assert engine.pooled > 0.9 > engine.per_day_mean - 0.05


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_neuromuscular_timing_does_not_survive_an_authored_competitor(report):
    """The claim most expected to survive the re-audit, measured not assumed.

    L3.2 argued the counter "collapses" on neuromuscular timing — 44.6%
    against the engine's 81.5% — because strain depends on relative intensity,
    which a set counter has no access to. Give the counter the library's
    compoundness column and the published intensity curve, both authored data,
    and it reaches 88.5%. The 44.6% measured a missing column, not a hard
    problem.
    """
    timing = {score.channel: score for score in report.timing}
    neuromuscular = timing["neuromuscular"]

    assert neuromuscular.baseline_peak_within_a_day == pytest.approx(0.446, abs=0.02), (
        "the historical 44.6% for the unattributed counter should still reproduce"
    )
    assert neuromuscular.authored_peak_within_a_day > neuromuscular.peak_within_a_day, (
        f"engine {neuromuscular.peak_within_a_day:.1%} vs authored counter "
        f"{neuromuscular.authored_peak_within_a_day:.1%}; if the engine ever "
        "leads here, LIM-40's conclusion has changed and the record must say so"
    )


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_every_timing_channel_reports_the_authored_competitor(report):
    for score in report.timing:
        assert score.authored_peak_within_a_day is not None, (
            f"{score.channel} timing has no authored competitor beside it"
        )
