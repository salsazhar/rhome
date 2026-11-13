"""Rhome's own logger, read back into the engine (L6.2).

Tested by **writing synthetic sessions into the logger's export shape and
reading them back**, in the same spirit as the Spotr adapter's round trip: the
answer is known before the adapter runs, so "it works" is a measurement rather
than an impression.

None of these fixtures are the athlete's. The adapter exists to carry data the
engine has never seen, and building it against that data would spend the only
prospective record this project has — the failure D22 records, repeated on
purpose. Every session here is fabricated.

The failure modes are asserted, not merely avoided. An unknown exercise id must
raise rather than resolve, because the logger writes library identifiers and a
miss means a version mismatch; and a re-export must supersede rather than
accumulate, because the app writes every finished session every time.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from rhome_core.exercises import library_path, load_library
from rhome_eval.rhome_logger import (
    RhomeLogError,
    RhomeLogReport,
    build_days,
    read_log,
)

# The logger bundles and logs against the expanded library, not the 27-exercise
# one the synthetic athlete needs, so the adapter is tested against what the
# app actually writes.
LIBRARY = load_library(library_path().parent / "exercise_library_v1_2.csv")

# Two library ids with different equipment, so the context rules can be
# exercised on one that needs a station and one that does not.
FIXED = "cable_lateral_raise"
FREE = "barbell_bench_press"


def _set(number: int, load: float, reps: int, *, rpe: float | None = 9.0,
         set_type: str = "working", at: datetime | None = None) -> dict:
    return {
        "setNumber": number,
        "loadKg": load,
        "reps": reps,
        "rpe": rpe,
        "rir": None,
        "setType": set_type,
        "completedAt": (at or datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)).isoformat(),
    }


def _entry(exercise_id: str, order: int, sets: list[dict], *,
           context: str | None = None, equipment: str = "cable") -> dict:
    return {
        "exerciseId": exercise_id,
        "exerciseName": exercise_id.replace("_", " ").title(),
        "equipment": equipment,
        "order": order,
        "equipmentContext": context,
        "sets": sets,
    }


def _session(when: datetime, entries: list[dict], *, id: str = "S1",
             gym: str | None = "A gym") -> dict:
    return {
        "id": id,
        "startedAt": when.isoformat(),
        "endedAt": (when + timedelta(hours=1)).isoformat(),
        "gym": gym,
        "notes": "",
        "entries": entries,
    }


def _export(tmp_path: Path, sessions: list[dict], *, name: str = "log.json",
            exported_at: datetime | None = None,
            schema: str = "rhome-logger/1",
            library_version: str = "v1.2") -> Path:
    payload = {
        "schemaVersion": schema,
        "libraryVersion": library_version,
        "exportedAt": (exported_at or datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)).isoformat(),
        "sessions": sessions,
    }
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_round_trips_a_session_into_logged_sets(tmp_path):
    """Every field the engine reads survives the trip unchanged."""
    when = datetime(2026, 8, 25, 11, 23, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [
            _entry(FIXED, 0, [
                _set(1, 7.5, 5, rpe=10.0),
                _set(2, 6.25, 8, rpe=9.5),
            ], context="corner pulley"),
        ]),
    ])

    by_day, report = read_log(path, LIBRARY)

    assert list(by_day) == [date(2026, 8, 25)]
    sets = by_day[date(2026, 8, 25)]
    assert len(sets) == 2
    assert report.sessions == 1 and report.sets == 2

    first = sets[0]
    assert first.exercise_id == FIXED
    assert first.set_number == 1
    assert first.set_type == "working"
    assert first.load_kg == pytest.approx(7.5)
    assert first.reps == 5
    assert first.rpe == pytest.approx(10.0)
    assert first.equipment_context == "corner pulley"
    assert first.workout_id == "S1"


def test_session_position_follows_the_logged_order_not_the_name(tmp_path):
    """Within-session position is a model input, so order is observable data.

    The exercise logged second is named so that an alphabetical sort would put
    it first. If that ever happens the fatigue curvature is being fed a
    sequence the athlete did not perform.
    """
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [
            _entry(FIXED, 0, [_set(1, 7.5, 8)], context="pulley"),
            _entry(FREE, 1, [_set(1, 60.0, 5)], equipment="barbell"),
        ]),
    ])

    by_day, _ = read_log(path, LIBRARY)
    order = [s.exercise_id for s in by_day[date(2026, 8, 25)]]
    assert order == [FIXED, FREE]
    assert FREE < FIXED  # an alphabetical sort would have inverted it


def test_a_re_export_supersedes_rather_than_accumulates(tmp_path):
    """The app writes every finished session each time it exports."""
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    monday = _export(tmp_path, [
        _session(when, [_entry(FIXED, 0, [_set(1, 7.5, 5)], context="pulley")]),
    ], name="monday.json", exported_at=datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc))

    # The same session re-exported a week later, with a correction: the athlete
    # fixed the load on the phone.
    friday = _export(tmp_path, [
        _session(when, [_entry(FIXED, 0, [_set(1, 8.75, 5)], context="pulley")]),
    ], name="friday.json", exported_at=datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc))

    by_day, report = read_log([monday, friday], LIBRARY)

    sets = by_day[date(2026, 8, 25)]
    assert len(sets) == 1, "the session was counted twice"
    assert sets[0].load_kg == pytest.approx(8.75), "the later export should win"
    assert report.sessions == 1
    assert report.sessions_superseded == 1

    # Order of arrival must not change the answer.
    reversed_by_day, _ = read_log([friday, monday], LIBRARY)
    assert reversed_by_day[date(2026, 8, 25)][0].load_kg == pytest.approx(8.75)


def test_an_unknown_exercise_id_raises_rather_than_resolving(tmp_path):
    """The logger writes library ids; a miss is a version mismatch."""
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [_entry("cable_lateral_raise_v2", 0, [_set(1, 7.5, 5)])]),
    ])

    with pytest.raises(RhomeLogError, match="not .*in the loaded library"):
        read_log(path, LIBRARY)


def test_an_unknown_schema_is_refused(tmp_path):
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [_entry(FIXED, 0, [_set(1, 7.5, 5)], context="pulley")]),
    ], schema="rhome-logger/99")

    with pytest.raises(RhomeLogError, match="announces schema"):
        read_log(path, LIBRARY)


def test_an_unknown_set_type_raises(tmp_path):
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [
            _entry(FIXED, 0, [_set(1, 7.5, 5, set_type="myoreps")], context="pulley"),
        ]),
    ])

    with pytest.raises(RhomeLogError, match="set type"):
        read_log(path, LIBRARY)


def test_a_set_with_no_repetitions_is_dropped_and_counted(tmp_path):
    """Started and abandoned. No dose, no observation, and it is reported."""
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [
            _entry(FIXED, 0, [_set(1, 7.5, 5), _set(2, 7.5, 0)], context="pulley"),
        ]),
    ])

    by_day, report = read_log(path, LIBRARY)
    assert len(by_day[date(2026, 8, 25)]) == 1
    assert report.sets_skipped == 1


def test_missing_context_on_fixed_equipment_is_counted_not_invented(tmp_path):
    """A free weight needs no context; a cable with none is a gap worth naming."""
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [
            _entry(FIXED, 0, [_set(1, 7.5, 5)], context=None),
            _entry(FREE, 1, [_set(1, 60.0, 5)], equipment="barbell", context=None),
        ]),
    ])

    by_day, report = read_log(path, LIBRARY)
    sets = by_day[date(2026, 8, 25)]
    assert sets[0].equipment_context is None
    assert report.contexts_missing == 1, "only the cable set should be counted"


def test_the_calendar_is_continuous_across_a_rest_gap(tmp_path):
    """A fortnight off arrives as empty days, not as a gap between entries."""
    first = datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc)
    later = datetime(2026, 8, 17, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(first, [_entry(FIXED, 0, [_set(1, 7.5, 5)], context="p")], id="A"),
        _session(later, [_entry(FIXED, 0, [_set(1, 8.75, 5)], context="p")], id="B"),
    ])

    days, report = build_days(path, LIBRARY)

    assert len(days) == 15, "3 August to 17 August inclusive"
    assert report.days == 15
    assert [d.day_index for d in days] == list(range(15))
    trained = [d.day_index for d in days if d.sets]
    assert trained == [0, 14]
    assert all(not d.sets for d in days[1:14])


def test_the_span_can_be_widened_to_join_the_historical_record(tmp_path):
    """Changing logger must not read as a discontinuity in training."""
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [_entry(FIXED, 0, [_set(1, 7.5, 5)], context="p")]),
    ])

    days, report = build_days(path, LIBRARY, first=date(2026, 8, 20))

    assert report.first_day == date(2026, 8, 20)
    assert len(days) == 6
    assert days[0].sets == []
    assert days[-1].sets, "the logged session is still the last day"


def test_a_library_version_mismatch_is_noted_not_silently_accepted(tmp_path):
    when = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    path = _export(tmp_path, [
        _session(when, [_entry(FIXED, 0, [_set(1, 7.5, 5)], context="p")]),
    ], library_version="v1.1")

    _, report = read_log(path, LIBRARY)
    assert any("logged against library v1.1" in note for note in report.notes)


def test_an_empty_export_raises_rather_than_returning_nothing(tmp_path):
    path = _export(tmp_path, [])
    with pytest.raises(RhomeLogError, match="no export produced a single usable session"):
        build_days(path, LIBRARY)
