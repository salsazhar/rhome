"""Reading observable data (``DATA.md`` §5, §17).

The engine reads what a real application could collect: logged sets, session
metadata, exercise definitions and nightly wearable summaries. It never reads
the simulator's latent tables, and Guardrail 1 scans this package's source to
enforce that.

Real ingestion meets malformed rows, and this module distinguishes two cases.
A **defect** is unrecoverable — a negative load, an unknown exercise — and the
row is rejected with a stated reason. A **repair** has exactly one sensible
reading — a repetition count written as ``5.0``, a categorical padded with
whitespace — and is corrected, with the correction recorded.

The distinction matters because silently coercing a bad row is how a parser
turns a data-entry error into a physiological claim. Nothing here guesses.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field, replace
from pathlib import Path

from rhome_core.exercises import ExerciseLibrary
from rhome_engine.dose import LoggedSet

__all__ = ["IngestIssue", "IngestResult", "parse_sets", "load_sets"]

#: Absolute bounds. These reject the physically impossible only; anything
#: requiring the athlete's history belongs where capacity is known.
_MAX_LOAD_KG = 500.0
_MAX_REPS = 100
_VALID_SET_TYPES = frozenset({"warmup", "working", "backoff", "drop"})

#: The effort bounds are *derived* from the documented reserve range rather
#: than chosen. ``MODEL.tex`` §From RPE to RIR clips logged repetitions in
#: reserve to [0, 8], so the corresponding RPE range is [2, 10] and nothing
#: narrower may be rejected. An earlier version of this parser used an invented
#: floor of RPE 4 and threw away 29 legitimate sets from the clean dataset,
#: which is what happens when a bound is picked by intuition instead of taken
#: from the specification that already defines it.
_MAX_RIR = 8.0
_MAX_RPE = 10.0
_MIN_RPE = _MAX_RPE - _MAX_RIR


@dataclass(frozen=True)
class IngestIssue:
    """One row that was rejected or repaired, and why."""

    row_number: int
    outcome: str  # "rejected" | "repaired"
    reason: str
    field_name: str | None = None


@dataclass
class IngestResult:
    sets: list[LoggedSet] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)

    @property
    def rejected(self) -> list[IngestIssue]:
        return [i for i in self.issues if i.outcome == "rejected"]

    @property
    def repaired(self) -> list[IngestIssue]:
        return [i for i in self.issues if i.outcome == "repaired"]


def _clean_text(value) -> str:
    return str(value if value is not None else "").strip().lower()


def _optional_number(value):
    if value in (None, "", "None"):
        return None
    return float(value)


def parse_sets(rows, library: ExerciseLibrary) -> IngestResult:
    """Parse logged set rows, rejecting what cannot be trusted."""
    result = IngestResult()
    seen: dict[tuple[str, str], set[int]] = {}

    for number, row in enumerate(rows, start=2):
        def reject(reason: str, field_name: str | None = None):
            result.issues.append(IngestIssue(number, "rejected", reason, field_name))

        def repair(reason: str, field_name: str | None = None):
            result.issues.append(IngestIssue(number, "repaired", reason, field_name))

        workout_id = str(row.get("workout_id") or "").strip()
        if not workout_id:
            reject("missing workout identifier", "workout_id")
            continue

        exercise_id = str(row.get("exercise_id") or "").strip()
        if exercise_id not in library:
            reject(f"unknown exercise {exercise_id!r}", "exercise_id")
            continue

        set_type = _clean_text(row.get("set_type"))
        if set_type != str(row.get("set_type") or ""):
            repair("set type normalised for whitespace and casing", "set_type")
        if set_type not in _VALID_SET_TYPES:
            reject(f"unknown set type {set_type!r}", "set_type")
            continue

        try:
            raw_load = row.get("external_load_kg")
            load = float(raw_load)
        except (TypeError, ValueError):
            reject(f"load is not numeric: {row.get('external_load_kg')!r}", "external_load_kg")
            continue
        if load < 0 and library[exercise_id].exercise_kind.value != "assisted_reps":
            reject(f"negative load {load}", "external_load_kg")
            continue
        if abs(load) > _MAX_LOAD_KG:
            reject(f"load {load} kg is beyond any human capacity", "external_load_kg")
            continue

        try:
            raw_reps = row.get("reps")
            reps_float = float(raw_reps)
        except (TypeError, ValueError):
            reject(f"repetitions are not numeric: {row.get('reps')!r}", "reps")
            continue
        if reps_float != int(reps_float):
            reject(f"fractional repetitions {reps_float}", "reps")
            continue
        reps = int(reps_float)
        if isinstance(raw_reps, float) or (isinstance(raw_reps, str) and "." in raw_reps):
            repair("repetition count written as a decimal", "reps")
        if reps < 1:
            reject(f"a set must have at least one repetition, got {reps}", "reps")
            continue
        if reps > _MAX_REPS:
            reject(f"{reps} repetitions is beyond any plausible set", "reps")
            continue

        try:
            rpe = _optional_number(row.get("rpe"))
            rir = _optional_number(row.get("rir"))
        except (TypeError, ValueError):
            reject("effort is not numeric", "rpe")
            continue

        if rpe is not None and not _MIN_RPE <= rpe <= _MAX_RPE:
            reject(f"RPE {rpe} is outside the working range", "rpe")
            continue
        if rir is not None and not 0.0 <= rir <= _MAX_RIR:
            reject(f"repetitions in reserve {rir} is outside the plausible range", "rir")
            continue

        if rpe is not None and rir is not None and abs((10.0 - rpe) - rir) > 0.51:
            # DATA.md §5.3 makes RIR the primary field, so it wins.
            repair(
                f"RPE {rpe} and RIR {rir} disagree; RIR taken as authoritative",
                "rpe",
            )
            rpe = None

        set_number = int(float(row.get("set_number") or 0))
        key = (workout_id, exercise_id)
        used = seen.setdefault(key, set())
        if set_number in used or set_number < 1:
            set_number = max(used, default=0) + 1
            repair("duplicate or missing set number reassigned", "set_number")
        used.add(set_number)

        result.sets.append(
            LoggedSet(
                workout_id=workout_id,
                exercise_id=exercise_id,
                set_number=set_number,
                set_type=set_type,
                load_kg=load,
                reps=reps,
                rpe=rpe,
                rir=rir,
                is_pr=_clean_text(row.get("is_pr")) == "true",
            )
        )
    return result


def load_sets(path: Path, library: ExerciseLibrary) -> IngestResult:
    """Read ``sets.csv`` from the observable directory."""
    with path.open(encoding="utf-8", newline="") as handle:
        return parse_sets(list(csv.DictReader(handle)), library)
