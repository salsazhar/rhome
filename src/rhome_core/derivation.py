"""Derived coefficients for user-created exercises (``MODEL.tex`` §Derived).

An athlete creating a new exercise supplies muscles, not coefficients. This
module infers the scoring layer from what they do supply: primary, secondary
and optionally tertiary muscle tags, plus movement pattern and equipment.

Two of the derived values need different treatment, and the distinction is the
substance of this module.

Contribution vectors follow directly from the tags, because the interface tiers
map onto the model's existing roles. Compoundness and systemic cost do not:
they are properties of the *movement*, not of its muscles. Tagging quadriceps
tells you nothing about whether the movement is a barbell squat or a seated leg
extension, and those differ enormously in whole-body cost.

Systemic cost in particular resists the obvious approach. Deriving it from
recruited muscle mass alone fails: a leg extension recruits the quadriceps, the
largest entry in the mass table, yet is systemically cheap because the athlete
is seated and braced; a pull-up and a chest-supported row recruit near-identical
musculature at materially different cost. Mass identifies which muscles work;
posture and pattern determine what the effort costs. Cost is therefore built
from pattern and equipment, with mass entering only as a modulator.
"""

from __future__ import annotations

import math
from types import MappingProxyType

from rhome_core.exercises import (
    CoefficientSource,
    Equipment,
    Exercise,
    ExerciseKind,
    MovementPattern,
    NuzzoCurve,
)
from rhome_core.muscles import MASS_WEIGHT, Muscle

__all__ = [
    "KAPPA_PATTERN_BASE",
    "KAPPA_EQUIPMENT_ADJUSTMENT",
    "SYSTEMIC_PATTERN_BASE",
    "SYSTEMIC_EQUIPMENT_ADJUSTMENT",
    "BODYWEIGHT_FRACTION_DEFAULT",
    "derive_compoundness",
    "derive_systemic_cost",
    "derive_bodyweight_fraction",
    "derive_exercise",
]

#: Pattern carries the multi-joint, high-force character of the movement, and
#: dominates. An earlier form made equipment the base and adjusted by pattern,
#: which let a barbell curl derive 0.44 -- outside the documented isolation
#: band of 0.15-0.30 -- because equipment outweighed the isolation penalty.
KAPPA_PATTERN_BASE: MappingProxyType[MovementPattern, float] = MappingProxyType(
    {
        MovementPattern.HINGE: 0.82,
        MovementPattern.SQUAT: 0.82,
        MovementPattern.VERTICAL_PRESS: 0.68,
        MovementPattern.HORIZONTAL_PRESS: 0.68,
        MovementPattern.VERTICAL_PULL: 0.68,
        MovementPattern.HORIZONTAL_PULL: 0.68,
        MovementPattern.LUNGE: 0.62,
        MovementPattern.ISOLATION: 0.20,
        MovementPattern.ROTATION: 0.20,
    }
)

#: How much the athlete must control the load themselves.
KAPPA_EQUIPMENT_ADJUSTMENT: MappingProxyType[Equipment, float] = MappingProxyType(
    {
        Equipment.BARBELL: 0.08,
        Equipment.BODYWEIGHT: 0.02,
        Equipment.DUMBBELL: 0.00,
        Equipment.MACHINE: -0.14,
        Equipment.CABLE: -0.20,
    }
)

#: Postural demand of the pattern: the dominant term in systemic cost.
SYSTEMIC_PATTERN_BASE: MappingProxyType[MovementPattern, float] = MappingProxyType(
    {
        MovementPattern.HINGE: 0.75,
        MovementPattern.SQUAT: 0.72,
        MovementPattern.LUNGE: 0.62,
        MovementPattern.VERTICAL_PRESS: 0.48,
        MovementPattern.VERTICAL_PULL: 0.48,
        MovementPattern.HORIZONTAL_PULL: 0.48,
        MovementPattern.HORIZONTAL_PRESS: 0.42,
        MovementPattern.ISOLATION: 0.18,
        MovementPattern.ROTATION: 0.18,
    }
)

#: Proxy for how much the equipment supports the athlete. A machine takes the
#: torso's work; a barbell leaves the athlete to stabilise the load themselves.
SYSTEMIC_EQUIPMENT_ADJUSTMENT: MappingProxyType[Equipment, float] = MappingProxyType(
    {
        Equipment.BARBELL: 0.10,
        Equipment.BODYWEIGHT: 0.05,
        Equipment.DUMBBELL: 0.04,
        Equipment.CABLE: -0.04,
        Equipment.MACHINE: -0.06,
    }
)

