"""The explanation trace (``MODEL.tex`` §Explanation trace, ``DATA.md`` §19.6).

Because the trace is an exact decomposition rather than a narrative, every
criterion in §19.6 is arithmetic and can be checked exactly. The two that are
not — that no driver string is emitted which is not derivable from the trace,
and that none crosses the claim boundaries of ``RESEARCH.md`` §17 — are
enforced here rather than by review, which is what the specification requires.
"""

from __future__ import annotations

import math

import pytest

from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_core.timeline import RecoveryTimeline, RecoveryWindow
from rhome_engine.dose import SetDose
from rhome_engine.ledger import Channel, ContributionLedger
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.recovery import RecoveryContext
from rhome_engine.session import RhomeEngine
from rhome_engine.state import StateEngine
from rhome_engine.trace import (
    ClaimBoundaryError,
    TraceBuilder,
    check_claim_boundaries,
    display_value,
)

LIBRARY = load_library()
BENCH = LIBRARY["bench_press"]


def _ledger() -> ContributionLedger:
    return ContributionLedger(
        {
            Channel.LOCAL_FATIGUE: ENGINE_PARAMETERS.value("local_half_life_h"),
            Channel.NEUROMUSCULAR: ENGINE_PARAMETERS.value("neuromuscular_half_life_h"),
            Channel.SYSTEMIC: ENGINE_PARAMETERS.value("systemic_half_life_h"),
        },
        ENGINE_PARAMETERS.value("adaptation_time_constant_days") * 24.0,
    )


def _engine(rho: float = 1.0):
    timeline = RecoveryTimeline()
    timeline.append(RecoveryWindow(0.0, rho))
    ledger = _ledger()
    return StateEngine(timeline, ledger=ledger), ledger


def _dose(fatigue: float = 0.5) -> SetDose:
    return SetDose(
        local_fatigue={Muscle.CHEST: fatigue},
        stimulus={Muscle.CHEST: 1.0},
        neuromuscular=0.2,
        systemic=0.3,
    )


@pytest.fixture(scope="module")
def window():
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")
    engine = RhomeEngine(LIBRARY)
    return engine, engine.run(_days()[:520])


# --- exactness (DATA.md §19.6, first two criteria) ---------------------------

@pytest.mark.spec("DATA:trace-decomposition-exact")
def test_contributor_shares_sum_to_one(window):
    _, results = window
    worst = 0.0
    counted = 0
    for result in results:
        for record in result.traces.values():
            counted += 1
            worst = max(worst, abs(record.share_total() - 1.0))
    assert counted > 5000, f"only {counted} traces examined"
    assert worst < 1e-9, f"worst share error {worst:.3e}"


@pytest.mark.spec("DATA:trace-decomposition-exact")
def test_a_state_rebuilds_from_the_contributors_it_lists(window):
    """If this fails, the explanation describes a number the engine never made."""
    _, results = window
    worst = 0.0
    for result in results:
        for record in result.traces.values():
            worst = max(worst, abs(record.reconstruct() - record.value) / max(record.value, 1e-12))
    assert worst < 1e-9, f"worst relative reconstruction error {worst:.3e}"


def test_background_activity_appears_as_a_contributor():
    """Steps enter as a rate, not an impulse, and were the easiest thing to lose.

    A ledger recording only sets finds its shares summing to less than one on
    any day the athlete walked — silently, and only on those days.
    """
    engine, ledger = _engine()
    engine.set_activity_window(16000, 8000, 7.5)
    engine.apply_dose(_dose(), 17.0, "bench_press", "set:1", "Bench, set 1")
    engine.advance_to(23.0)

    total = engine.state.systemic
    contributions = ledger.contributions(
        Channel.SYSTEMIC, "", total, engine.state.t_h, engine.state.rho_clock
    )
    labels = {c.label for c in contributions}
    assert "daily activity" in labels
    assert sum(c.share for c in contributions) == pytest.approx(1.0, abs=1e-9)


