"""Curated exercise library (``DATA.md`` §5.4, §8).

A great deal of the model's behaviour is decided in this table rather than in
any equation, so it is validated more heavily than its size suggests.
"""

from __future__ import annotations

import pytest

from rhome_core.exercises import (
    DOSE_BEARING_KINDS,
    CoefficientSource,
    Equipment,
    Exercise,
    ExerciseKind,
    MovementPattern,
    NuzzoCurve,
    load_library,
)
from rhome_core.muscles import Muscle, Region
from rhome_core.parameters import CORE_PARAMETERS


@pytest.fixture(scope="module")
def library():
    return load_library()


# --- structure -------------------------------------------------------------

def test_library_loads_and_is_not_trivially_small(library):
    assert len(library) >= 20


@pytest.mark.spec("DATA:exercise-library-covers-model")
def test_every_model_muscle_receives_load_from_some_exercise(library):
    missing = set(Muscle) - library.covered_muscles()
    assert not missing, (
        f"no exercise loads {sorted(m.value for m in missing)}; a muscle the "
        f"library cannot reach would hold a permanently empty state"
    )


def test_every_model_muscle_is_primary_somewhere(library):
    """A muscle only ever loaded indirectly could never be trained on purpose."""
    primary: set[Muscle] = set()
    for exercise in library:
        primary |= set(exercise.primary_muscles)
    missing = set(Muscle) - primary
    assert not missing, f"never a primary muscle: {sorted(m.value for m in missing)}"


def test_abs_is_trainable_directly(library):
    """Direct core work was absent from the pool until docs v0.3."""
    direct = [e for e in library if Muscle.ABS in e.primary_muscles]
    assert len(direct) >= 3, "the pool must contain real direct core work"


@pytest.mark.spec("DATA:upper-lower-parity-feasible")
def test_both_regions_have_enough_exercises_for_parity(library):
    """``DATA.md`` §3.2 requires upper/lower parity within ±10%.

    Impossible to satisfy if one region is thinly served, so the feasibility of
    the requirement is checked here rather than discovered in L1.4.
    """
    upper = library.by_region(Region.UPPER)
    lower = library.by_region(Region.LOWER)
    assert len(upper) >= 8 and len(lower) >= 8
    assert 0.6 <= len(upper) / len(lower) <= 1.7, (
        f"pool is lopsided: {len(upper)} upper vs {len(lower)} lower"
    )


# --- coefficient sanity ----------------------------------------------------

@pytest.mark.parametrize(
    "heavier, lighter, attribute",
    [
        ("back_squat", "lateral_raise", "systemic_cost"),
        ("deadlift", "leg_extension", "systemic_cost"),
        ("back_squat", "leg_press", "systemic_cost"),
        ("deadlift", "bench_press", "systemic_cost"),
        ("back_squat", "lat_pulldown", "compoundness"),
        ("bench_press", "triceps_pressdown", "compoundness"),
        ("deadlift", "leg_curl", "compoundness"),
        ("weighted_pullup", "db_curl", "compoundness"),
    ],
)
def test_coefficients_rank_plausibly(library, heavier, lighter, attribute):
    """Orderings a coach would recognise. A transposed row would break these."""
    assert getattr(library[heavier], attribute) > getattr(library[lighter], attribute)


def test_free_weight_compounds_outrank_their_machine_equivalents(library):
    assert library["back_squat"].compoundness > library["hack_squat"].compoundness
    assert library["weighted_pullup"].compoundness > library["lat_pulldown"].compoundness


@pytest.mark.parametrize(
    "exercise_id, band",
    [
        ("back_squat", (0.80, 1.00)),
        ("deadlift", (0.80, 1.00)),
        ("bench_press", (0.65, 0.85)),
        ("overhead_press", (0.65, 0.85)),
        ("leg_press", (0.45, 0.65)),
        ("lat_pulldown", (0.45, 0.65)),
        ("lateral_raise", (0.15, 0.30)),
        ("triceps_pressdown", (0.15, 0.30)),
        ("leg_curl", (0.15, 0.30)),
    ],
)
def test_compoundness_sits_in_its_documented_class_band(library, exercise_id, band):
    """Bands from ``MODEL.tex`` §Neuromuscular-strain impulse."""
    low, high = band
    assert low <= library[exercise_id].compoundness <= high


