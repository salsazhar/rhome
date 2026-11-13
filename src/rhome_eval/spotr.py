"""Reading the athlete's own logs into the engine's schema (L3.11).

Two sources, one target. The Spotr SQLite archive carries the training log; the
Oura trends export carries the nightly physiology; the engine wants
``DayInput``. This module is the join.

**Scope: this athlete, not the product.** The Spotr archive exists only because
it was scraped from a device export, and no user will ever arrive with one. This
is validation scaffolding for L3.12. General import — from Hevy, Strong, a CSV —
is a real product feature and belongs in Layer 6, where it also happens to
shorten the capacity warm-up for anyone switching loggers. It is not a
mitigation this engine may assume it has.

**Written against the schema, not the values.** Everything here was built from
column types, from the categorical vocabularies extracted at L3.11, and from the
synthetic dataset re-expressed in Spotr's shape as a fixture. The seal stays
shut while the parsing is debugged, which is where the work actually is.

**It resolves no exercise names itself.** Every logged name goes through the
mapping frozen at L3.10. A name the mapping has not seen raises rather than
being matched on the spot, because matching at read time is matching with the
athlete's results in view.

Four things the sources do not provide, each handled explicitly rather than
invented:

**Spotr marks only drop sets.** ``set_wdf`` takes exactly one value,
``Dropset``. There is no warm-up marker, so a warm-up the athlete logged is
indistinguishable from a working set and will carry full dose. See LIM-29.

**Neither source carries body mass.** ``health_data`` records HRV, resting
heart rate, sleep, readiness and calories — not weight; only
``user.weight_in_pounds`` exists, a single current figure. The athlete has never
tracked it. What stands in is four **recalled** anchor points, interpolated
between and absent outside, loaded from ``data/real_body_mass.json`` and marked
throughout as recollection rather than measurement. See LIM-30.

**Effort is RPE only.** There is no RIR column, so every set arrives as RPE and
the L2.1 parser's Zourdos conversion applies. Sets with no RPE arrive unrated
and are imputed by the engine, per D18.

**Oura's readiness score is deliberately dropped.** ``DATA.md`` §5.1 forbids the
v0 engine using it as a predictor, because it is generated from overlapping
underlying variables. It is not carried into ``RecoveryReading`` at all, so the
prohibition is structural rather than remembered.
"""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

from rhome_core.exercises import ExerciseLibrary
from rhome_engine.dose import LoggedSet
from rhome_engine.recovery import RecoveryReading
from rhome_engine.session import DayInput
from rhome_eval.vocabulary import ExerciseMapping

__all__ = [
    "SpotrIngestError",
    "body_mass_series",
    "IngestReport",
    "read_training_sets",
    "load_equipment_contexts",
    "read_oura",
    "build_days",
    "SET_QUERY",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
GYM_TAGS = REPO_ROOT / "data" / "real_gym_tags.json"


class SpotrIngestError(RuntimeError):
    """The source could not be read into the engine's schema."""


def load_equipment_contexts(path: Path | None = None) -> dict[str, str]:
    """Workout-id to athlete-recorded gym, empty when no context file exists."""
    path = path or GYM_TAGS
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict):
        raise SpotrIngestError(f"{path.name} has no session-to-gym mapping")
    invalid = [key for key, value in sessions.items() if not key or not str(value).strip()]
    if invalid:
        raise SpotrIngestError(f"{path.name} has blank equipment contexts")
    return {str(key): str(value).strip() for key, value in sessions.items()}


#: Spotr's own encodings, from ``data/real_conventions.json``.
DROP_MARKER = "Dropset"
WEIGHT_UNIT = "kg"
TYPE_TO_KIND = {
    "weight_reps": "weighted_reps",
    "reps_only": "reps_only",
    "time_only": "time_only",
}