def test_folding_old_impulses_preserves_the_sum():
    """Pruning would break sum-to-one; folding does not."""
    engine, ledger = _engine()
    for day in range(60):
        engine.apply_dose(_dose(0.4), day * 24.0 + 17.0, "bench_press", f"set:{day}", f"Set {day}")
    engine.advance_to(60 * 24.0 + 23.0)

    before = ledger.size()
    ledger.fold_old(engine.state.t_h, engine.state.rho_clock)
    after = ledger.size()
    assert after < before, "nothing was folded, so the test proves nothing"

    total = engine.state.local_fatigue[Muscle.CHEST]
    contributions = ledger.contributions(
        Channel.LOCAL_FATIGUE, "chest", total, engine.state.t_h, engine.state.rho_clock
    )
    assert sum(c.share for c in contributions) == pytest.approx(1.0, abs=1e-9)
    assert any(c.is_residual for c in contributions)


def test_the_ledger_prices_survival_from_the_state_engine_clock():
    """The property that stops the trace drifting from the state.

    Under a recovery multiplier below one, decay is slower. A ledger with its
    own notion of elapsed time would not know that, and would agree with the
    state only while rho stayed at one.
    """
    fast, fast_ledger = _engine(rho=1.0)
    slow, slow_ledger = _engine(rho=0.8)
    for engine in (fast, slow):
        engine.apply_dose(_dose(), 0.0, "bench_press", "set:1", "Bench, set 1")
        engine.advance_to(48.0)

    for engine, ledger in ((fast, fast_ledger), (slow, slow_ledger)):
        total = engine.state.local_fatigue[Muscle.CHEST]
        contribution = ledger.contributions(
            Channel.LOCAL_FATIGUE, "chest", total, engine.state.t_h, engine.state.rho_clock
        )[0]
        assert contribution.surviving == pytest.approx(total, rel=1e-12)

    assert slow.state.local_fatigue[Muscle.CHEST] > fast.state.local_fatigue[Muscle.CHEST]


# --- the parameter block (DATA.md §19.6, third criterion) --------------------

@pytest.mark.spec("DATA:trace-parameters-declared")
def test_every_parameter_in_the_block_carries_an_evidence_grade(window):
    _, results = window
    record = next(iter(results[-1].traces.values()))
    assert record.parameters
    for parameter in record.parameters:
        assert parameter.grade in ("A", "B", "C")
        assert parameter.version_id.count("@") == 1
        assert parameter.document and parameter.section


@pytest.mark.spec("DATA:trace-parameters-declared")
def test_the_parameter_block_is_read_from_the_code_not_declared_by_hand():
    """A hand-kept list is the thing that stays at its first value."""
    from rhome_engine.trace import _parameters_read_by

    dose_parameters = _parameters_read_by("dose")
    assert "local_fatigue_scale" in dose_parameters
    assert "neuromuscular_scale" in dose_parameters
    assert "systemic_scale" in dose_parameters
    # The contribution coefficients were inline literals until L2.7, so they
    # could not appear here however carefully anyone maintained a list.
    assert "stimulus_secondary_coeff" in _parameters_read_by("core:exercises")


def test_the_block_discloses_how_much_rests_on_engineering_priors(window):
    _, results = window
    record = next(iter(results[-1].traces.values()))
    grades = record.grades()
    assert sum(grades.values()) == len(record.parameters)
    assert grades["C"] > 0, "the disclosure is the point; there are Grade C priors here"


# --- driver strings (DATA.md §19.6, last two criteria) -----------------------

@pytest.mark.spec("RESEARCH:claim-boundaries-enforced")
@pytest.mark.parametrize(
    "forbidden",
    [
        "Your CNS is 72% fatigued.",
        "Your chest is exactly 64% recovered biologically.",
        "An HRV of 42 means you should not train.",
        "Your ACWR is 1.4, therefore injury risk is high.",
        "You are overtrained.",
        "Your wearable proves you are ill.",
        "Take today off.",
    ],
)
def test_the_forbidden_examples_are_rejected(forbidden):
    """The six examples are lifted verbatim from ``RESEARCH.md`` §17."""
    with pytest.raises(ClaimBoundaryError):
        check_claim_boundaries(forbidden)


