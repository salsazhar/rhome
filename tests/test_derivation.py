"""Derived coefficients for user-created exercises (``MODEL.tex`` §Derived).

The derivation exists so a user-created exercise is usable, not to replace
curation. It is validated against the curated library, where the hand-assigned
values provide a reference.
"""

from __future__ import annotations

import pytest

from rhome_core.derivation import (
    BODYWEIGHT_FRACTION_DEFAULT,
    derive_bodyweight_fraction,
    derive_compoundness,
    derive_exercise,
    derive_systemic_cost,
)
from rhome_core.exercises import (
    CoefficientSource,
    Equipment,
    ExerciseKind,
    MovementPattern,
    load_library,
)
from rhome_core.muscles import Muscle

TOLERANCE = 0.15
MIN_AGREEMENT = 0.80

#: Exercises the derivation is known to miss, with the reason. Tracked
#: explicitly so the limitation stays visible rather than being absorbed into
#: an aggregate pass rate.
KNOWN_OUTLIERS = {
    "back_extension": (
        "The 'hinge' pattern covers both a loaded standing deadlift and an "
        "unloaded supported back extension. The model cannot see absolute load "
        "by design, so the derivation has no signal to separate them."
    ),
}


@pytest.fixture(scope="module")
def library():
    return load_library()


def _derived_pair(exercise):
    return (
        derive_compoundness(
            exercise.equipment, exercise.movement_pattern, len(exercise.primary_muscles)
        ),
        derive_systemic_cost(
            exercise.stimulus_contributions, exercise.equipment, exercise.movement_pattern
        ),
    )


# --- the acceptance criterion ----------------------------------------------

@pytest.mark.spec("MODEL:derivation-matches-curated")
def test_derivation_meets_its_documented_acceptance_criterion(library):
    """At least 80% of curated exercises within ±0.15 on both coefficients."""
    within = 0
    for exercise in library:
        kappa, systemic = _derived_pair(exercise)
        if (
            abs(kappa - exercise.compoundness) <= TOLERANCE
            and abs(systemic - exercise.systemic_cost) <= TOLERANCE
        ):
            within += 1
    agreement = within / len(library)
    assert agreement >= MIN_AGREEMENT, (
        f"only {agreement:.0%} of curated exercises are reproduced within "
        f"±{TOLERANCE}; the documented criterion is {MIN_AGREEMENT:.0%}"
    )


@pytest.mark.spec("MODEL:derivation-matches-curated")
@pytest.mark.parametrize(
    "exercise_id",
    [e for e in load_library().exercises if e not in KNOWN_OUTLIERS],
)
def test_each_non_outlier_exercise_is_reproduced(library, exercise_id):
    exercise = library[exercise_id]
    kappa, systemic = _derived_pair(exercise)
    assert abs(kappa - exercise.compoundness) <= TOLERANCE, (
        f"{exercise_id}: derived compoundness {kappa:.2f} vs curated "
        f"{exercise.compoundness:.2f}"
    )
    assert abs(systemic - exercise.systemic_cost) <= TOLERANCE, (
        f"{exercise_id}: derived systemic cost {systemic:.2f} vs curated "
        f"{exercise.systemic_cost:.2f}"
    )


@pytest.mark.parametrize("exercise_id, reason", sorted(KNOWN_OUTLIERS.items()))
def test_known_outliers_are_still_outliers(library, exercise_id, reason):
    """If one starts passing, the limitation was fixed and should be removed.

    Kept as an assertion so the list cannot quietly go stale.
    """
    exercise = library[exercise_id]
    kappa, systemic = _derived_pair(exercise)
    worst = max(
        abs(kappa - exercise.compoundness), abs(systemic - exercise.systemic_cost)
    )
    assert worst > TOLERANCE, (
        f"{exercise_id} now agrees within ±{TOLERANCE}. If the derivation "
        f"improved, remove it from KNOWN_OUTLIERS. Reason recorded: {reason}"
    )


# --- the mass-versus-posture property --------------------------------------

@pytest.mark.spec("MODEL:systemic-cost-not-mass-alone")
def test_identical_muscles_can_have_very_different_systemic_cost():
    """The finding the derivation was restructured around.

    A leg extension and a back squat both load the quadriceps. Deriving cost
    from recruited mass alone would give them similar values, which is wrong:
    one is performed seated and braced.
    """
    quads_only = {Muscle.QUADS: 1.0}
    seated = derive_systemic_cost(quads_only, Equipment.MACHINE, MovementPattern.ISOLATION)
    standing = derive_systemic_cost(quads_only, Equipment.BARBELL, MovementPattern.SQUAT)
    assert standing > seated + 0.4, (
        "posture and pattern must dominate systemic cost, not recruited mass"
    )


def test_recruited_mass_still_modulates_cost():
    """Mass is not the driver, but it is not ignored either."""
    light = derive_systemic_cost({Muscle.BICEPS: 1.0}, Equipment.BARBELL, MovementPattern.SQUAT)
    heavy = derive_systemic_cost(
        {Muscle.QUADS: 1.0, Muscle.GLUTES: 1.0}, Equipment.BARBELL, MovementPattern.SQUAT
    )
    assert heavy > light