#: Oura columns the engine reads. Readiness is absent on purpose (§5.1).
OURA_FIELDS = {
    "hrv_rmssd_ms": "Average HRV",
    "resting_hr_bpm": "Average Resting Heart Rate",
    "total_sleep_min": "Total Sleep Duration",
    "sleep_efficiency": "Sleep Efficiency",
    "temperature_deviation_c": "Temperature Deviation (°C)",
}
OURA_STEPS = "Steps"

#: Everything the adapter reads from the log. Stated as a constant for the same
#: reason L3.10's extraction query is: a query built at the call site is a query
#: that can quietly grow.
SET_QUERY = """
SELECT workout_uuid, workout_date, exercise_name, set_number, reps, weight_kg,
       set_rpe, set_wdf, exercise_type, is_personal_best, is_done,
       set_is_deleted, workout_is_deleted, set_id
FROM training_sets
ORDER BY workout_date, workout_uuid, exercise_order, set_number
"""


@dataclass
class IngestReport:
    """What the adapter did, and what it refused to do."""

    days: int = 0
    sessions: int = 0
    days_without_body_mass: int = 0
    sets_read: int = 0
    sets_kept: int = 0
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    derived_exercises: set[str] = field(default_factory=set)
    oura_nights: int = 0
    days_without_wearable: int = 0
    first_day: date | None = None
    last_day: date | None = None

    def note(self, reason: str) -> None:
        self.skipped[reason] += 1

    def summary(self) -> str:
        parts = [
            f"{self.days} days, {self.sessions} sessions, "
            f"{self.sets_kept} of {self.sets_read} sets kept",
            f"{self.oura_nights} wearable nights, "
            f"{self.days_without_wearable} days without one",
            f"{self.days_without_body_mass} days with no body mass",
        ]
        if self.skipped:
            parts.append(
                "skipped: "
                + ", ".join(f"{k} {v}" for k, v in sorted(self.skipped.items()))
            )
        if self.derived_exercises:
            parts.append(f"derived coefficients: {sorted(self.derived_exercises)}")
        return " · ".join(parts)


# --- the training log ---------------------------------------------------------

def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_flag(value) -> bool:
    """Interpret a boolean column across every storage class SQLite allows.

    SQLite is dynamically typed: a column declared ``INT`` can hold the *string*
    ``"0"``, and a plain truth test on that string is ``True``. The round-trip
    fixture stores every column as TEXT for exactly this reason, and the first
    version of this adapter read all 1 771 of its rows as deleted.

    The archive happens to store these as integers today. Depending on that is
    depending on a detail of one export.
    """
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text not in ("", "0", "0.0", "false", "no", "none", "null")


