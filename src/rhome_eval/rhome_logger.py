"""Reading Rhome's own logger into the engine's schema (L6.2).

The counterpart to :mod:`rhome_eval.spotr`, and deliberately much smaller.
Where the Spotr adapter had to reconcile a foreign vocabulary, infer set types
from a single drop-set marker and recover a gym from recollection, this one
reads a file the app wrote against the engine's own definitions.

**No name resolution, ever.** The logger stores library identifiers chosen from
the bundled library, so an exercise either resolves or the file is wrong. There
is no fuzzy matching here and there must never be: matching at read time is
matching with the athlete's results in view, which is what the frozen L3.10
mapping exists to prevent. An unknown id raises.

**Exports are cumulative, not incremental.** The app writes every finished
session each time, so two exports a fortnight apart overlap almost entirely.
Sessions are keyed by their UUID and the *latest* export of a session wins —
that is what makes a correction on the phone reach the engine, and what stops a
re-export from double-counting a month of training.

**Equipment context arrives as logged.** ``PRODUCT.md`` §7.1 leaves granularity
to the athlete: where a gym's cables share one weighting, one label for the
building is correct, and where two machines disagree the station is. The
adapter records the label and forms no opinion about which case it is in.

**Recovery is not in this file.** The logger captures training only; nightly
physiology still arrives from the Oura export through the existing path. A day
with no reading gets an empty one rather than an invented one.

**One known imprecision.** Timestamps are exported in UTC, and the day a
session belongs to is taken from that instant. A session spanning local
midnight could therefore land a day either side of where the athlete would put
it. Recorded rather than silently corrected, because the fix is a timezone the
export does not yet carry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from rhome_core.exercises import ExerciseLibrary
from rhome_engine.dose import LoggedSet
from rhome_engine.session import DayInput
from rhome_engine.recovery import RecoveryReading

#: Schema versions this adapter understands. A file announcing anything else
#: is refused rather than parsed hopefully.
SUPPORTED_SCHEMAS = frozenset({"rhome-logger/1"})

#: Set types the logger may emit, matching ``rhome_engine.ingest``. The app was
#: written against this vocabulary, so a mismatch is a bug rather than a
#: dialect to translate.
VALID_SET_TYPES = frozenset({"warmup", "working", "backoff", "drop"})


class RhomeLogError(RuntimeError):
    """The export could not be read as written."""


@dataclass
class RhomeLogReport:
    """What the read found, for the build record to quote."""

    files: int = 0
    sessions: int = 0
    sessions_superseded: int = 0
    sets: int = 0
    sets_skipped: int = 0
    first_day: date | None = None
    last_day: date | None = None
    days: int = 0
    days_without_wearable: int = 0
    gyms: set[str] = field(default_factory=set)
    contexts_missing: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"{self.files} export(s)",
            f"{self.sessions} sessions",
            f"{self.sets} sets kept",
        ]
        if self.sets_skipped:
            parts.append(f"{self.sets_skipped} skipped")
        if self.sessions_superseded:
            parts.append(f"{self.sessions_superseded} superseded by a later export")
        if self.gyms:
            parts.append("gyms: " + ", ".join(sorted(self.gyms)))
        if self.contexts_missing:
            parts.append(f"{self.contexts_missing} fixed-equipment sets with no context")
        return " · ".join(parts)


@dataclass(frozen=True)
class _Session:
    """One logged session, before it is placed on the calendar."""

    id: str
    day: date
    started_at: datetime
    exported_at: datetime
    gym: str | None
    sets: tuple[LoggedSet, ...]


def _instant(value: str, *, field_name: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise RhomeLogError(f"{field_name} is not an ISO 8601 instant: {value!r}") from exc


def _read_one(
    path: Path, library: ExerciseLibrary, report: RhomeLogReport
) -> list[_Session]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RhomeLogError(f"{path} could not be read as JSON: {exc}") from exc

    schema = payload.get("schemaVersion")
    if schema not in SUPPORTED_SCHEMAS:
        raise RhomeLogError(
            f"{path} announces schema {schema!r}; this adapter reads "
            f"{sorted(SUPPORTED_SCHEMAS)}"
        )

    # The library the app logged against. A mismatch is not fatal — ids may well
    # still resolve — but it is recorded, because an id meaning something
    # different in two library versions is exactly the failure L3.9 pins
    # against.
    logged_library = payload.get("libraryVersion")
    pinned = library.pin.version if library.pin else None
    if pinned and logged_library and logged_library != pinned:
        report.notes.append(
            f"{path.name} logged against library {logged_library}, "
            f"engine loaded {pinned}"
        )

    exported_at = _instant(payload.get("exportedAt", ""), field_name="exportedAt")

    sessions: list[_Session] = []
    for raw in payload.get("sessions", []):
        sessions.append(_read_session(raw, library, report, exported_at, path))
    return sessions


def _read_session(
    raw: Mapping,
    library: ExerciseLibrary,
    report: RhomeLogReport,
    exported_at: datetime,
    path: Path,
) -> _Session:
    session_id = str(raw.get("id") or "").strip()
    if not session_id:
        raise RhomeLogError(f"{path}: a session carries no id")

    started_at = _instant(raw.get("startedAt", ""), field_name="startedAt")
    gym = (raw.get("gym") or "").strip() or None
    if gym:
        report.gyms.add(gym)

    sets: list[LoggedSet] = []
    # Session position is a model input, so the observable order is preserved:
    # exercises by their logged order, sets by number within each. Never sorted
    # by name.
    for entry in sorted(raw.get("entries", []), key=lambda e: int(e.get("order", 0))):
        exercise_id = str(entry.get("exerciseId") or "").strip()
        if exercise_id not in library.exercises:
            raise RhomeLogError(
                f"{path}: session {session_id} logs {exercise_id!r}, which is not "
                f"in the loaded library. The logger writes library ids, so this "
                f"is a version mismatch, not a name to be matched."
            )

        context = (entry.get("equipmentContext") or "").strip() or None
        equipment = str(entry.get("equipment") or "")

        for logged in sorted(
            entry.get("sets", []), key=lambda s: int(s.get("setNumber", 0))
        ):
            set_type = str(logged.get("setType") or "").strip().lower()
            if set_type not in VALID_SET_TYPES:
                raise RhomeLogError(
                    f"{path}: session {session_id} logs set type {set_type!r}"
                )

            reps = int(logged.get("reps") or 0)
            if reps <= 0:
                # A set with no repetitions was started and abandoned. It
                # carries no dose and no observation; dropping it is not a
                # judgement about the training.
                report.sets_skipped += 1
                continue

            if equipment in ("cable", "machine") and context is None:
                report.contexts_missing += 1

            sets.append(
                LoggedSet(
                    workout_id=session_id,
                    exercise_id=exercise_id,
                    set_number=int(logged.get("setNumber") or 0),
                    set_type=set_type,
                    load_kg=float(logged.get("loadKg") or 0.0),
                    reps=reps,
                    rpe=_optional_float(logged.get("rpe")),
                    rir=_optional_float(logged.get("rir")),
                    equipment_context=context,
                )
            )

    return _Session(
        id=session_id,
        day=started_at.date(),
        started_at=started_at,
        exported_at=exported_at,
        gym=gym,
        sets=tuple(sets),
    )


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_log(
    paths: Path | Sequence[Path],
    library: ExerciseLibrary,
    report: RhomeLogReport | None = None,
) -> tuple[dict[date, list[LoggedSet]], RhomeLogReport]:
    """Read one or more exports into sets by calendar day.

    Later exports supersede earlier ones for the same session id, so a run of
    weekly exports can be passed together and the newest description of each
    session wins.
    """
    if isinstance(paths, Path):
        paths = [paths]
    report = report or RhomeLogReport()

    newest: dict[str, _Session] = {}
    for path in paths:
        report.files += 1
        for session in _read_one(Path(path), library, report):
            existing = newest.get(session.id)
            if existing is None:
                newest[session.id] = session
            elif session.exported_at >= existing.exported_at:
                newest[session.id] = session
                report.sessions_superseded += 1
            else:
                report.sessions_superseded += 1

    by_day: dict[date, list[LoggedSet]] = {}
    for session in sorted(newest.values(), key=lambda s: s.started_at):
        if not session.sets:
            continue
        by_day.setdefault(session.day, []).extend(session.sets)
        report.sessions += 1
        report.sets += len(session.sets)

    return by_day, report


def build_days(
    paths: Path | Sequence[Path],
    library: ExerciseLibrary,
    *,
    nights: Mapping[date, tuple[RecoveryReading, float | None]] | None = None,
    body_mass: Mapping[date, float] | None = None,
    first: date | None = None,
    last: date | None = None,
) -> tuple[list[DayInput], RhomeLogReport]:
    """Assemble a continuous run of ``DayInput`` from the logger's exports.

    The calendar is **continuous**, not one entry per session, for the reason
    the Spotr adapter states: the engine evolves state in real time, so a
    fortnight away from the gym must arrive as fourteen empty days rather than
    as a gap between two entries. That absence is the information
    (``DATA.md`` §19.5).

    ``first`` and ``last`` widen the span beyond what the log itself covers,
    which is how a run is joined to the historical record without the engine
    seeing a discontinuity where one athlete simply changed logger.
    """
    sessions, report = read_log(paths, library)
    if not sessions:
        raise RhomeLogError("no export produced a single usable session")

    nights = nights or {}
    body_mass = body_mass or {}

    span = sorted(sessions)
    start = min([span[0], first]) if first else span[0]
    end = max([span[-1], last]) if last else span[-1]
    report.first_day, report.last_day = start, end

    days: list[DayInput] = []
    for offset in range((end - start).days + 1):
        when = date.fromordinal(start.toordinal() + offset)
        reading, steps = nights.get(when, (RecoveryReading(), None))
        if when not in nights:
            report.days_without_wearable += 1
        days.append(
            DayInput(
                day_index=offset,
                reading=reading,
                sets=list(sessions.get(when, [])),
                body_mass_kg=body_mass.get(when),
                steps=steps,
                # The logger records no standardised anchor efforts, so none
                # are claimed. Inventing them would give ordinary sets the
                # heavier learning rate that only a deliberate test earns.
                anchor_exercise_ids=frozenset(),
            )
        )

    report.days = len(days)
    return days, report