BODYWEIGHT_FRACTION_DEFAULT: MappingProxyType[MovementPattern, float] = MappingProxyType(
    {
        MovementPattern.VERTICAL_PULL: 1.00,
        MovementPattern.SQUAT: 0.85,
        MovementPattern.HORIZONTAL_PRESS: 0.65,
        MovementPattern.LUNGE: 0.85,
        MovementPattern.HINGE: 0.55,
        MovementPattern.VERTICAL_PRESS: 0.65,
        MovementPattern.HORIZONTAL_PULL: 0.65,
        MovementPattern.ISOLATION: 0.55,
        MovementPattern.ROTATION: 0.55,
    }
)

_MASS_NORMALISER = 3.0
_MASS_TERM_WEIGHT = 0.10


def derive_compoundness(
    equipment: Equipment, pattern: MovementPattern, primary_count: int
) -> float:
    """Infer ``kappa``: high-force, multi-joint demand."""
    if primary_count < 1:
        raise ValueError("at least one primary muscle is required")
    value = (
        KAPPA_PATTERN_BASE[pattern]
        + KAPPA_EQUIPMENT_ADJUSTMENT[equipment]
        + 0.06 * (primary_count - 1)
    )
    return min(max(value, 0.15), 1.00)


def derive_systemic_cost(
    stimulus_contributions: dict[Muscle, float],
    equipment: Equipment,
    pattern: MovementPattern,
) -> float:
    """Infer ``b``: whole-body demand.

    Pattern and equipment carry the postural demand; recruited mass modulates
    it. See the module docstring for why mass cannot be the driver.
    """
    recruited_mass = sum(
        weight * MASS_WEIGHT[muscle] for muscle, weight in stimulus_contributions.items()
    )
    value = (
        SYSTEMIC_PATTERN_BASE[pattern]
        + SYSTEMIC_EQUIPMENT_ADJUSTMENT[equipment]
        + _MASS_TERM_WEIGHT * min(1.0, recruited_mass / _MASS_NORMALISER)
    )
    return min(max(value, 0.20), 1.00)


def derive_bodyweight_fraction(
    kind: ExerciseKind, pattern: MovementPattern
) -> float | None:
    """Infer ``beta``, which applies only to bodyweight-involving kinds."""
    if kind not in {ExerciseKind.REPS_ONLY, ExerciseKind.ASSISTED_REPS}:
        return None
    return BODYWEIGHT_FRACTION_DEFAULT[pattern]


def derive_exercise(
    exercise_id: str,
    name: str,
    movement_pattern: MovementPattern,
    equipment: Equipment,
    exercise_kind: ExerciseKind,
    primary_muscles: tuple[Muscle, ...],
    secondary_muscles: tuple[Muscle, ...] = (),
    tertiary_muscles: tuple[Muscle, ...] = (),
    unilateral: bool = False,
) -> Exercise:
    """Build a complete exercise from muscle tags alone.

    The result is stamped ``derived``, which reduces the dose-quality component
    of confidence. It never alters the dose itself: a guessed coefficient makes
    the model less certain, not differently wrong.
    """
    stimulus = {
        **{m: 1.00 for m in primary_muscles},
        **{m: 0.50 for m in secondary_muscles},
    }
    return Exercise(
        exercise_id=exercise_id,
        name=name,
        movement_pattern=movement_pattern,
        equipment=equipment,
        exercise_kind=exercise_kind,
        primary_muscles=tuple(primary_muscles),
        secondary_muscles=tuple(secondary_muscles),
        stabiliser_muscles=tuple(tertiary_muscles),
        compoundness=derive_compoundness(equipment, movement_pattern, len(primary_muscles)),
        systemic_cost=derive_systemic_cost(stimulus, equipment, movement_pattern),
        bodyweight_fraction=derive_bodyweight_fraction(exercise_kind, movement_pattern),
        axial_load=None,
        eccentric_demand=None,
        nuzzo_curve=NuzzoCurve.GENERAL,
        unilateral=unilateral,
        coefficient_source=CoefficientSource.DERIVED,
    )
