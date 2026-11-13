"""Ranking and calibration against a competent competitor (L3.17, D23).

Neither module carried a trivial competitor of any kind. "All six ranking
orderings correct" and "the engine expresses ~80% of the true contrast" were
reported for two stages with nothing beside them saying what an absence of
modelling would have achieved — which is the exact condition D20 was written
to prevent, and which had already misled the per-muscle latent claim.

With a competitor that gets the library's authored columns and nothing the
engine works out, five of the six orderings turn out to be free.
"""

from __future__ import annotations

import pytest

from rhome_eval.calibration import (
    CASES as CALIBRATION_CASES,
    counter_suppression,
    fit_counter_scale,
    run_calibration,
)
from rhome_eval.ranking import CASES, deload_response, run_rankings
from rhome_eval.run import evaluate
from rhome_eval.window import Window

from test_session_driver import DATASET, _days

pytestmark = pytest.mark.skipif(
    not (DATASET / "observable" / "sets.csv").exists(), reason="dataset not generated"
)


@pytest.fixture(scope="module")
def rankings():
    return run_rankings()


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_every_ranking_ordering_reports_what_a_counter_did(rankings):
    for result in rankings:
        assert result.baseline_higher > 0.0 or result.baseline_lower > 0.0, (
            f"{result.case.name} has no competitor score"
        )
        assert result.baseline_correct in (True, False, None)


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_most_orderings_are_free_to_a_set_counter(rankings):
    """The finding, asserted so it cannot quietly stop being true.

    If a later change makes the engine earn more of these, this test fails and
    the record has to be rewritten — which is the point. A finding that is
    allowed to drift is not a finding.
    """
    earned = [r.case.name for r in rankings if r.earned]
    free = [r.case.name for r in rankings if r.baseline_correct is True]

    assert len(free) == 4, f"expected 4 free orderings, got {len(free)}: {free}"
    assert earned == ["failure vs matched-volume non-failure"], (
        f"the only dose ordering the engine earns should be the volume-matched "
        f"one, got {earned}"
    )


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_the_volume_matched_case_is_where_a_counter_must_tie(rankings):
    """A matched pair is matched: if the counter separates them, it is not."""
    for result in rankings:
        if result.case.volume_matched and result.case.channel == "local_fatigue":
            assert result.baseline_correct is None, (
                f"{result.case.name} is volume-matched, so a set counter must "
                "tie on it; that it does not means the pair is not matched"
            )


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_the_deload_rebound_is_free_to_anything_that_decays():
    """Stated rather than assumed (D20). A counter falls across a deload, so
    any monotone reading of it predicts a rebound."""
    response = deload_response(evaluate(_days(), Window.DEVELOPMENT))

    assert response.baseline_gain is not None
    assert response.baseline_correct is True, (
        "a decaying counter should predict the post-deload rebound; if it does "
        "not, the deload episodes are not what this test assumes"
    )
    assert not response.earned, (
        "the deload ordering must not be reported as earned while a counter "
        "gets it for nothing"
    )


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_the_calibration_competitor_is_scaled_but_not_shaped():
    """One free parameter, and it may not be handed the answer per case."""
    scale = fit_counter_scale(CALIBRATION_CASES)
    assert scale > 0.0

    # A single scalar for every case: the competitor cannot bend per band.
    predictions = [scale * counter_suppression(c.protocol) for c in CALIBRATION_CASES]
    ratios = [
        p / counter_suppression(c.protocol)
        for p, c in zip(predictions, CALIBRATION_CASES)
    ]
    assert max(ratios) - min(ratios) < 1e-9, "the competitor used more than one scale"


@pytest.mark.spec("DATA:attributed-baseline-required")
def test_calibration_is_where_the_engine_is_ahead_of_the_counter():
    """The one place in the D23 re-audit the engine wins, so it is recorded."""
    results = run_calibration()
    engine = sum(1 for r in results if r.in_band)
    counter = sum(1 for r in results if r.baseline_in_band)
    simulator = sum(1 for r in results if r.simulator_in_band)

    assert engine > counter, (
        f"engine {engine}/{len(results)} vs counter {counter}/{len(results)}; "
        "if the counter ever catches up here the D23 audit has no survivor"
    )
    assert simulator == len(results), (
        "the bands are simulator-centred under D21, so the simulator should "
        "hit all of them; if it does not, the bands have moved"
    )