def test_supported_equipment_reduces_systemic_cost():
    contributions = {Muscle.LATS: 1.0, Muscle.UPPER_BACK: 1.0}
    free = derive_systemic_cost(contributions, Equipment.BARBELL, MovementPattern.HORIZONTAL_PULL)
    supported = derive_systemic_cost(contributions, Equipment.MACHINE, MovementPattern.HORIZONTAL_PULL)
    assert free > supported


# --- compoundness ----------------------------------------------------------

def test_more_primary_muscles_raise_compoundness():
    one = derive_compoundness(Equipment.BARBELL, MovementPattern.SQUAT, 1)
    three = derive_compoundness(Equipment.BARBELL, MovementPattern.SQUAT, 3)
    assert three > one


def test_isolation_is_low_compoundness_on_any_equipment():
    for equipment in Equipment:
        value = derive_compoundness(equipment, MovementPattern.ISOLATION, 1)
        assert value <= 0.35, f"{equipment.value} isolation derived {value:.2f}"


def test_free_weight_outranks_machine_for_the_same_pattern():
    barbell = derive_compoundness(Equipment.BARBELL, MovementPattern.SQUAT, 1)
    machine = derive_compoundness(Equipment.MACHINE, MovementPattern.SQUAT, 1)
    assert barbell > machine


@pytest.mark.parametrize("count", [0, -1])
def test_derivation_requires_a_primary_muscle(count):
    with pytest.raises(ValueError):
        derive_compoundness(Equipment.BARBELL, MovementPattern.SQUAT, count)


def test_derived_coefficients_are_always_in_range():
    for equipment in Equipment:
        for pattern in MovementPattern:
            for count in (1, 2, 3, 5):
                kappa = derive_compoundness(equipment, pattern, count)
                assert 0.15 <= kappa <= 1.00
            systemic = derive_systemic_cost(
                {m: 1.0 for m in Muscle}, equipment, pattern
            )
            assert 0.20 <= systemic <= 1.00


# --- bodyweight fraction ---------------------------------------------------

def test_bodyweight_fraction_only_applies_to_bodyweight_kinds():
    assert derive_bodyweight_fraction(ExerciseKind.WEIGHTED_REPS, MovementPattern.SQUAT) is None
    assert derive_bodyweight_fraction(ExerciseKind.TIME_ONLY, MovementPattern.SQUAT) is None
    assert derive_bodyweight_fraction(ExerciseKind.REPS_ONLY, MovementPattern.VERTICAL_PULL) == 1.00
    assert derive_bodyweight_fraction(ExerciseKind.ASSISTED_REPS, MovementPattern.VERTICAL_PULL) == 1.00


def test_every_pattern_has_a_bodyweight_default():
    for pattern in MovementPattern:
        assert pattern in BODYWEIGHT_FRACTION_DEFAULT


# --- end-to-end user-created exercise --------------------------------------

def test_user_created_exercise_is_complete_and_marked_derived():
    """The scenario from the interface: a name, a pattern, and muscle tags."""
    exercise = derive_exercise(
        exercise_id="po",
        name="Po",
        movement_pattern=MovementPattern.SQUAT,
        equipment=Equipment.BARBELL,
        exercise_kind=ExerciseKind.WEIGHTED_REPS,
        primary_muscles=(Muscle.QUADS,),
        secondary_muscles=(Muscle.GLUTES,),
        tertiary_muscles=(Muscle.ABS,),
    )
    assert exercise.coefficient_source is CoefficientSource.DERIVED
    assert 0.15 <= exercise.compoundness <= 1.0
    assert 0.20 <= exercise.systemic_cost <= 1.0
    assert exercise.bears_dose


def test_user_tiers_map_onto_the_model_contribution_roles():
    exercise = derive_exercise(
        exercise_id="po", name="Po",
        movement_pattern=MovementPattern.SQUAT, equipment=Equipment.BARBELL,
        exercise_kind=ExerciseKind.WEIGHTED_REPS,
        primary_muscles=(Muscle.QUADS,), secondary_muscles=(Muscle.GLUTES,),
        tertiary_muscles=(Muscle.ABS,),
    )
    assert exercise.stimulus_contributions[Muscle.QUADS] == pytest.approx(1.00)
    assert exercise.stimulus_contributions[Muscle.GLUTES] == pytest.approx(0.50)
    assert Muscle.ABS not in exercise.stimulus_contributions, (
        "a tertiary muscle earns no adaptive credit"
    )
    assert exercise.fatigue_contributions[Muscle.ABS] == pytest.approx(0.20), (
        "a tertiary muscle does accrue fatigue"
    )


def test_derived_exercise_still_passes_schema_validation():
    """A user-created exercise is a first-class citizen, not a special case."""
    exercise = derive_exercise(
        exercise_id="grip_thing", name="Grip Thing",
        movement_pattern=MovementPattern.VERTICAL_PULL, equipment=Equipment.BODYWEIGHT,
        exercise_kind=ExerciseKind.REPS_ONLY,
        primary_muscles=(Muscle.FOREARMS,),
    )
    assert exercise.bodyweight_fraction == 1.00
    assert sum(exercise.performance_weights.values()) == pytest.approx(1.0)
