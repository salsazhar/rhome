"""Simulator-centred Grade-C calibration references (DATA.md §19.4)."""

from __future__ import annotations

import pytest

from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_eval.calibration import CASES, READ_AFTER_H, run_calibration
from rhome_eval.run import evaluate
from rhome_eval.window import Window


@pytest.fixture(scope="module")
def results():
    return run_calibration()


@pytest.mark.spec("DATA:calibration-bands")
def test_the_simulator_lands_inside_the_versioned_reference_bands(results):
    assert all(result.simulator_in_band for result in results), [
        result.case.name for result in results if not result.simulator_in_band
    ]


@pytest.mark.spec("DATA:calibration-bands")
def test_the_engine_gap_is_reported_instead_of_fitted_away(results):
    assert sum(result.in_band for result in results) == 2
    for result in results[2:]:
        assert result.engine_lower_body < result.simulator_lower_body


@pytest.mark.spec("DATA:calibration-bands")
def test_suppression_rises_monotonically_with_accumulation(results):
    """Fresh < one session < a week < a block < an overload peak."""
    ordered = [r.engine_lower_body for r in results]
    fresh, single, failure_single, week, block, overload = ordered
    assert fresh < single < week < block < overload
    assert single < failure_single, "a failure session must cost more than an ordinary one"


@pytest.mark.spec("DATA:calibration-bands")
def test_upper_body_suppression_runs_below_lower_body(results):
    """§19.4 calls this a correct prediction, not a calibration error."""
    for result in results[1:]:
        assert result.upper_body_gap > 0, (
            f"{result.case.name}: upper body should suppress less than lower"
        )
    ordinary = results[1]
    assert 0.5 < ordinary.upper_body_gap < 3.0, (
        f"the documented expectation is roughly one percentage point; "
        f"got {ordinary.upper_body_gap:.1f}pp"
    )


@pytest.mark.spec("DATA:calibration-bands")
def test_the_numerical_stability_clip_never_binds_in_ordinary_training():
    """§19.4: if it binds during ordinary training, that is a defect."""
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")

    run = evaluate(_days(), Window.DEVELOPMENT)
    clip = ENGINE_PARAMETERS.value("suppression_clip")
    bound = [
        (result.day_index, exercise_id)
        for result in run.results
        for exercise_id, record in result.projections.items()
        if sum(record.terms.values()) >= clip - 1e-12
    ]
    assert not bound, f"the clip bound on {len(bound)} projections: {bound[:5]}"


def test_the_simulator_suppresses_at_least_as_much_as_the_engine(results):
    """The same compression the ranking tests found, on a different measure.

    The simulator's suppression is b/(1+b) with larger λ and unclipped; the
    engine's is 1−exp(−b) with smaller λ and a clip. Both rise with
    accumulation and the engine rises less, which is the misspecification
    showing rather than a calibration error.
    """
    for result in results[1:]:
        assert result.simulator_lower_body >= result.engine_lower_body * 0.95
    peak = results[-1]
    assert peak.simulator_lower_body > peak.engine_lower_body * 1.3


def test_the_bands_are_read_a_day_after_the_last_session():
    assert READ_AFTER_H == 24.0
    for case in CASES:
        assert case.protocol.events
        assert min(age for age, *_ in case.protocol.events) >= 24.0, (
            f"{case.name}: the most recent event must be at least a day old"
        )


def test_every_case_states_a_band_from_the_document():
    assert len(CASES) == 6
    for case in CASES:
        assert 0.0 <= case.lower_bound < case.upper_bound <= 0.30
