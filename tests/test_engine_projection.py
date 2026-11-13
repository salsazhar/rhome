"""Forward projection and counterfactual sessions (``MODEL.tex`` §Projection).

The validation the build plan asks for is monotone decay under no training,
counterfactual sessions producing the expected change, and confidence widening
with the horizon. The tests below cover those and the three assumptions the
module makes, each of which could bias a forecast quietly.
"""

from __future__ import annotations

import pytest

from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_core.timeline import RecoveryTimeline, RecoveryWindow
from rhome_engine.confidence import Band
from rhome_engine.dose import LoggedSet
from rhome_engine.projection import (
    DEFAULT_HORIZONS_H,
    CounterfactualSet,
    project,
)
from rhome_engine.session import RhomeEngine
from rhome_engine.state import StateEngine

LIBRARY = load_library()


def _hard_set(number: int = 1) -> LoggedSet:
    return LoggedSet("cf", "bench_press", number, "working", load_kg=100.0, reps=5, rpe=9.0)


def _loaded(rho: float = 1.0) -> StateEngine:
    timeline = RecoveryTimeline()
    timeline.append(RecoveryWindow(0.0, rho))
    engine = StateEngine(timeline)
    for muscle in (Muscle.CHEST, Muscle.TRICEPS, Muscle.QUADS):
        engine.state.local_fatigue[muscle] = 1.0
    engine.state.neuromuscular = 0.8
    engine.state.systemic = 0.6
    engine.advance_to(24.0)
    return engine


@pytest.fixture(scope="module")
def window():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    engine = RhomeEngine(LIBRARY)
    engine.run(_days()[:520])
    return engine


# --- decay under no training -------------------------------------------------

@pytest.mark.spec("MODEL:projection-monotone-without-training")
def test_every_channel_decays_monotonically_with_no_training():
    engine = _loaded()
    projection = project(engine, LIBRARY, (0.0, 12.0, 24.0, 48.0, 72.0, 168.0, 336.0))

    for muscle in (Muscle.CHEST, Muscle.TRICEPS, Muscle.QUADS):
        series = [p.local_fatigue[muscle] for p in projection.points]
        assert series == sorted(series, reverse=True), muscle
    for attribute in ("neuromuscular", "systemic"):
        series = [getattr(p, attribute) for p in projection.points]
        assert series == sorted(series, reverse=True), attribute


def test_projection_agrees_with_simply_advancing_the_engine():
    """The property that makes a second decay implementation unnecessary.

    If these ever disagree, the projector has acquired arithmetic of its own.
    """
    engine = _loaded()
    projection = project(engine, LIBRARY, (72.0,))

    reference = engine.fork(RecoveryTimeline([RecoveryWindow(engine.state.t_h, 1.0)]))
    reference.advance_to(engine.state.t_h + 72.0)

    for muscle in Muscle:
        assert projection.at(72.0).local_fatigue[muscle] == pytest.approx(
            reference.state.local_fatigue[muscle], rel=1e-15, abs=1e-18
        )
    assert projection.at(72.0).neuromuscular == pytest.approx(
        reference.state.neuromuscular, rel=1e-15
    )


def test_a_projection_never_moves_the_present():
    engine = _loaded()
    before = engine.state.copy()

    project(engine, LIBRARY, (168.0,),
            counterfactual=(CounterfactualSet(_hard_set(), 24.0),))

    assert engine.state.t_h == before.t_h
    for muscle in Muscle:
        assert engine.state.local_fatigue[muscle] == before.local_fatigue[muscle]
    assert engine.state.neuromuscular == before.neuromuscular
    assert engine.state.rho_clock == before.rho_clock


# --- the assumptions ---------------------------------------------------------

@pytest.mark.spec("MODEL:projection-neutral-recovery")
def test_the_forecast_resets_the_recovery_context_to_neutral():
    """A poor night must not forecast a poor week.

    The timeline's last window extends indefinitely, so a projector that used
    it directly would carry one night's context across seven days.
    """
    poor = _loaded(rho=0.80)
    assert poor.timeline.rho_at(poor.state.t_h + 100.0) == pytest.approx(0.80)

    neutral = project(poor, LIBRARY, (72.0,))
    carried = project(poor, LIBRARY, (72.0,), assumed_rho=0.80)

    assert neutral.assumed_rho == 1.0
    assert neutral.at(72.0).neuromuscular < carried.at(72.0).neuromuscular, (
        "neutral recovery should clear fatigue faster than a suppressed context"
    )


def test_the_assumed_context_can_be_overridden_but_must_be_positive():
    engine = _loaded()
    assert project(engine, LIBRARY, (24.0,), assumed_rho=1.1).assumed_rho == 1.1
    with pytest.raises(ValueError):
        project(engine, LIBRARY, (24.0,), assumed_rho=0.0)
    with pytest.raises(ValueError):
        project(engine, LIBRARY, (-1.0,))


def test_a_projection_states_its_assumptions():
    engine = _loaded()
    resting = project(engine, LIBRARY, (72.0,)).assumptions()
    assert any("neutral" in line for line in resting)
    assert any("typical" in line for line in resting)
    assert any("no training" in line for line in resting)

    planned = project(
        engine, LIBRARY, (72.0,),
        counterfactual=(CounterfactualSet(_hard_set(), 24.0),),
    ).assumptions()
    assert any("1 proposed sets included" in line for line in planned)