@pytest.mark.parametrize(
    "exercise_id, band",
    [
        ("deadlift", (0.80, 1.00)),
        ("back_squat", (0.80, 1.00)),
        ("bulgarian_split_squat", (0.65, 0.85)),
        ("leg_press", (0.65, 0.85)),
        ("bench_press", (0.45, 0.65)),
        ("cable_row", (0.45, 0.65)),
        ("lateral_raise", (0.20, 0.35)),
        ("leg_extension", (0.20, 0.35)),
    ],
)
def test_systemic_cost_sits_in_its_documented_class_band(library, exercise_id, band):
    """Bands from ``MODEL.tex`` §Systemic-fatigue impulse."""
    low, high = band
    assert low <= library[exercise_id].systemic_cost <= high


# --- contribution vectors --------------------------------------------------

def test_stabilisers_accrue_fatigue_but_earn_no_adaptive_credit(library):
    """The asymmetry is deliberate: grip limits a deadlift, but does not grow."""
    deadlift = library["deadlift"]
    assert Muscle.FOREARMS in deadlift.stabiliser_muscles
    assert Muscle.FOREARMS not in deadlift.stimulus_contributions
    assert deadlift.fatigue_contributions[Muscle.FOREARMS] == pytest.approx(0.20)


def test_contribution_tiers_use_the_registered_coefficients(library):
    squat = library["back_squat"]
    assert squat.stimulus_contributions[Muscle.QUADS] == pytest.approx(
        CORE_PARAMETERS.value("stimulus_primary_coeff")
    )
    assert squat.stimulus_contributions[Muscle.HAMSTRINGS] == pytest.approx(
        CORE_PARAMETERS.value("stimulus_secondary_coeff")
    )
    assert squat.fatigue_contributions[Muscle.ABS] == pytest.approx(
        CORE_PARAMETERS.value("fatigue_stabiliser_coeff")
    )


@pytest.mark.spec("MODEL:performance-weights-normalised")
def test_performance_weights_sum_to_one_for_every_exercise(library):
    for exercise in library:
        assert sum(exercise.performance_weights.values()) == pytest.approx(1.0)


@pytest.mark.spec("MODEL:performance-weights-normalised")
def test_performance_weights_include_stabilisers(library):
    """``omega`` uses the fatigue vector, not the stimulus vector."""
    deadlift = library["deadlift"]
    assert Muscle.FOREARMS in deadlift.performance_weights
    assert deadlift.performance_weights[Muscle.FOREARMS] > 0.0


# --- kinds and curves ------------------------------------------------------

@pytest.mark.spec("DATA:exercise-kind-dose-eligibility")
def test_every_library_exercise_bears_dose(library):
    """v0 Athlete A contains only repetition-based kinds."""
    for exercise in library:
        assert exercise.bears_dose
        assert exercise.exercise_kind in DOSE_BEARING_KINDS


@pytest.mark.spec("DATA:exercise-kind-dose-eligibility")
@pytest.mark.parametrize(
    "kind, expected",
    [
        (ExerciseKind.WEIGHTED_REPS, True),
        (ExerciseKind.REPS_ONLY, True),
        (ExerciseKind.ASSISTED_REPS, True),
        (ExerciseKind.TIME_ONLY, False),
        (ExerciseKind.WEIGHT_TIME, False),
        (ExerciseKind.WEIGHT_DISTANCE, False),
        (ExerciseKind.DISTANCE_TIME, False),
    ],
)
def test_dose_eligibility_by_kind(kind, expected):
    assert (kind in DOSE_BEARING_KINDS) is expected


def test_bodyweight_kinds_declare_a_fraction(library):
    for exercise in library:
        if exercise.requires_bodyweight:
            assert exercise.bodyweight_fraction is not None


