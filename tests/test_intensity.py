"""Relative-intensity mapping (``MODEL.tex`` §Estimating relative intensity)."""

from __future__ import annotations

import pytest

from rhome_core.intensity import (
    DOMAIN_MAX_REPS,
    DOMAIN_MIN_INTENSITY,
    DOMAIN_MIN_REPS,
    EXERCISE_ENDURANCE_FACTOR,
    NUZZO_GENERAL,
    IntensityConfidence,
    relative_intensity,
    reps_to_failure,
    rir_from_rpe,
)


# --- RPE to RIR (MODEL.tex) ------------------------------------------------

@pytest.mark.spec("MODEL:rpe-to-rir")
@pytest.mark.parametrize("rpe, expected", [(10, 0), (9.5, 0.5), (9, 1), (8, 2), (6, 4)])
def test_rpe_maps_to_repetitions_in_reserve(rpe, expected):
    assert rir_from_rpe(rpe) == pytest.approx(expected)


def test_rpe_below_the_scale_does_not_give_negative_reserve():
    assert rir_from_rpe(0) >= 0


@pytest.mark.parametrize("bad", [-1, 10.5, 12])
def test_impossible_rpe_is_rejected(bad):
    with pytest.raises(ValueError):
        rir_from_rpe(bad)


# --- the published relationship --------------------------------------------

@pytest.mark.spec("MODEL:nuzzo-inversion")
@pytest.mark.parametrize("intensity, reps", NUZZO_GENERAL)
def test_every_published_value_round_trips(intensity, reps):
    """The tabulated relationship must be reproduced exactly, not approximated."""
    got, confidence = relative_intensity(reps, 0.0)
    assert got == pytest.approx(intensity, abs=1e-9)
    assert confidence is IntensityConfidence.HIGH


@pytest.mark.spec("MODEL:nuzzo-inversion")
def test_relative_intensity_falls_monotonically_with_repetitions():
    previous = 1.01
    for reps in range(1, 40):
        current, _ = relative_intensity(reps, 0.0)
        assert 0.0 < current <= previous, f"not monotone at {reps} repetitions"
        previous = current


def test_repetitions_in_reserve_lower_the_implied_intensity():
    """The same repetitions with more left over mean a lighter load."""
    hard, _ = relative_intensity(5, 0.0)
    easy, _ = relative_intensity(5, 3.0)
    assert easy < hard


def test_the_inverse_agrees_with_the_curve():
    for reps in (4, 6, 10, 15, 22):
        intensity, _ = relative_intensity(reps, 0.0)
        assert reps_to_failure(intensity) == pytest.approx(reps, rel=0.02)


# --- domain policy (MODEL.tex) ---------------------------------------------

@pytest.mark.spec("MODEL:intensity-domain-policy")
def test_a_single_maximal_repetition_is_the_maximum_by_definition():
    intensity, confidence = relative_intensity(1, 0.0)
    assert intensity == pytest.approx(1.00)
    assert confidence is IntensityConfidence.MEDIUM


@pytest.mark.spec("MODEL:intensity-domain-policy")
def test_near_maximal_sets_are_extended_not_clipped():
    """Clipping would make a true single indistinguishable from a heavy triple."""
    single, _ = relative_intensity(1, 0.0)
    double, _ = relative_intensity(2, 0.0)
    triple, _ = relative_intensity(3, 0.0)
    assert single > double > triple
    assert triple > 0.94, "the extension should meet the tabulated curve near 0.95"


@pytest.mark.spec("MODEL:intensity-domain-policy")
def test_high_repetition_sets_are_clipped_and_flagged():
    intensity, confidence = relative_intensity(30, 4.0)
    assert intensity == pytest.approx(DOMAIN_MIN_INTENSITY)
    assert confidence is IntensityConfidence.LOW


@pytest.mark.spec("MODEL:intensity-domain-policy")
@pytest.mark.parametrize(
    "reps, rir, expected",
    [
        (5, 1, IntensityConfidence.HIGH),
        (10, 2, IntensityConfidence.HIGH),
        (2, 0, IntensityConfidence.MEDIUM),
        (1, 0, IntensityConfidence.MEDIUM),
        (25, 4, IntensityConfidence.LOW),
    ],
)
def test_confidence_matches_the_documented_policy(reps, rir, expected):
    _, confidence = relative_intensity(reps, rir)
    assert confidence is expected


def test_intensity_never_leaves_its_bounds():
    for reps in range(1, 60):
        for rir in (0, 1, 3, 6):
            intensity, _ = relative_intensity(reps, rir)
            assert DOMAIN_MIN_INTENSITY <= intensity <= 1.0


# --- exercise-specific curves ----------------------------------------------

def test_leg_press_implies_a_heavier_load_than_bench_for_the_same_set():
    """Nuzzo et al. report leg press permits more repetitions at a given load.

    So performing only six repetitions on a movement where many are normally
    possible implies a heavier load relative to maximum — the direction is easy
    to get backwards.
    """
    bench, _ = relative_intensity(5, 1, "bench")
    general, _ = relative_intensity(5, 1, "general")
    leg_press, _ = relative_intensity(5, 1, "leg_press")
    assert bench < general < leg_press


def test_the_exercise_factors_are_recorded_as_approximations():
    """The published tables are not in this project's documents.

    The factors express the reported direction, not the reported curves, and
    the module says so. This test pins that they remain modest, so an
    approximation cannot quietly grow into a strong claim.
    """
    assert EXERCISE_ENDURANCE_FACTOR["general"] == 1.00
    for name, factor in EXERCISE_ENDURANCE_FACTOR.items():
        assert 0.75 <= factor <= 1.35, f"{name} factor {factor} is not modest"


def test_an_unknown_curve_is_rejected():
    with pytest.raises(ValueError, match="unknown curve"):
        relative_intensity(5, 1, "deadlift")


# --- input validation ------------------------------------------------------

@pytest.mark.parametrize("reps, rir", [(0, 1), (-2, 1), (5, -1)])
def test_impossible_sets_are_rejected(reps, rir):
    with pytest.raises(ValueError):
        relative_intensity(reps, rir)


def test_the_domain_boundaries_match_the_specification():
    assert DOMAIN_MIN_REPS == pytest.approx(3.28)
    assert DOMAIN_MAX_REPS == pytest.approx(25.99)
    assert DOMAIN_MIN_INTENSITY == pytest.approx(0.50)
