"""Athlete A's latent parameters (``DATA.md`` §10, §16.2).

The properties tested here are what make the synthetic dataset a genuine test
rather than a circular one. If the simulator's parameters collapsed onto the
engine's priors, the engine would be inverting its own generator.
"""

from __future__ import annotations

import numpy as np
import pytest

from rhome_core.exercises import load_library
from rhome_core.muscles import Muscle
from rhome_core.parameters import CORE_PARAMETERS
from rhome_sim.athlete import ANCHOR_CAPACITY_KG, sample_athlete
from rhome_sim.parameters import SIM_PARAMETERS

SEED = 20260822


@pytest.fixture(scope="module")
def athlete():
    return sample_athlete(SEED)


@pytest.fixture(scope="module")
def library():
    return load_library()


# --- determinism -----------------------------------------------------------

@pytest.mark.guardrail(4)
def test_same_seed_reproduces_an_identical_athlete():
    first, second = sample_athlete(SEED), sample_athlete(SEED)
    assert first == second


@pytest.mark.guardrail(4)
def test_different_seeds_give_different_athletes():
    assert sample_athlete(1) != sample_athlete(2)


# --- the inverse-crime property -------------------------------------------

@pytest.mark.spec("DATA:simulator-richer-than-engine")
def test_every_muscle_has_its_own_recovery_half_life(athlete):
    """The engine assumes one value for all sixteen; the athlete has sixteen."""
    values = list(athlete.local_half_life_h.values())
    assert len(set(values)) == len(Muscle), "half-lives must be sampled per muscle"


@pytest.mark.spec("DATA:simulator-richer-than-engine")
def test_half_life_spread_is_wide_enough_to_matter(athlete):
    """A spread too narrow to affect behaviour would make the test vacuous."""
    assert athlete.half_life_spread_h() > 6.0, (
        "if every muscle recovers at nearly the same rate, the engine's "
        "single-value assumption costs it nothing and is never tested"
    )


@pytest.mark.spec("DATA:simulator-richer-than-engine")
def test_no_muscle_sits_exactly_on_the_engine_prior(athlete):
    """A muscle at exactly 30 h would be a free win for the engine."""
    for muscle, half_life in athlete.local_half_life_h.items():
        assert abs(half_life - 30.0) > 1e-6, f"{muscle.value} sits on the engine prior"


@pytest.mark.spec("DATA:simulator-richer-than-engine")
def test_global_half_lives_differ_from_the_engine_priors(athlete):
    assert abs(athlete.systemic_half_life_h - 30.0) > 0.1
    assert abs(athlete.neuromuscular_half_life_h - 24.0) > 0.1


@pytest.mark.spec("DATA:simulator-richer-than-engine")
def test_rir_reporting_is_biased_in_both_directions(athlete):
    """The engine assumes unbiased RIR. This athlete is not."""
    biases = list(athlete.rir_bias.values())
    assert min(biases) < -0.05 and max(biases) > 0.05, (
        "bias must run both ways, or the engine could correct it with a constant"
    )
    assert max(abs(b) for b in biases) < 2.0, "bias must stay physiologically plausible"


@pytest.mark.spec("DATA:heteroskedastic-performance-noise")
def test_performance_noise_is_heteroskedastic(athlete, library):
    """Less compound movements must vary more, as ``DATA.md`` §16.2 requires."""
    scales = athlete.performance_noise_scale
    compoundness = {e.exercise_id: e.compoundness for e in library}
    xs = [compoundness[k] for k in scales]
    ys = [scales[k] for k in scales]
    correlation = float(np.corrcoef(xs, ys)[0, 1])
    assert correlation < -0.5, (
        f"noise scale should fall as compoundness rises; correlation {correlation:.2f}"
    )
    assert len(set(ys)) == len(ys), "a constant noise scale is homoskedastic"


def test_simulator_and_core_registries_are_separate():
    """D4: the engine's priors must not be reachable through a shared registry."""
    assert SIM_PARAMETERS.namespace != CORE_PARAMETERS.namespace
    shared = {p.name for p in SIM_PARAMETERS} & {p.name for p in CORE_PARAMETERS}
    assert not shared, f"a parameter registered in both registries: {shared}"


# --- documented starting state --------------------------------------------

@pytest.mark.spec("DATA:athlete-starting-state")
def test_starting_state_matches_the_specification(athlete):
    assert athlete.initial_body_mass_kg == 80.0
    assert athlete.habitual_steps == 10000.0
    assert athlete.target_sleep_h == 7.5
    assert athlete.baseline_resting_hr_bpm == 52.0
    assert athlete.baseline_log_rmssd == pytest.approx(np.log(60.0))


