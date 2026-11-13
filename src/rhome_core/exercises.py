"""Exercise library (``DATA.md`` §5.4, §8).

Rhome maintains its own exercise database in two layers.

The **base layer** --- name, movement pattern, equipment, muscle tags --- is
commodity data and could be seeded from any standard exercise list.

The **scoring layer** --- the contribution vectors, compoundness, systemic cost
and bodyweight fraction --- is specific to this model. It is what converts a
logged movement into a dose, and no external database provides it.

A great deal of the model's behaviour is decided here rather than in any
equation. Whether a Romanian deadlift loads the hamstrings at 1.0 and the
erectors at 0.5, and whether it costs 0.88 systemically or 0.60, matters more
to the output than most of the coefficients in ``MODEL.tex``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from rhome_core.parameters import CORE_PARAMETERS
from rhome_core.muscles import Muscle, Region, REGION_OF, resolve_display_label

__all__ = [
    "MovementPattern",
    "Equipment",
    "ExerciseKind",
    "NuzzoCurve",
    "CoefficientSource",
    "Exercise",
    "ExerciseLibrary",
    "load_library",
    "library_path",
    "LibraryPin",
    "library_pin",
    "KNOWN_LIBRARIES",
    "DOSE_BEARING_KINDS",
]


class MovementPattern(StrEnum):
    SQUAT = "squat"
    HINGE = "hinge"
    LUNGE = "lunge"
    VERTICAL_PRESS = "vertical_press"
    HORIZONTAL_PRESS = "horizontal_press"
    VERTICAL_PULL = "vertical_pull"
    HORIZONTAL_PULL = "horizontal_pull"
    ISOLATION = "isolation"
    ROTATION = "rotation"


class Equipment(StrEnum):
    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    MACHINE = "machine"
    CABLE = "cable"
    BODYWEIGHT = "bodyweight"


class ExerciseKind(StrEnum):
    """Measurement form (``DATA.md`` §5.4.1)."""

    WEIGHTED_REPS = "weighted_reps"
    REPS_ONLY = "reps_only"
    ASSISTED_REPS = "assisted_reps"
    TIME_ONLY = "time_only"
    WEIGHT_TIME = "weight_time"
    WEIGHT_DISTANCE = "weight_distance"
    DISTANCE_TIME = "distance_time"


#: Kinds that produce impulses in the four dose channels. The others are
#: recorded and shown in the log, but the relative-intensity mapping is defined
#: on repetitions and cannot be stretched to cover a plank or a run.
DOSE_BEARING_KINDS = frozenset(
    {ExerciseKind.WEIGHTED_REPS, ExerciseKind.REPS_ONLY, ExerciseKind.ASSISTED_REPS}
)


class NuzzoCurve(StrEnum):
    GENERAL = "general"
    BENCH = "bench"
    LEG_PRESS = "leg_press"


class CoefficientSource(StrEnum):
    CURATED = "curated"
    DERIVED = "derived"


@dataclass(frozen=True)
class Exercise:
    """One exercise, base layer and scoring layer together."""

    exercise_id: str
    name: str
    movement_pattern: MovementPattern
    equipment: Equipment
    exercise_kind: ExerciseKind
    primary_muscles: tuple[Muscle, ...]
    secondary_muscles: tuple[Muscle, ...]
    stabiliser_muscles: tuple[Muscle, ...]
    compoundness: float
    systemic_cost: float
    bodyweight_fraction: float | None
    axial_load: float | None
    eccentric_demand: float | None
    nuzzo_curve: NuzzoCurve
    unilateral: bool
    coefficient_source: CoefficientSource
    # Read from the registry rather than written here. These three were
    # inline literals until L2.7, which meant Guardrail 3 was verifying values
    # against MODEL.tex that the contribution matrix never consulted: an edit
    # to the literal would have left the registry, the document and the test
    # all agreeing with each other and disagreeing with the code.
    stimulus_primary_coeff: float = CORE_PARAMETERS.value("stimulus_primary_coeff")
    stimulus_secondary_coeff: float = CORE_PARAMETERS.value("stimulus_secondary_coeff")
    fatigue_stabiliser_coeff: float = CORE_PARAMETERS.value("fatigue_stabiliser_coeff")

    def __post_init__(self) -> None:
        for name_, value in (
            ("compoundness", self.compoundness),
            ("systemic_cost", self.systemic_cost),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{self.exercise_id}: {name_} must be in [0,1], got {value}")
        for name_, value in (
            ("bodyweight_fraction", self.bodyweight_fraction),
            ("axial_load", self.axial_load),
            ("eccentric_demand", self.eccentric_demand),
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{self.exercise_id}: {name_} must be in [0,1], got {value}")
        if not self.primary_muscles:
            raise ValueError(f"{self.exercise_id}: at least one primary muscle is required")

        overlap = (
            (set(self.primary_muscles) & set(self.secondary_muscles))
            | (set(self.primary_muscles) & set(self.stabiliser_muscles))
            | (set(self.secondary_muscles) & set(self.stabiliser_muscles))
        )
        if overlap:
            raise ValueError(
                f"{self.exercise_id}: muscle in more than one tier: "
                f"{sorted(m.value for m in overlap)}"
            )
        if self.requires_bodyweight and self.bodyweight_fraction is None:
            raise ValueError(
                f"{self.exercise_id}: kind {self.exercise_kind.value} needs a "
                f"bodyweight_fraction"
            )

    @property
    def requires_bodyweight(self) -> bool:
        return self.exercise_kind in {ExerciseKind.REPS_ONLY, ExerciseKind.ASSISTED_REPS}

    @property
    def bears_dose(self) -> bool:
        """Whether this exercise contributes to the four dose channels."""
        return self.exercise_kind in DOSE_BEARING_KINDS

    @property
    def stimulus_contributions(self) -> dict[Muscle, float]:
        """The ``c^S`` vector. Stabilisers earn no adaptive credit.

        The zero is read rather than expressed by leaving stabilisers out.
        Omission encodes the same behaviour but makes the value unfalsifiable:
        the registry would claim 0.00 and the documents would agree, and
        neither would be connected to anything.
        """
        stabiliser = CORE_PARAMETERS.value("stimulus_stabiliser_coeff")
        return {
            **{m: self.stimulus_primary_coeff for m in self.primary_muscles},
            **{m: self.stimulus_secondary_coeff for m in self.secondary_muscles},
            **({m: stabiliser for m in self.stabiliser_muscles} if stabiliser else {}),
        }

    @property
    def fatigue_contributions(self) -> dict[Muscle, float]:
        """The ``c^F`` vector. Stabilisers do accrue fatigue."""
        return {
            **{m: self.stimulus_primary_coeff for m in self.primary_muscles},
            **{m: self.stimulus_secondary_coeff for m in self.secondary_muscles},
            **{m: self.fatigue_stabiliser_coeff for m in self.stabiliser_muscles},
        }

    @property
    def performance_weights(self) -> dict[Muscle, float]:
        """``omega_me``: the fatigue vector normalised to unit sum.

        The fatigue vector is used rather than the stimulus vector because
        performance is limited by fatigue anywhere in the chain, stabilisers
        included: grip fatigue limits a deadlift even though the grip receives
        no hypertrophic credit for the set.
        """
        contributions = self.fatigue_contributions
        total = sum(contributions.values())
        return {m: c / total for m, c in contributions.items()}

    @property
    def regions(self) -> frozenset[Region]:
        """Regions this exercise loads, by primary muscles only."""
        return frozenset(REGION_OF[m] for m in self.primary_muscles)


def library_path() -> Path:
    """The curated library, a committed source artefact rather than output."""
    return Path(__file__).resolve().parents[2] / "data" / "exercises" / "exercise_library.csv"


# --- library versioning (L3.9) ----------------------------------------------
# The library is an input to dataset generation, and ``generation_config.json``
# pinned the seed, the commit and every simulator constant but not this. That
# gap is not benign: nineteen of the twenty-seven v0 exercise ids do not exist
# in the athlete-authored v1 library — ``bench_press`` became
# ``barbell_bench_press`` — so exchanging the file does not perturb a dataset,
# it invalidates it, and nothing in the artefact would have said which library
# produced it.
#
# The pin is content-addressed rather than declared, for the reason the frozen
# projections are: a version string a human maintains is a version string that
# eventually lies. A digest cannot.

_LIBRARY_REGISTRY = Path(__file__).resolve().parents[2] / "data" / "exercises" / "LIBRARIES.json"


@dataclass(frozen=True)
class LibraryPin:
    """Which library a dataset was generated against, and proof of it."""

    version: str
    filename: str
    digest: str
    exercises: int

    @property
    def is_registered(self) -> bool:
        return self.version != "unregistered"

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "filename": self.filename,
            "sha256": self.digest,
            "exercises": self.exercises,
        }

    def matches(self, other: "LibraryPin | dict") -> bool:
        """Digest equality. A pin agrees with another only byte for byte."""
        digest = other["sha256"] if isinstance(other, dict) else other.digest
        return self.digest == digest


def known_libraries() -> dict[str, dict]:
    """The registered library versions, by version string."""
    if not _LIBRARY_REGISTRY.exists():
        return {}
    return json.loads(_LIBRARY_REGISTRY.read_text(encoding="utf-8"))


#: Read once at import for convenience; ``known_libraries()`` re-reads.
KNOWN_LIBRARIES = known_libraries()


def library_pin(path: Path | None = None) -> LibraryPin:
    """Identify a library file by its content.

    An unregistered digest is reported as ``unregistered`` rather than raising.
    Refusing to load an unknown library would make authoring one impossible;
    reporting it as unknown makes an unpinned library visible the moment it
    reaches a dataset, which is where it matters.
    """
    path = path or library_path()
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    rows = sum(1 for _ in csv.DictReader(io.StringIO(payload.decode("utf-8"))))
    for version, entry in known_libraries().items():
        if entry.get("sha256") == digest:
            return LibraryPin(version, path.name, digest, rows)
    return LibraryPin("unregistered", path.name, digest, rows)


def _muscles(cell: str) -> tuple[Muscle, ...]:
    if not cell.strip():
        return ()
    return tuple(resolve_display_label(part.strip()) for part in cell.split("|") if part.strip())


def _resolve_tiers(
    primary: tuple[Muscle, ...],
    secondary: tuple[Muscle, ...],
    stabiliser: tuple[Muscle, ...],
) -> tuple[tuple[Muscle, ...], tuple[Muscle, ...], tuple[Muscle, ...], int]:
    """Keep the highest tier when the D16 fold collapses two labels into one.

    A consequence of D16 that only appears once a library using the finer
    labels is actually loaded, and it appears in **302 of the athlete's 1074
    rows**. ``bent_over_barbell_row`` lists ``posterior_delts`` as a secondary
    mover and ``rotator_cuff`` as a stabiliser; both fold to
    ``posterior_delts``, and the exercise then holds one muscle in two tiers —
    which ``Exercise.__post_init__`` rejects, correctly, because for a
    hand-authored library that is a genuine authoring error.

    So the collision is resolved here, before the ``Exercise`` is built, rather
    than by weakening the invariant. **The highest tier wins**: a muscle named
    as a primary or secondary mover is not demoted because a finer label for
    the same group also appeared lower down.

    Taking the maximum rather than the sum is the conservative direction. The
    row above contributes the secondary coefficient (0.50) rather than
    secondary plus stabiliser (0.50 + 0.20); adding them would count one
    anatomical structure twice because the library happened to name it twice.
    The cost is a small understatement of fatigue on exactly the exercises
    where a folded label sits below a real one, and it is recorded as such.
    """
    claimed: set[Muscle] = set()
    resolved: list[tuple[Muscle, ...]] = []
    collisions = 0
    for tier in (primary, secondary, stabiliser):
        kept: list[Muscle] = []
        for muscle in tier:
            if muscle in claimed:
                collisions += 1
                continue
            claimed.add(muscle)
            kept.append(muscle)
        resolved.append(tuple(kept))
    return resolved[0], resolved[1], resolved[2], collisions


def _optional_float(cell: str) -> float | None:
    return float(cell) if cell.strip() else None


@dataclass(frozen=True)
class ExerciseLibrary:
    """An immutable collection of exercises, indexed by id."""

    exercises: MappingProxyType[str, Exercise]
    #: Which library file this was loaded from, content-addressed (L3.9).
    #: Carried on the library rather than looked up from the default path,
    #: so a simulation run against a non-default library cannot be recorded
    #: as having used the default one.
    pin: "LibraryPin | None" = None

    def __getitem__(self, exercise_id: str) -> Exercise:
        try:
            return self.exercises[exercise_id]
        except KeyError:
            raise KeyError(f"no such exercise: {exercise_id!r}") from None

    def __len__(self) -> int:
        return len(self.exercises)

    def __iter__(self):
        return iter(self.exercises.values())

    def __contains__(self, exercise_id: object) -> bool:
        return exercise_id in self.exercises

    def covered_muscles(self) -> frozenset[Muscle]:
        """Every muscle receiving load from some exercise, at any tier."""
        covered: set[Muscle] = set()
        for exercise in self:
            covered |= set(exercise.fatigue_contributions)
        return frozenset(covered)

    def by_region(self, region: Region) -> tuple[Exercise, ...]:
        return tuple(e for e in self if region in e.regions)


def load_library(path: Path | None = None) -> ExerciseLibrary:
    """Load and validate the exercise library from CSV."""
    path = path or library_path()
    exercises: dict[str, Exercise] = {}
    folded = 0

    with path.open(encoding="utf-8", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            exercise_id = row["exercise_id"].strip()
            if not exercise_id:
                raise ValueError(f"{path}:{line_number}: missing exercise_id")
            if exercise_id in exercises:
                raise ValueError(f"{path}:{line_number}: duplicate exercise_id {exercise_id!r}")
            try:
                primary, secondary, stabiliser, collided = _resolve_tiers(
                    _muscles(row["primary_muscles"]),
                    _muscles(row["secondary_muscles"]),
                    _muscles(row["stabiliser_muscles"]),
                )
                folded += collided
                exercises[exercise_id] = Exercise(
                    exercise_id=exercise_id,
                    name=row["name"].strip(),
                    movement_pattern=MovementPattern(row["movement_pattern"].strip()),
                    equipment=Equipment(row["equipment"].strip()),
                    exercise_kind=ExerciseKind(row["exercise_kind"].strip()),
                    primary_muscles=primary,
                    secondary_muscles=secondary,
                    stabiliser_muscles=stabiliser,
                    compoundness=float(row["compoundness"]),
                    systemic_cost=float(row["systemic_cost"]),
                    bodyweight_fraction=_optional_float(row["bodyweight_fraction"]),
                    axial_load=_optional_float(row["axial_load"]),
                    eccentric_demand=_optional_float(row["eccentric_demand"]),
                    nuzzo_curve=NuzzoCurve(row["nuzzo_curve"].strip()),
                    unilateral=row["unilateral"].strip().lower() == "true",
                    coefficient_source=CoefficientSource(row["coefficient_source"].strip()),
                )
            except (ValueError, KeyError) as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error

    if not exercises:
        raise ValueError(f"{path}: library is empty")
    return ExerciseLibrary(MappingProxyType(exercises), pin=library_pin(path))
