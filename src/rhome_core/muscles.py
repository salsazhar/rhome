"""Muscle taxonomy (``DATA.md`` §7).

Rhome uses two levels of taxonomy, and the separation is a claim boundary
rather than a convenience.

The **model layer** is sixteen groups. Every latent state, contribution vector
and stored value is keyed by these identifiers.

The **display layer** is finer, because lifters think in terms of upper chest,
traps, obliques and grip. It maps many-to-one onto the model groups.

The model layer is deliberately coarser because the evidence underneath this
model is reported per muscle group, never per region. Nothing in it supports
treating upper-chest fatigue as a state distinct from lower-chest fatigue, so
Rhome does not offer one. Athletes log at the granularity they think in; the
model claims only what it can defend.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from rhome_core.parameters import CORE_PARAMETERS

__all__ = [
    "Muscle",
    "Region",
    "REGION_OF",
    "DISPLAY_TO_MODEL",
    "MASS_WEIGHT",
    "resolve_display_label",
    "muscles_in_region",
    "display_labels_for",
    "LIBRARY_LABEL_TO_MODEL",
    "library_labels_for",
]


class Region(StrEnum):
    """Anatomical region, used for the upper/lower parity requirement."""

    UPPER = "upper"
    CORE = "core"
    LOWER = "lower"


class Muscle(StrEnum):
    """The sixteen model groups."""

    # Upper body (9)
    CHEST = "chest"
    LATS = "lats"
    UPPER_BACK = "upper_back"
    ANTERIOR_DELTS = "anterior_delts"
    LATERAL_DELTS = "lateral_delts"
    POSTERIOR_DELTS = "posterior_delts"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"
    # Core (1)
    ABS = "abs"
    # Lower body (6)
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    ADDUCTORS = "adductors"
    SPINAL_ERECTORS = "spinal_erectors"


REGION_OF: MappingProxyType[Muscle, Region] = MappingProxyType(
    {
        Muscle.CHEST: Region.UPPER,
        Muscle.LATS: Region.UPPER,
        Muscle.UPPER_BACK: Region.UPPER,
        Muscle.ANTERIOR_DELTS: Region.UPPER,
        Muscle.LATERAL_DELTS: Region.UPPER,
        Muscle.POSTERIOR_DELTS: Region.UPPER,
        Muscle.BICEPS: Region.UPPER,
        Muscle.TRICEPS: Region.UPPER,
        Muscle.FOREARMS: Region.UPPER,
        Muscle.ABS: Region.CORE,
        Muscle.QUADS: Region.LOWER,
        Muscle.HAMSTRINGS: Region.LOWER,
        Muscle.GLUTES: Region.LOWER,
        Muscle.CALVES: Region.LOWER,
        Muscle.ADDUCTORS: Region.LOWER,
        Muscle.SPINAL_ERECTORS: Region.LOWER,
    }
)

#: Display label -> model group (``DATA.md`` §7.2). Many-to-one by design.
#: Adding a label here is a data change requiring no model change.
DISPLAY_TO_MODEL: MappingProxyType[str, Muscle] = MappingProxyType(
    {
        "Upper Chest": Muscle.CHEST,
        "Mid Chest": Muscle.CHEST,
        "Lower Chest": Muscle.CHEST,
        "Lats": Muscle.LATS,
        "Upper Back": Muscle.UPPER_BACK,
        "Trapezius": Muscle.UPPER_BACK,
        "Rhomboids": Muscle.UPPER_BACK,
        "Lower Back": Muscle.SPINAL_ERECTORS,
        "Front Delts": Muscle.ANTERIOR_DELTS,
        "Side Delts": Muscle.LATERAL_DELTS,
        "Rear Delts": Muscle.POSTERIOR_DELTS,
        "Biceps": Muscle.BICEPS,
        "Triceps": Muscle.TRICEPS,
        "Forearms": Muscle.FOREARMS,
        "Grip": Muscle.FOREARMS,
        "Upper Abs": Muscle.ABS,
        "Lower Abs": Muscle.ABS,
        "Obliques": Muscle.ABS,
        "Glutes": Muscle.GLUTES,
        "Hip Abductors": Muscle.GLUTES,
        "Quadriceps": Muscle.QUADS,
        "Hamstrings": Muscle.HAMSTRINGS,
        "Calves": Muscle.CALVES,
        "Adductors": Muscle.ADDUCTORS,
    }
)

#: Relative muscle mass weights, used only to modulate derived systemic cost
#: (``MODEL.tex`` §Derived coefficients). Engineering priors reflecting gross
#: segmental distribution, not measured cross-sectional areas.
MASS_WEIGHT: MappingProxyType[Muscle, float] = MappingProxyType(
    {
        Muscle.QUADS: 1.00,
        Muscle.GLUTES: 0.90,
        Muscle.HAMSTRINGS: 0.70,
        Muscle.LATS: 0.70,
        Muscle.CHEST: 0.60,
        Muscle.SPINAL_ERECTORS: 0.55,
        Muscle.UPPER_BACK: 0.55,
        Muscle.ADDUCTORS: 0.50,
        Muscle.ABS: 0.35,
        Muscle.CALVES: 0.25,
        Muscle.TRICEPS: 0.22,
        Muscle.ANTERIOR_DELTS: 0.20,
        Muscle.BICEPS: 0.15,
        Muscle.LATERAL_DELTS: 0.12,
        Muscle.POSTERIOR_DELTS: 0.12,
        Muscle.FOREARMS: 0.10,
    }
)


#: Muscle labels the athlete-authored library uses that the model taxonomy does
#: not have (D16, implemented at L3.9).
#:
#: The alternative was adding model groups. It was rejected for the reason that
#: settled the single ``abs`` group: the sixteen exist because the evidence in
#: ``RESEARCH.md`` is reported at that resolution, and a seventeenth would be
#: pure Grade C — a dimension the research specification can say nothing about,
#: added because a label existed.
#:
#: **The cost, stated plainly and not buried:** neck work reads as upper-back
#: fatigue and tibialis work as calf fatigue. Both are low-volume and
#: low-systemic, so the error is small, but it is an error rather than a
#: modelling choice that could be defended on physiology. `LIM-11` carries it.
#:
#: The finer label is not lost. It is preserved here and recoverable through
#: ``library_labels_for``, which is what the two-level taxonomy was built for.
LIBRARY_LABEL_TO_MODEL: MappingProxyType[str, Muscle] = MappingProxyType(
    {
        # Trunk. 868 uses of `core`, stabiliser in nearly all of them.
        "core": Muscle.ABS,
        "deep_core": Muscle.ABS,
        # Scapular and upper-back work the taxonomy folds together.
        "traps": Muscle.UPPER_BACK,
        "serratus": Muscle.UPPER_BACK,
        "neck": Muscle.UPPER_BACK,
        # 466 uses, 13 of them as a primary muscle.
        "rotator_cuff": Muscle.POSTERIOR_DELTS,
        # Rectus femoris is both a hip flexor and a knee extensor.
        "hip_flexors": Muscle.QUADS,
        # Lower leg.
        "tibialis": Muscle.CALVES,
        "foot_ankle_stabilisers": Muscle.CALVES,
        # Our own display label in a different spelling; "Hip Abductors" does
        # not slugify to "abductors", so it needs saying explicitly.
        "abductors": Muscle.GLUTES,
    }
)


def _normalise_label(label: str) -> str:
    """Compare labels insensitively to spelling: case, spacing and separators.

    D16 observed that three of the twelve unmatched labels in the athlete's
    library are our *own* display labels in a different spelling —
    ``upper_chest`` for "Upper Chest". Those need no mapping at all, only a
    lookup that does not care which spelling it is handed.
    """
    return label.strip().lower().replace("-", " ").replace("_", " ")


_NORMALISED_DISPLAY: dict[str, Muscle] = {
    _normalise_label(label): muscle for label, muscle in DISPLAY_TO_MODEL.items()
}


def resolve_display_label(label: str) -> Muscle:
    """Resolve a display or library label to its model group.

    Accepts a display label ("Upper Chest"), the same label in slug spelling
    ("upper_chest"), a model identifier ("chest"), or one of the finer labels
    the athlete's library uses ("rotator_cuff").

    An unrecognised label still raises. Resolving the unknown to a plausible
    neighbour is how a taxonomy silently acquires whatever anyone types.
    """
    if label in DISPLAY_TO_MODEL:
        return DISPLAY_TO_MODEL[label]
    try:
        return Muscle(label)
    except ValueError:
        pass
    normalised = _normalise_label(label)
    if normalised in _NORMALISED_DISPLAY:
        return _NORMALISED_DISPLAY[normalised]
    if label.strip() in LIBRARY_LABEL_TO_MODEL:
        return LIBRARY_LABEL_TO_MODEL[label.strip()]
    raise KeyError(
        f"unknown muscle label {label!r}; expected a display label from "
        f"DATA.md §7.2, a model group identifier, or one of the library "
        f"labels D16 maps: {sorted(LIBRARY_LABEL_TO_MODEL)}"
    )


def muscles_in_region(region: Region) -> tuple[Muscle, ...]:
    """The model groups belonging to one region."""
    return tuple(m for m in Muscle if REGION_OF[m] is region)


def display_labels_for(muscle: Muscle) -> tuple[str, ...]:
    """Every display label that resolves to this model group."""
    return tuple(
        label for label, target in DISPLAY_TO_MODEL.items() if target is muscle
    )


def library_labels_for(muscle: Muscle) -> tuple[str, ...]:
    """Every finer library label folded into this model group (D16).

    The display layer reads this. D16's commitment was that folding twelve
    labels into the sixteen groups loses resolution in the *model* and not in
    what the athlete is shown, and that only holds if the finer label remains
    recoverable.
    """
    return tuple(
        label for label, target in LIBRARY_LABEL_TO_MODEL.items() if target is muscle
    )


# The documented group count is not decoration: it is checked against the enum
# at import, so a muscle added without updating DATA.md fails immediately
# rather than leaving the specification quietly wrong.
_DOCUMENTED_GROUPS = CORE_PARAMETERS.value("model_muscle_group_count")
if len(Muscle) != _DOCUMENTED_GROUPS:
    raise RuntimeError(
        f"{len(Muscle)} model muscle groups defined but DATA.md §7.1 "
        f"documents {_DOCUMENTED_GROUPS}"
    )