@pytest.mark.spec("RESEARCH:claim-boundaries-enforced")
@pytest.mark.parametrize(
    "permitted",
    [
        "Estimated local fatigue is elevated.",
        "This session produced high neuromuscular strain in the model.",
        "Your recent sleep context is less favourable than baseline.",
        "Observed performance is below your recent trend.",
    ],
)
def test_the_permitted_examples_pass(permitted):
    assert check_claim_boundaries(permitted) == permitted


@pytest.mark.spec("RESEARCH:claim-boundaries-enforced")
def test_every_driver_string_the_engine_generates_stays_inside_the_boundaries(window):
    _, results = window
    drivers = {r.driver for result in results for r in result.traces.values() if r.driver}
    assert len(drivers) > 200, f"only {len(drivers)} distinct drivers to check"
    for driver in drivers:
        check_claim_boundaries(driver)


def test_a_driver_names_only_contributors_that_are_in_the_trace(window):
    """§19.6: no driver string may be emitted that the trace cannot derive."""
    _, results = window
    checked = 0
    for result in results:
        for record in result.traces.values():
            if not record.driver:
                continue
            checked += 1
            named = [c for c in record.contributors if not c.is_residual][:2]
            leader = named[0]
            # Either the two leaders are named, or the diffuse template names
            # the leader's exercise. Both come from the contributor list.
            assert (
                leader.label in record.driver
                or leader.label.split(",")[0] in record.driver
            ), record.driver
    assert checked > 5000


def test_a_diffuse_state_is_not_attributed_to_two_sets():
    """Naming two contributors at eight per cent each implies what is not there."""
    engine, ledger = _engine()
    for index in range(20):
        engine.apply_dose(
            _dose(0.1), 17.0 + index * 0.02, "bench_press", f"set:{index}", f"Bench, set {index+1}"
        )
    engine.advance_to(24.0)
    builder = TraceBuilder(ledger)
    record = builder.record(Channel.LOCAL_FATIGUE, "chest", engine.state)

    assert record.contributors[0].share < 0.25
    assert "rather than any single set" in record.driver
    assert "set 1 " not in record.driver


def test_a_driver_reports_the_largest_modifier_deviation():
    engine, ledger = _engine()
    engine.apply_dose(_dose(), 17.0, "bench_press", "set:1", "Bench, set 1")
    engine.advance_to(24.0)
    builder = TraceBuilder(ledger)
    context = RecoveryContext(
        rho=0.86,
        raw_z={"hrv": -0.4, "resting_hr": 2.1, "sleep_efficiency": 0.2},
    )
    record = builder.record(Channel.LOCAL_FATIGUE, "chest", engine.state, context)

    assert "resting heart rate" in record.driver
    assert "hrv" not in record.driver
    assert record.modifiers[0].name == "recovery context"


def test_adaptation_reports_no_recovery_modifier():
    """Reporting rho against a channel it does not touch would be false."""
    engine, ledger = _engine()
    engine.apply_dose(_dose(), 17.0, "bench_press", "set:1", "Bench, set 1")
    engine.advance_to(24.0)
    builder = TraceBuilder(ledger)
    context = RecoveryContext(rho=0.80, raw_z={"hrv": -2.0})

    fatigue = builder.record(Channel.LOCAL_FATIGUE, "chest", engine.state, context)
    adaptation = builder.record(Channel.ADAPTATION, "chest", engine.state, context)
    assert fatigue.modifiers
    assert adaptation.modifiers == ()


# --- display -----------------------------------------------------------------

def test_the_display_transform_is_an_index_not_a_percentage_of_anything():
    """Bounded and monotone, and never a claim about biology.

    The latent state is unbounded; the display is not. Nothing in the range
    the engine actually produces comes close to the ceiling — the worst day in
    the development window sits around 30 — so the compression happens where
    no real reading lives.
    """
    assert display_value(0.0) == 0.0
    assert display_value(1.0) == pytest.approx(100 * (1 - math.exp(-1)))

    values = [display_value(x / 10) for x in range(0, 60)]
    assert values == sorted(values)
    assert all(0.0 <= v < 100.0 for v in values)
    assert display_value(3.0) > display_value(2.0)


def test_a_trace_record_carries_its_channel_confidence(window):
    _, results = window
    record = next(iter(results[-1].traces.values()))
    assert record.confidence is not None
    assert record.confidence.binding_reason.detail