def test_an_activity_window_still_running_is_carried_into_the_forecast():
    """Already-declared activity is not a future assumption; it is a fact."""
    timeline = RecoveryTimeline()
    timeline.append(RecoveryWindow(0.0, 1.0))
    walking = StateEngine(timeline)
    walking.set_activity_window(20000, 8000, 7.5)
    walking.advance_to(8.0)

    forecast = project(walking, LIBRARY, (0.0, 8.0))
    assert forecast.at(8.0).systemic > forecast.points[0].systemic, (
        "systemic load should still be accruing inside the declared window"
    )


# --- counterfactual sessions -------------------------------------------------

@pytest.mark.spec("MODEL:projection-counterfactual")
def test_a_proposed_session_raises_fatigue_in_the_muscles_it_trains():
    engine = _loaded()
    rest = project(engine, LIBRARY, (24.0, 72.0, 168.0))
    session = project(
        engine, LIBRARY, (24.0, 72.0, 168.0),
        counterfactual=tuple(CounterfactualSet(_hard_set(i + 1), 12.0) for i in range(5)),
    )

    for horizon in (24.0, 72.0, 168.0):
        assert session.at(horizon).local_fatigue[Muscle.CHEST] > rest.at(horizon).local_fatigue[
            Muscle.CHEST
        ]
        assert session.at(horizon).neuromuscular > rest.at(horizon).neuromuscular
    # An untrained muscle is unaffected.
    assert session.at(72.0).local_fatigue[Muscle.HAMSTRINGS] == pytest.approx(
        rest.at(72.0).local_fatigue[Muscle.HAMSTRINGS]
    )


def test_the_added_fatigue_decays_like_any_other():
    engine = _loaded()
    rest = project(engine, LIBRARY, (12.0, 42.0, 72.0))
    session = project(
        engine, LIBRARY, (12.0, 42.0, 72.0),
        counterfactual=(CounterfactualSet(_hard_set(), 12.0),),
    )
    deltas = [
        session.at(h).local_fatigue[Muscle.CHEST] - rest.at(h).local_fatigue[Muscle.CHEST]
        for h in (12.0, 42.0, 72.0)
    ]
    assert deltas[0] > deltas[1] > deltas[2] > 0
    half_life = 30.0
    assert deltas[1] / deltas[0] == pytest.approx(0.5 ** (30.0 / half_life), rel=0.02)


def test_a_session_before_the_first_horizon_is_included_in_all_of_them():
    engine = _loaded()
    projection = project(
        engine, LIBRARY, (48.0, 72.0),
        counterfactual=(CounterfactualSet(_hard_set(), 6.0),),
    )
    rest = project(engine, LIBRARY, (48.0, 72.0))
    assert projection.at(48.0).local_fatigue[Muscle.CHEST] > rest.at(48.0).local_fatigue[
        Muscle.CHEST
    ]


def test_a_counterfactual_set_cannot_be_placed_in_the_past():
    with pytest.raises(ValueError):
        CounterfactualSet(_hard_set(), -1.0)


def test_proposed_sets_are_applied_in_time_order_however_they_are_given():
    engine = _loaded()
    forwards = project(
        engine, LIBRARY, (72.0,),
        counterfactual=(
            CounterfactualSet(_hard_set(1), 6.0),
            CounterfactualSet(_hard_set(2), 30.0),
        ),
    )
    backwards = project(
        engine, LIBRARY, (72.0,),
        counterfactual=(
            CounterfactualSet(_hard_set(2), 30.0),
            CounterfactualSet(_hard_set(1), 6.0),
        ),
    )
    assert forwards.at(72.0).local_fatigue[Muscle.CHEST] == pytest.approx(
        backwards.at(72.0).local_fatigue[Muscle.CHEST]
    )


# --- confidence --------------------------------------------------------------

@pytest.mark.spec("MODEL:projection-confidence-widens")
def test_confidence_falls_as_the_horizon_extends(window):
    projection = window.project((0.0, 24.0, 72.0, 168.0, 336.0))
    values = [p.confidence.value for p in projection.points]

    assert values == sorted(values, reverse=True)
    assert values[0] > values[-1]
    # MODEL.tex: roughly 80% of current confidence at 72 h, 65% at 7 days.
    assert values[2] / values[0] == pytest.approx(0.80, abs=0.02)
    assert values[3] / values[0] == pytest.approx(0.65, abs=0.05)


def test_a_long_horizon_eventually_leaves_the_high_band(window):
    projection = window.project((0.0, 336.0))
    assert projection.points[0].confidence.band is not Band.LIMITED
    assert projection.points[-1].confidence.band is Band.LIMITED


def test_the_default_horizons_are_the_ones_the_product_asks_for():
    assert 72.0 in DEFAULT_HORIZONS_H
    assert 168.0 in DEFAULT_HORIZONS_H


def test_projecting_from_the_engine_reports_a_recognisable_present(window):
    projection = window.project((0.0, 72.0))
    for muscle in Muscle:
        assert projection.origin.local_fatigue[muscle] == pytest.approx(
            window.state_engine.state.local_fatigue[muscle]
        )
    assert projection.at(72.0).total_local_fatigue < projection.origin.total_local_fatigue