def _as_date(value) -> date | None:
    """Spotr stores the workout date untyped; accept the shapes it produces."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[: len(pattern) + 2], pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def read_training_sets(
    archive: Path,
    mapping: ExerciseMapping,
    library: ExerciseLibrary,
    report: IngestReport,
    equipment_contexts: Mapping[str, str] | None = None,
) -> dict[date, list[LoggedSet]]:
    """Read the log into ``LoggedSet`` objects, keyed by calendar date.

    The archive is **copied before it is opened**. SQLite's ``mode=ro`` still
    creates WAL sidecar files beside the database, which broke the seal once
    already (LIM-27), and a sealed artefact a tool can write next to is not
    sealed.
    """
    if not archive.exists():
        raise SpotrIngestError(f"no Spotr archive at {archive}")

    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "archive.sqlite"
        shutil.copyfile(archive, copy)
        connection = sqlite3.connect(copy)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(SET_QUERY).fetchall()
        finally:
            connection.close()

    by_day: dict[date, list[LoggedSet]] = defaultdict(list)
    equipment_contexts = equipment_contexts or {}
    for row in rows:
        report.sets_read += 1

        # ``training_sets`` is a left join from a workout's exercises onto its
        # sets, so an exercise the athlete added and never logged a set for
        # arrives as one row with every set field null — including ``set_id``.
        # It is not a set with missing data; it is the absence of a set, and
        # counting it as "no repetitions" would report a tenth of the log as
        # lost training when nothing was lost at all.
        if row["set_id"] is None:
            report.note("exercise added but never performed")
            continue
        if _as_flag(row["workout_is_deleted"]) or _as_flag(row["set_is_deleted"]):
            report.note("deleted")
            continue
        if row["is_done"] is not None and not _as_flag(row["is_done"]):
            # A planned set the athlete did not perform. Keeping it would
            # invent training that never happened.
            report.note("not performed")
            continue

        when = _as_date(row["workout_date"])
        if when is None:
            report.note("undated")
            continue

        name = (row["exercise_name"] or "").strip()
        if not name:
            report.note("unnamed exercise")
            continue

        # L3.10's frozen mapping is the only resolver. An unknown name raises
        # rather than being matched here, with the results in view.
        exercise_id = mapping.library_id(name)
        if exercise_id is None:
            report.derived_exercises.add(name)
            report.note("derived exercise, not yet supported")
            continue
        if exercise_id not in library:
            raise SpotrIngestError(
                f"the frozen mapping sends {name!r} to {exercise_id!r}, which is "
                f"not in the library it names"
            )

        reps = row["reps"]
        if reps is None or int(reps) < 1:
            report.note("no repetitions")
            continue

        load = _as_float(row["weight_kg"])
        if load is None:
            load = 0.0

        by_day[when].append(
            LoggedSet(
                workout_id=str(row["workout_uuid"]),
                exercise_id=exercise_id,
                set_number=int(row["set_number"] or 1),
                # Spotr marks only drop sets; everything else reads as working.
                set_type="drop" if row["set_wdf"] == DROP_MARKER else "working",
                load_kg=load,
                reps=int(reps),
                rpe=_as_float(row["set_rpe"]),
                rir=None,
                is_pr=_as_flag(row["is_personal_best"]),
                equipment_context=equipment_contexts.get(str(row["workout_uuid"])),
            )
        )
        report.sets_kept += 1

    return dict(by_day)


# --- the wearable -------------------------------------------------------------

def _minutes(value: str | None) -> float | None:
    """Oura reports durations in seconds; the engine wants minutes."""
    seconds = _as_float(value)
    return None if seconds is None else seconds / 60.0


def _fraction(value: str | None) -> float | None:
    """Sleep efficiency arrives as a percentage; the engine wants a fraction."""
    percent = _as_float(value)
    if percent is None:
        return None
    return percent / 100.0 if percent > 1.0 else percent


def read_oura(path: Path, report: IngestReport) -> dict[date, tuple[RecoveryReading, float | None]]:
    """Read the trends export into nightly readings, keyed by date."""
    if not path.exists():
        raise SpotrIngestError(f"no Oura export at {path}")

    nights: dict[date, tuple[RecoveryReading, float | None]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            when = _as_date(row.get("date"))
            if when is None:
                continue
            reading = RecoveryReading(
                hrv_rmssd_ms=_as_float(row.get(OURA_FIELDS["hrv_rmssd_ms"])),
                resting_hr_bpm=_as_float(row.get(OURA_FIELDS["resting_hr_bpm"])),
                total_sleep_min=_minutes(row.get(OURA_FIELDS["total_sleep_min"])),
                sleep_efficiency=_fraction(row.get(OURA_FIELDS["sleep_efficiency"])),
                temperature_deviation_c=_as_float(
                    row.get(OURA_FIELDS["temperature_deviation_c"])
                ),
            )
            nights[when] = (reading, _as_float(row.get(OURA_STEPS)))
    report.oura_nights = len(nights)
    return nights


# --- body mass ----------------------------------------------------------------

BODY_MASS = REPO_ROOT / "data" / "real_body_mass.json"


def body_mass_series(path: Path | None = None) -> dict[date, float]:
    """Body mass by date, interpolated between the athlete's recalled anchors.

    **These are not measurements.** The athlete has never tracked body mass, and
    neither source carries a series, so four points recalled from memory stand
    in. They are labelled as recollection everywhere they appear, because a
    number that looks measured and is not is worse than an absent one.

    Two choices keep that honest.

    **Linear between anchors, nothing outside.** Extrapolating past the first
    or last anchor would invent a trend where there is not even a recollection.
    Days outside the range get no body mass at all, so bodyweight exercises
    there contribute dose and no performance observation — which is what the
    engine already does when body mass is unknown, and is the correct answer.

    **No synthetic fluctuation.** Real scale readings carry about a kilogram of
    water and gut content, and ``BodyMassTracker`` smooths them with a
    seven-day median for exactly that reason. Adding invented noise here would
    make recalled figures look measured, and the smoother would then dutifully
    remove variation that never existed. A straight line between two recalled
    points is the honest shape of a recalled quantity.
    """
    path = path or BODY_MASS
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    anchors = sorted(
        (date.fromisoformat(a["date"]), float(a["kg"])) for a in payload["anchors"]
    )
    if len(anchors) < 2:
        raise SpotrIngestError("a body-mass series needs at least two anchors")

    series: dict[date, float] = {}
    for (start, low), (stop, high) in zip(anchors, anchors[1:]):
        span = (stop - start).days
        for offset in range(span + 1):
            when = date.fromordinal(start.toordinal() + offset)
            series[when] = low + (high - low) * (offset / span)
    return series


# --- the join -----------------------------------------------------------------

def build_days(
    archive: Path,
    oura: Path,
    mapping: ExerciseMapping,
    library: ExerciseLibrary,
    *,
    body_mass: dict[date, float] | None = None,
    equipment_contexts: Mapping[str, str] | None = None,
) -> tuple[list[DayInput], IngestReport]:
    """Assemble a continuous run of ``DayInput`` from both sources.

    The calendar is **continuous**, not one entry per session. The engine
    evolves state in real time, so a fortnight away from the gym has to arrive
    as fourteen empty days rather than as a gap between two entries — that
    absence is the information (``DATA.md`` §19.5).

    ``body_mass`` maps dates to kilograms and defaults to the athlete's recalled
    anchors, interpolated (LIM-30). A date the series does not cover gets
    ``None``, and bodyweight exercises on that day contribute dose and no
    performance observation — the engine never imputes body mass from
    population statistics, and a recollection that does not reach back that far
    is not evidence.
    """
    report = IngestReport()
    weights = body_mass_series() if body_mass is None else body_mass
    sessions = read_training_sets(
        archive, mapping, library, report, equipment_contexts
    )
    nights = read_oura(oura, report)

    if not sessions and not nights:
        raise SpotrIngestError("neither source produced a single usable row")

    span = sorted({*sessions, *nights})
    first, last = span[0], span[-1]
    report.first_day, report.last_day = first, last
    report.sessions = sum(1 for v in sessions.values() if v)

    days: list[DayInput] = []
    for offset in range((last - first).days + 1):
        when = date.fromordinal(first.toordinal() + offset)
        reading, steps = nights.get(when, (RecoveryReading(), None))
        if when not in nights:
            report.days_without_wearable += 1
        if when not in weights:
            report.days_without_body_mass += 1
        days.append(
            DayInput(
                day_index=offset,
                reading=reading,
                # SET_QUERY already orders rows by workout, exercise_order and
                # set_number. Preserve that observable chronology: an
                # alphabetical exercise sort destroys the session position
                # used by within-session fatigue curvature.
                sets=list(sessions.get(when, [])),
                body_mass_kg=weights.get(when),
                steps=steps,
                # Spotr records no standardised anchor efforts, so none are
                # claimed. Inventing them would give ordinary sets the heavier
                # learning rate that only a deliberate test earns.
                anchor_exercise_ids=frozenset(),
            )
        )
    report.days = len(days)
    return days, report
