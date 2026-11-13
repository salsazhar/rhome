"""Ranking tests (``DATA.md`` §19.3, L3.4).

Six orderings a user would notice being wrong. Each is a matched pair pushed
through the engine and, separately, through the simulator's own physiology,
so a disagreement can be attributed: to the engine, or to a specification
asking for something neither model produces.
"""

from __future__ import annotations

import pytest

from rhome_eval.ranking import CASES, deload_response, run_rankings
from rhome_eval.run import evaluate
from rhome_eval.window import Window


@pytest.fixture(scope="module")
def results():
    return run_rankings()


@pytest.fixture(scope="module")
def rebound():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    return deload_response(evaluate(_days(), Window.DEVELOPMENT))


@pytest.mark.spec("DATA:ranking-orderings")
def test_all_five_constructed_orderings_hold(results):
    assert len(results) == len(CASES) == 5
    for result in results:
        assert result.engine_correct, f"{result.case.name}: {result.case.requirement}"


@pytest.mark.spec("DATA:ranking-orderings")
def test_the_simulator_produces_the_same_orderings(results):
    """If it did not, the specification would be asking for something neither
    model does — which is a finding about the specification, not the engine."""
    for result in results:
        assert result.truth_correct, (
            f"{result.case.name}: the simulator does not produce this ordering "
            f"either, so the requirement is wrong rather than unmet"
        )


@pytest.mark.spec("DATA:ranking-orderings")
def test_post_deload_performance_exceeds_pre_deload(rebound):
    """The sixth case, which cannot be constructed from a matched pair.

    Suppression is monotone in fatigue by definition, so a hand-built
    low-fatigue state would out-project a high-fatigue one whatever the engine
    did. Measured from the run instead, comparing the last session before each
    deload against the first after it.
    """
    assert rebound.episodes > 20
    assert rebound.engine_correct is True
    assert rebound.truth_correct is True
    assert rebound.engine_agreements / rebound.episodes > 0.6


def test_curvature_moves_contrasts_toward_truth_without_worsening_any(results, rebound):
    """L5.3's frozen-baseline criterion, including harmless overshoot."""
    ratios = [r.engine_margin / r.truth_margin for r in results]
    ratios.append(rebound.engine_gain / rebound.truth_gain)
    frozen_v0 = (0.576, 0.788, 0.764, 0.688, 0.681, 0.564)

    assert all(
        abs(current - 1.0) <= abs(frozen - 1.0) + 0.001
        for current, frozen in zip(ratios, frozen_v0)
    ), (ratios, frozen_v0)
    assert abs(ratios[1] - 1.0) < abs(frozen_v0[1] - 1.0)
    assert abs(ratios[4] - 1.0) < abs(frozen_v0[4] - 1.0)
    assert abs(ratios[5] - 1.0) < abs(frozen_v0[5] - 1.0)


def test_the_failure_case_is_matched_on_volume(results):
    """Otherwise the ordering could be explained by set count alone."""
    by_name = {r.case.name: r for r in results}
    case = by_name["failure vs matched-volume non-failure"].case
    assert case.volume_matched
    assert case.higher.total_sets == case.lower.total_sets


def test_each_case_states_the_requirement_it_comes_from():
    for case in CASES:
        assert case.requirement
        assert case.channel in ("local_fatigue", "neuromuscular", "systemic")
        assert case.higher.sets and case.lower.sets