@pytest.mark.spec("DATA:athlete-starting-state")
@pytest.mark.parametrize(
    "exercise_id, documented",
    [
        ("bench_press", 105.0),
        ("back_squat", 155.0),
        ("deadlift", 185.0),
        ("overhead_press", 65.0),
    ],
)
def test_documented_anchor_lifts_start_near_their_specified_values(
    athlete, exercise_id, documented
):
    """Individual variation is applied, but must stay close to the anchor."""
    assert ANCHOR_CAPACITY_KG[exercise_id] == documented
    assert athlete.initial_capacity_kg[exercise_id] == pytest.approx(
        documented, rel=0.20
    )


# --- coverage and plausibility --------------------------------------------

def test_every_library_exercise_has_a_starting_capacity(athlete, library):
    for exercise in library:
        assert exercise.exercise_id in athlete.initial_capacity_kg


def test_missing_starting_capacity_is_rejected(tmp_path):
    """An exercise the athlete cannot train must fail loudly, not silently."""
    csv_path = tmp_path / "extra.csv"
    source = load_library.__module__  # noqa: F841  (documentation of intent)
    header = (
        "exercise_id,name,movement_pattern,equipment,exercise_kind,primary_muscles,"
        "secondary_muscles,stabiliser_muscles,compoundness,systemic_cost,"
        "bodyweight_fraction,axial_load,eccentric_demand,nuzzo_curve,unilateral,"
        "coefficient_source\n"
    )
    csv_path.write_text(
        header
        + "mystery_lift,Mystery Lift,squat,barbell,weighted_reps,quads,,,0.9,0.9,,,,general,false,curated\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no starting capacity"):
        sample_athlete(SEED, library=load_library(csv_path))


def test_half_lives_stay_inside_the_documented_truncation(athlete):
    low = SIM_PARAMETERS.value("local_half_life_min_h")
    high = SIM_PARAMETERS.value("local_half_life_max_h")
    for muscle, half_life in athlete.local_half_life_h.items():
        assert low <= half_life <= high, f"{muscle.value} at {half_life:.1f} h"


def test_truncation_does_not_pile_mass_on_the_boundaries():
    """Rejection sampling, not clipping.

    Clipping a normal to a range would give several muscles a half-life of
    exactly 24 or 42 hours, which is not what a truncated normal means.
    """
    low = SIM_PARAMETERS.value("local_half_life_min_h")
    high = SIM_PARAMETERS.value("local_half_life_max_h")
    on_boundary = 0
    for seed in range(60):
        for half_life in sample_athlete(seed).local_half_life_h.values():
            if abs(half_life - low) < 1e-9 or abs(half_life - high) < 1e-9:
                on_boundary += 1
    assert on_boundary == 0, f"{on_boundary} half-lives landed exactly on a boundary"


@pytest.mark.parametrize("seed", range(12))
def test_sampled_parameters_stay_physiologically_plausible(seed):
    """No seed may produce an impossible athlete."""
    athlete = sample_athlete(seed)
    assert 20.0 <= athlete.systemic_half_life_h <= 45.0
    assert 15.0 <= athlete.neuromuscular_half_life_h <= 36.0
    assert 0.3 <= athlete.sleep_sd_h <= 1.3
    assert all(v > 0 for v in athlete.performance_noise_scale.values())
    assert all(v >= 0.5 for v in athlete.adaptation_rate.values())
    assert all(v > 0 for v in athlete.initial_capacity_kg.values())
    assert athlete.novelty_sensitivity > 0


def test_capacities_rank_plausibly(athlete):
    """A trained athlete's relative strengths, as a coding-error trap."""
    capacity = athlete.initial_capacity_kg
    assert capacity["deadlift"] > capacity["back_squat"] > capacity["bench_press"]
    assert capacity["bench_press"] > capacity["overhead_press"]
    assert capacity["leg_press"] > capacity["back_squat"]
    assert capacity["back_squat"] > capacity["lateral_raise"] * 5


def test_athlete_parameters_are_immutable(athlete):
    with pytest.raises(TypeError):
        athlete.local_half_life_h[Muscle.CHEST] = 99.0  # type: ignore[index]
    with pytest.raises(Exception):
        athlete.initial_body_mass_kg = 90.0  # type: ignore[misc]