def test_exercise_specific_nuzzo_curves_are_assigned(library):
    """Nuzzo et al. give exercise-specific curves only for these two."""
    assert library["bench_press"].nuzzo_curve is NuzzoCurve.BENCH
    assert library["leg_press"].nuzzo_curve is NuzzoCurve.LEG_PRESS
    others = [e for e in library if e.exercise_id not in {"bench_press", "leg_press"}]
    assert all(e.nuzzo_curve is NuzzoCurve.GENERAL for e in others)


def test_library_is_entirely_curated(library):
    for exercise in library:
        assert exercise.coefficient_source is CoefficientSource.CURATED


def test_unilateral_exercises_are_flagged(library):
    assert library["bulgarian_split_squat"].unilateral
    assert not library["back_squat"].unilateral


# --- schema validation -----------------------------------------------------

def _valid_kwargs(**overrides):
    base = dict(
        exercise_id="test", name="Test", movement_pattern=MovementPattern.SQUAT,
        equipment=Equipment.BARBELL, exercise_kind=ExerciseKind.WEIGHTED_REPS,
        primary_muscles=(Muscle.QUADS,), secondary_muscles=(), stabiliser_muscles=(),
        compoundness=0.9, systemic_cost=0.9, bodyweight_fraction=None,
        axial_load=None, eccentric_demand=None, nuzzo_curve=NuzzoCurve.GENERAL,
        unilateral=False, coefficient_source=CoefficientSource.CURATED,
    )
    base.update(overrides)
    return base


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_out_of_range_coefficients_are_rejected(value):
    with pytest.raises(ValueError, match="must be in"):
        Exercise(**_valid_kwargs(compoundness=value))


def test_exercise_without_a_primary_muscle_is_rejected():
    with pytest.raises(ValueError, match="primary muscle"):
        Exercise(**_valid_kwargs(primary_muscles=()))


def test_muscle_in_two_tiers_is_rejected():
    """Double-counting would silently inflate that muscle's dose."""
    with pytest.raises(ValueError, match="more than one tier"):
        Exercise(**_valid_kwargs(
            primary_muscles=(Muscle.QUADS,), secondary_muscles=(Muscle.QUADS,)
        ))


def test_bodyweight_kind_without_a_fraction_is_rejected():
    with pytest.raises(ValueError, match="bodyweight_fraction"):
        Exercise(**_valid_kwargs(
            exercise_kind=ExerciseKind.REPS_ONLY, bodyweight_fraction=None
        ))


