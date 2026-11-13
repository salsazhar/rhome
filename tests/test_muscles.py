"""Muscle taxonomy (``DATA.md`` §7)."""

from __future__ import annotations

import pytest

from rhome_core.muscles import (
    DISPLAY_TO_MODEL,
    MASS_WEIGHT,
    REGION_OF,
    Muscle,
    Region,
    display_labels_for,
    muscles_in_region,
    resolve_display_label,
)


@pytest.mark.spec("DATA:sixteen-model-groups")
def test_there_are_sixteen_model_groups():
    assert len(list(Muscle)) == 16


@pytest.mark.spec("DATA:sixteen-model-groups")
def test_region_composition_matches_the_specification():
    assert len(muscles_in_region(Region.UPPER)) == 9
    assert len(muscles_in_region(Region.CORE)) == 1
    assert len(muscles_in_region(Region.LOWER)) == 6


def test_abs_is_a_model_group():
    """Absent from the taxonomy until docs v0.3; a real gap for a training log."""
    assert Muscle.ABS in Muscle
    assert REGION_OF[Muscle.ABS] is Region.CORE


def test_every_muscle_has_exactly_one_region():
    assert set(REGION_OF) == set(Muscle)


@pytest.mark.spec("DATA:display-taxonomy-maps-to-model")
def test_every_display_label_resolves_to_a_model_group():
    for label, muscle in DISPLAY_TO_MODEL.items():
        assert isinstance(muscle, Muscle), f"{label} maps outside the model taxonomy"


@pytest.mark.spec("DATA:display-taxonomy-maps-to-model")
@pytest.mark.parametrize(
    "labels, expected",
    [
        (["Upper Chest", "Mid Chest", "Lower Chest"], Muscle.CHEST),
        (["Upper Abs", "Lower Abs", "Obliques"], Muscle.ABS),
        (["Upper Back", "Trapezius", "Rhomboids"], Muscle.UPPER_BACK),
        (["Forearms", "Grip"], Muscle.FOREARMS),
        (["Glutes", "Hip Abductors"], Muscle.GLUTES),
        (["Lower Back"], Muscle.SPINAL_ERECTORS),
    ],
)
def test_regional_labels_collapse_to_one_group(labels, expected):
    """The claim boundary in code: no regional resolution within a group."""
    assert {resolve_display_label(label) for label in labels} == {expected}


def test_display_taxonomy_is_finer_than_the_model():
    assert len(DISPLAY_TO_MODEL) > len(list(Muscle))


def test_display_taxonomy_covers_every_model_group():
    """No model group may be unreachable from the interface."""
    reachable = set(DISPLAY_TO_MODEL.values())
    missing = set(Muscle) - reachable
    assert not missing, f"unreachable from the display layer: {sorted(m.value for m in missing)}"


def test_model_identifiers_resolve_to_themselves():
    for muscle in Muscle:
        assert resolve_display_label(muscle.value) is muscle


def test_unknown_label_is_rejected_with_a_useful_message():
    with pytest.raises(KeyError, match="unknown muscle label"):
        resolve_display_label("Pectoralis Minor")


def test_display_labels_for_round_trips():
    for muscle in Muscle:
        for label in display_labels_for(muscle):
            assert resolve_display_label(label) is muscle


def test_every_muscle_has_a_mass_weight_in_range():
    assert set(MASS_WEIGHT) == set(Muscle)
    assert all(0.0 < w <= 1.0 for w in MASS_WEIGHT.values())


def test_mass_weights_rank_plausibly():
    """Sanity ordering: a coding error here would silently distort derived cost."""
    assert MASS_WEIGHT[Muscle.QUADS] > MASS_WEIGHT[Muscle.CHEST]
    assert MASS_WEIGHT[Muscle.GLUTES] > MASS_WEIGHT[Muscle.BICEPS]
    assert MASS_WEIGHT[Muscle.LATS] > MASS_WEIGHT[Muscle.FOREARMS]
    assert MASS_WEIGHT[Muscle.HAMSTRINGS] > MASS_WEIGHT[Muscle.CALVES]
    assert MASS_WEIGHT[Muscle.QUADS] == max(MASS_WEIGHT.values())


def test_taxonomy_is_immutable():
    with pytest.raises(TypeError):
        DISPLAY_TO_MODEL["Pecs"] = Muscle.CHEST  # type: ignore[index]
    with pytest.raises(TypeError):
        MASS_WEIGHT[Muscle.CHEST] = 9.0  # type: ignore[index]