def test_duplicate_exercise_ids_are_rejected(tmp_path):
    csv_path = tmp_path / "dup.csv"
    header = (
        "exercise_id,name,movement_pattern,equipment,exercise_kind,primary_muscles,"
        "secondary_muscles,stabiliser_muscles,compoundness,systemic_cost,"
        "bodyweight_fraction,axial_load,eccentric_demand,nuzzo_curve,unilateral,"
        "coefficient_source\n"
    )
    row = "x,X,squat,barbell,weighted_reps,quads,,,0.9,0.9,,,,general,false,curated\n"
    csv_path.write_text(header + row + row, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate exercise_id"):
        load_library(csv_path)


def test_unknown_muscle_label_in_csv_is_rejected(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "exercise_id,name,movement_pattern,equipment,exercise_kind,primary_muscles,"
        "secondary_muscles,stabiliser_muscles,compoundness,systemic_cost,"
        "bodyweight_fraction,axial_load,eccentric_demand,nuzzo_curve,unilateral,"
        "coefficient_source\n"
        "x,X,squat,barbell,weighted_reps,Pectoralis Minor,,,0.9,0.9,,,,general,false,curated\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown muscle label"):
        load_library(csv_path)


def test_display_labels_are_accepted_in_the_csv(tmp_path):
    """The library may be authored in either vocabulary."""
    csv_path = tmp_path / "display.csv"
    csv_path.write_text(
        "exercise_id,name,movement_pattern,equipment,exercise_kind,primary_muscles,"
        "secondary_muscles,stabiliser_muscles,compoundness,systemic_cost,"
        "bodyweight_fraction,axial_load,eccentric_demand,nuzzo_curve,unilateral,"
        "coefficient_source\n"
        "x,X,isolation,cable,weighted_reps,Upper Abs|Obliques,,,0.2,0.24,,,,general,false,curated\n",
        encoding="utf-8",
    )
    exercise = load_library(csv_path)["x"]
    assert exercise.primary_muscles == (Muscle.ABS,) or set(exercise.primary_muscles) == {Muscle.ABS}


# --- the athlete-authored library (L3.9) --------------------------------------

@pytest.mark.spec("DATA:library-labels-fold-to-model-groups")
def test_every_library_muscle_label_resolves_to_a_model_group():
    """D16, measured over all 1074 rows rather than asserted.

    Twelve labels in the athlete's library are outside the model taxonomy. Two
    are our own display labels in slug spelling and need no mapping; the rest
    fold per D16. A label that resolved to nothing would fail the load, so this
    also proves the library is readable at all.
    """
    from rhome_core.exercises import load_library, library_path

    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    assert len(library) == 1074, len(library)
    assert len(library.covered_muscles()) == len(list(Muscle)), (
        "every model group must receive load from some exercise"
    )


def test_v1_2_fixes_the_two_confirmed_equipment_mislabels():
    from rhome_core.exercises import Equipment, load_library, library_path

    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    assert library["straight_bar_triceps_pressdown"].equipment is Equipment.CABLE
    assert library["seated_calf_raise"].equipment is Equipment.MACHINE


@pytest.mark.spec("DATA:library-labels-fold-to-model-groups")
def test_an_unmapped_label_still_fails_rather_than_resolving_to_a_neighbour():
    """The mapping must not become a place where anything typed is accepted."""
    from rhome_core.muscles import resolve_display_label

    for label in ("quadzilla", "", "rotator cuffs", "core_deep"):
        with pytest.raises(KeyError):
            resolve_display_label(label)


@pytest.mark.spec("DATA:library-labels-fold-to-model-groups")
def test_the_fold_keeps_the_highest_tier_when_two_labels_collapse():
    """The consequence of D16 that only appears once a library is loaded.

    ``bent_over_barbell_row`` names ``posterior_delts`` as a secondary mover and
    ``rotator_cuff`` as a stabiliser. Both fold to ``posterior_delts``. The
    muscle must survive at the *higher* tier — a mover is not demoted because a
    finer label for the same group also appeared below it — and must appear
    exactly once, because counting one structure twice would inflate its dose.
    """
    from rhome_core.exercises import _resolve_tiers

    primary, secondary, stabiliser, collisions = _resolve_tiers(
        (Muscle.UPPER_BACK,),
        (Muscle.POSTERIOR_DELTS, Muscle.BICEPS),
        (Muscle.POSTERIOR_DELTS, Muscle.FOREARMS),
    )
    assert collisions == 1
    assert Muscle.POSTERIOR_DELTS in secondary, "the higher tier must win"
    assert Muscle.POSTERIOR_DELTS not in stabiliser, "and must not also remain below"
    assert stabiliser == (Muscle.FOREARMS,)
    assert primary == (Muscle.UPPER_BACK,)

    # A muscle named primary outranks the same muscle named anywhere lower.
    primary, secondary, stabiliser, collisions = _resolve_tiers(
        (Muscle.ABS,), (Muscle.ABS,), (Muscle.ABS,)
    )
    assert (primary, secondary, stabiliser) == ((Muscle.ABS,), (), ())
    assert collisions == 2


@pytest.mark.spec("DATA:library-labels-fold-to-model-groups")
def test_the_fold_does_not_touch_the_v0_library():
    """The v0 dataset is pinned to the v0 library, so the fold must be inert there.

    If this ever fails, the synthetic dataset every Layer 3 number was measured
    against has silently changed.
    """
    import csv as _csv

    from rhome_core.exercises import _muscles, _resolve_tiers, library_path

    collisions = 0
    with library_path().open(encoding="utf-8") as handle:
        for row in _csv.DictReader(handle):
            *_, collided = _resolve_tiers(
                _muscles(row["primary_muscles"]),
                _muscles(row["secondary_muscles"]),
                _muscles(row["stabiliser_muscles"]),
            )
            collisions += collided
    assert collisions == 0, (
        f"{collisions} tier collisions in the v0 library; the fold is no longer "
        f"a no-op there and the pinned dataset may have changed"
    )
