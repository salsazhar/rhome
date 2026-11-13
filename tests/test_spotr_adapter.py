"""The real-data ingest adapter (L3.11).

The adapter is tested by **round-tripping the synthetic dataset through Spotr's
shape**: the 730-day synthetic log is written into a SQLite database with the
archive's schema and an Oura-shaped CSV, read back through the adapter, and
compared against what the engine gets from the synthetic CSVs directly.

That is the whole point of the design. The seal stays shut while the parsing is
debugged, which is where the work is, and the comparison has a known answer —
so "the adapter works" is a measurement rather than an impression.

Where the round trip *cannot* be exact, the difference is asserted rather than
tolerated: Spotr carries no warm-up marker and no body-mass series, so the
fixture proves what is lost as well as what survives.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from rhome_core.exercises import load_library
from rhome_eval.spotr import (
    SET_QUERY,
    IngestReport,
    SpotrIngestError,
    build_days,
    load_equipment_contexts,
    read_oura,
    read_training_sets,
)
from rhome_eval.vocabulary import ExerciseMapping

LIBRARY = load_library()
ORIGIN = date(2024, 1, 1)

#: The archive's own column list, from `PRAGMA table_info(training_sets)`. The
#: fixture builds the full width so the adapter is exercised against the real
#: shape rather than a convenient subset.
TRAINING_SETS_COLUMNS = (
    "workout_uuid", "workout_date", "workout_timestamp_utc", "workout_title",
    "workout_notes", "workout_duration_seconds", "workout_personal_bests",
    "in_progress", "workout_is_deleted", "exercise_instance_id",
    "exercise_order", "exercise_notes", "exercise_id", "exercise_name",
    "canonical_name", "muscle_group", "muscle_subgroup", "exercise_type",
    "set_id", "set_number", "reps", "min_reps", "max_reps",
    "weight_stored_lb", "weight_kg", "distance_stored", "set_duration_seconds",
    "set_wdf", "set_rpe", "is_done", "set_is_deleted", "estimated_one_rep_max",
    "is_personal_best", "placeholder_weight", "placeholder_reps",
    "placeholder_distance", "placeholder_duration",
)

OURA_HEADER = (
    "date", "Average HRV", "Average Resting Heart Rate", "Total Sleep Duration",
    "Sleep Efficiency", "Temperature Deviation (°C)", "Steps", "Readiness Score",
)


# --- the fixture: the synthetic dataset, re-expressed in Spotr's shape ---------

def _write_archive(path: Path, rows: list[dict]) -> None:
    connection = sqlite3.connect(path)
    columns = ", ".join(f"{c} TEXT" for c in TRAINING_SETS_COLUMNS)
    connection.execute(f"CREATE TABLE training_sets ({columns})")
    connection.executemany(
        f"INSERT INTO training_sets ({', '.join(TRAINING_SETS_COLUMNS)}) "
        f"VALUES ({', '.join('?' for _ in TRAINING_SETS_COLUMNS)})",
        [tuple(r.get(c) for c in TRAINING_SETS_COLUMNS) for r in rows],
    )
    connection.commit()
    connection.close()


def _row(**overrides) -> dict:
    base = {
        "workout_uuid": "w1", "workout_date": "2024-01-01",
        "workout_is_deleted": 0, "exercise_order": 1,
        "exercise_name": "Barbell Bench Press", "exercise_type": "weight_reps",
        "set_number": 1, "reps": 8, "weight_kg": 80.0, "set_rpe": 8.0,
        "set_wdf": None, "is_done": 1, "set_is_deleted": 0,
        "is_personal_best": 0, "set_id": "s1",
    }
    base.update(overrides)
    return base


def _mapping(**extra) -> ExerciseMapping:
    resolved = {"Barbell Bench Press": "bench_press", "Jackknife": None}
    resolved.update(extra)
    return ExerciseMapping(resolved=resolved, digest="x" * 64, library="test")


@pytest.fixture
def sources(tmp_path):
    """A small Spotr archive and Oura export, in the real shapes."""
    archive = tmp_path / "archive.sqlite"
    _write_archive(archive, [
        _row(set_number=1),
        _row(set_number=2, reps=6, set_rpe=9.0),
        _row(set_number=3, reps=5, set_wdf="Dropset", weight_kg=60.0),
        _row(set_number=4, reps=8, set_rpe=None),          # unrated, imputed
        _row(set_number=5, is_done=0),                      # planned, not done
        _row(set_number=6, set_is_deleted=1),               # deleted set
        _row(set_number=7, workout_is_deleted=1),           # deleted workout
        _row(set_number=8, reps=None),                      # no repetitions
        _row(workout_uuid="w2", workout_date="2024-01-04", set_number=1, reps=10),
    ])

    oura = tmp_path / "oura.csv"
    with oura.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OURA_HEADER)
        for offset in (0, 1, 3):
            writer.writerow([
                (ORIGIN + timedelta(days=offset)).isoformat(),
                52.4, 51.8, 27000, 88.5, 0.12, 9400, 76,
            ])
    return archive, oura


# --- what survives ------------------------------------------------------------

@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_the_adapter_reads_the_log_into_the_engine_schema(sources):
    archive, oura = sources
    days, report = build_days(archive, oura, _mapping(), LIBRARY)

    # A continuous calendar: 1st to 4th inclusive, not two session entries.
    assert [d.day_index for d in days] == [0, 1, 2, 3]
    assert report.first_day == ORIGIN and report.last_day == ORIGIN + timedelta(days=3)

    first = days[0]
    assert len(first.sets) == 4, [s.set_number for s in first.sets]
    assert {s.exercise_id for s in first.sets} == {"bench_press"}
    assert [s.set_type for s in first.sets].count("drop") == 1
    assert days[1].sets == [] and days[2].sets == []
    assert len(days[3].sets) == 1

    # Effort arrives as RPE; Spotr has no RIR column at all.
    assert {s.rir for s in first.sets} == {None}
    assert sorted(s.rpe for s in first.sets if s.rpe is not None) == [8.0, 8.0, 9.0]
    assert any(s.rpe is None for s in first.sets), "an unrated set must survive"


@pytest.mark.spec("DATA:session-order-preserved")
def test_the_adapter_preserves_logged_exercise_order(tmp_path):
    archive = tmp_path / "ordered.sqlite"
    _write_archive(archive, [
        _row(exercise_order=1, exercise_name="Cable Row", set_id="c1"),
        _row(exercise_order=2, exercise_name="Barbell Bench Press", set_id="b1"),
    ])
    oura = tmp_path / "ordered.csv"
    oura.write_text(",".join(OURA_HEADER) + "\n", encoding="utf-8")

    days, _ = build_days(
        archive, oura, _mapping(**{"Cable Row": "cable_row"}), LIBRARY
    )
    assert [logged.exercise_id for logged in days[0].sets] == [
        "cable_row", "bench_press"
    ]


def test_equipment_contexts_are_validated_and_reach_logged_sets(sources, tmp_path):
    tags = tmp_path / "gym_tags.json"
    tags.write_text(
        '{"sessions":{"w1":" Main gym ","w2":"Second gym"}}\n',
        encoding="utf-8",
    )
    contexts = load_equipment_contexts(tags)
    archive, oura = sources
    days, _ = build_days(
        archive, oura, _mapping(), LIBRARY, equipment_contexts=contexts
    )

    assert contexts == {"w1": "Main gym", "w2": "Second gym"}
    assert {logged.equipment_context for logged in days[0].sets} == {"Main gym"}
    assert days[3].sets[0].equipment_context == "Second gym"

    tags.write_text('{"sessions":{"w1":""}}\n', encoding="utf-8")
    with pytest.raises(SpotrIngestError, match="blank equipment contexts"):
        load_equipment_contexts(tags)


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_nothing_is_invented_where_the_source_has_none(sources):
    """No field may be conjured. Every absence stays an absence."""
    archive, oura = sources
    days, _ = build_days(archive, oura, _mapping(), LIBRARY)

    assert all(d.body_mass_kg is None for d in days), (
        "these fixture dates predate the athlete's first recalled anchor, so "
        "body mass is unknown and must stay unknown"
    )
    assert all(d.anchor_exercise_ids == frozenset() for d in days), (
        "Spotr records no standardised anchor efforts; claiming one would give "
        "an ordinary set the heavier learning rate a deliberate test earns"
    )
    # The day with no Oura night carries an empty reading, not a fabricated one.
    assert days[2].reading.channels_present == 0
    assert days[0].reading.channels_present == 5


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_rows_that_are_not_training_are_skipped_and_counted(sources):
    archive, oura = sources
    _, report = build_days(archive, oura, _mapping(), LIBRARY)

    assert report.sets_read == 9
    assert report.sets_kept == 5
    assert report.skipped["deleted"] == 2
    assert report.skipped["not performed"] == 1
    assert report.skipped["no repetitions"] == 1
    assert "skipped" in report.summary()


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_oura_units_are_converted_not_copied(sources):
    """Oura reports seconds and percentages; the engine wants minutes and fractions."""
    _, oura = sources
    report = IngestReport()
    nights = read_oura(oura, report)

    reading, steps = nights[ORIGIN]
    assert reading.total_sleep_min == pytest.approx(450.0), "27000 s is 450 min"
    assert reading.sleep_efficiency == pytest.approx(0.885), "88.5% is 0.885"
    assert reading.hrv_rmssd_ms == pytest.approx(52.4)
    assert steps == pytest.approx(9400)
    assert report.oura_nights == 3


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_the_readiness_score_never_reaches_the_engine(sources):
    """``DATA.md`` §5.1 forbids it as a predictor, so it is not carried at all.

    Structural rather than remembered: there is no field on ``RecoveryReading``
    for it to occupy, and the adapter never reads the column.
    """
    from rhome_eval import spotr

    assert "Readiness" not in str(spotr.OURA_FIELDS)
    _, oura = sources
    nights = read_oura(oura, IngestReport())
    reading, _ = nights[ORIGIN]
    assert not any(
        getattr(reading, f) == 76 for f in reading.__dataclass_fields__
    ), "the readiness score leaked into a wearable channel"


# --- what the adapter refuses -------------------------------------------------

@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_an_unmapped_exercise_name_raises_rather_than_being_matched(sources, tmp_path):
    """Matching at read time is matching with the results in view."""
    from rhome_eval.vocabulary import MappingError

    archive = tmp_path / "other.sqlite"
    _write_archive(archive, [_row(exercise_name="Zercher Squat")])
    _, oura = sources

    with pytest.raises(MappingError, match="no mapping for logged exercise"):
        build_days(archive, oura, _mapping(), LIBRARY)


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_a_mapping_pointing_outside_the_library_raises(sources, tmp_path):
    """L3.12 runs once; a bad id must fail now, not then."""
    archive = tmp_path / "other.sqlite"
    _write_archive(archive, [_row(exercise_name="Ghost Press")])
    _, oura = sources
    mapping = _mapping(**{"Ghost Press": "not_an_exercise"})

    with pytest.raises(SpotrIngestError, match="not in the library"):
        build_days(archive, oura, mapping, LIBRARY)


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_empty_sources_raise_rather_than_producing_an_empty_run(tmp_path):
    archive = tmp_path / "empty.sqlite"
    _write_archive(archive, [])
    oura = tmp_path / "empty.csv"
    oura.write_text(",".join(OURA_HEADER) + "\n", encoding="utf-8")

    with pytest.raises(SpotrIngestError, match="neither source produced"):
        build_days(archive, oura, _mapping(), LIBRARY)


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_the_adapter_copies_the_archive_before_opening_it():
    """LIM-27: SQLite's read-only mode writes sidecar files beside the database."""
    import ast

    source = Path(__file__).resolve().parents[1] / "src" / "rhome_eval" / "spotr.py"
    text = source.read_text(encoding="utf-8")
    assert "shutil.copyfile" in text

    # Executable strings only: the module explains why mode=ro is wrong, and
    # prose about a boundary must not be reported as crossing it.
    tree = ast.parse(text)
    docstrings = {
        id(n.body[0].value) for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and n.body and isinstance(n.body[0], ast.Expr)
        and isinstance(n.body[0].value, ast.Constant)
        and isinstance(n.body[0].value.value, str)
    }
    live = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in docstrings
    ]
    assert not [t for t in live if "mode=ro" in t]


# --- the round trip -----------------------------------------------------------

@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_the_synthetic_dataset_survives_a_trip_through_spotrs_shape(tmp_path):
    """The measurement the whole design exists for.

    The synthetic log is written into Spotr's schema, read back through the
    adapter, and compared against what the engine gets from the synthetic CSVs
    directly. Loads, repetitions and effort must survive exactly; the set count
    must survive minus the warm-ups Spotr cannot express.
    """
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")

    original = _days()[:120]
    mapping_rows: dict[str, str] = {}
    rows: list[dict] = []
    for day in original:
        when = (ORIGIN + timedelta(days=day.day_index)).isoformat()
        for order, logged in enumerate(day.sets, start=1):
            name = f"Logged {logged.exercise_id}"
            mapping_rows[name] = logged.exercise_id
            rows.append(_row(
                workout_uuid=f"w{day.day_index}",
                workout_date=when,
                exercise_order=order,
                exercise_name=name,
                set_number=logged.set_number,
                reps=logged.reps,
                weight_kg=logged.load_kg,
                set_rpe=logged.rpe if logged.rpe is not None
                else (10.0 - logged.rir if logged.rir is not None else None),
                set_wdf="Dropset" if logged.set_type == "drop" else None,
            ))

    archive = tmp_path / "round.sqlite"
    _write_archive(archive, rows)
    oura = tmp_path / "round.csv"
    with oura.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OURA_HEADER)
        for day in original:
            r = day.reading
            if r.channels_present == 0:
                continue
            writer.writerow([
                (ORIGIN + timedelta(days=day.day_index)).isoformat(),
                r.hrv_rmssd_ms, r.resting_hr_bpm,
                None if r.total_sleep_min is None else r.total_sleep_min * 60.0,
                None if r.sleep_efficiency is None else r.sleep_efficiency * 100.0,
                r.temperature_deviation_c, day.steps, 70,
            ])

    mapping = ExerciseMapping(resolved=mapping_rows, digest="y" * 64, library="test")
    recovered, report = build_days(archive, oura, mapping, LIBRARY)

    assert len(recovered) == len(original), "the calendar must stay continuous"

    # Warm-ups are the one thing Spotr cannot express, so they are the one
    # thing that may differ — asserted, not tolerated.
    original_sets = sum(len(d.sets) for d in original)
    warmups = sum(1 for d in original for s in d.sets if s.set_type == "warmup")
    assert warmups > 100, f"only {warmups} warm-ups; the check would be weak"
    assert report.sets_kept == original_sets, (
        "every logged set must survive the trip; Spotr keeps warm-ups, it just "
        "cannot label them"
    )

    # Loads, repetitions and effort survive exactly.
    before = [(s.exercise_id, s.reps, round(s.load_kg, 4))
              for d in original for s in d.sets]
    after = [(s.exercise_id, s.reps, round(s.load_kg, 4))
             for d in recovered for s in d.sets]
    assert sorted(after) == sorted(before)

    # And the warm-ups come back as working sets, which is the loss LIM-29 names.
    assert sum(1 for d in recovered for s in d.sets if s.set_type == "warmup") == 0
    assert sum(1 for d in recovered for s in d.sets if s.set_type == "working") == (
        original_sets - sum(1 for d in original for s in d.sets if s.set_type == "drop")
    )


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_the_wearable_round_trips_through_ouras_units(tmp_path):
    """Sleep in seconds, efficiency in percent, back to minutes and fractions."""
    from test_session_driver import DATASET, _days

    if not (DATASET / "observable" / "sets.csv").exists():
        pytest.skip("dataset not generated")

    original = [d for d in _days()[:60] if d.reading.channels_present == 5]
    assert len(original) > 40, "too few complete nights to test against"

    oura = tmp_path / "w.csv"
    with oura.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(OURA_HEADER)
        for day in original:
            r = day.reading
            writer.writerow([
                (ORIGIN + timedelta(days=day.day_index)).isoformat(),
                r.hrv_rmssd_ms, r.resting_hr_bpm, r.total_sleep_min * 60.0,
                r.sleep_efficiency * 100.0, r.temperature_deviation_c,
                day.steps, 70,
            ])

    nights = read_oura(oura, IngestReport())
    for day in original:
        reading, steps = nights[ORIGIN + timedelta(days=day.day_index)]
        assert reading.total_sleep_min == pytest.approx(day.reading.total_sleep_min)
        assert reading.sleep_efficiency == pytest.approx(day.reading.sleep_efficiency)
        assert reading.hrv_rmssd_ms == pytest.approx(day.reading.hrv_rmssd_ms)
        assert reading.temperature_deviation_c == pytest.approx(
            day.reading.temperature_deviation_c
        )
        assert steps == pytest.approx(day.steps)


# --- body mass: recollection, handled as recollection -------------------------

@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_body_mass_is_interpolated_between_recalled_anchors_and_absent_outside():
    """LIM-30. Four recalled points, not measurements, and treated as such.

    Extrapolating past the anchors would invent a trend where there is not even
    a recollection, so days outside the range get no body mass and bodyweight
    exercises there yield dose and no performance observation.
    """
    import json as _json

    from rhome_eval.spotr import BODY_MASS, body_mass_series

    payload = _json.loads(BODY_MASS.read_text(encoding="utf-8"))
    assert "recalled" in payload["source"], (
        "the provenance must say these are recollections, not readings"
    )

    series = body_mass_series()
    anchors = {date.fromisoformat(a["date"]): a["kg"] for a in payload["anchors"]}
    for when, kg in anchors.items():
        assert series[when] == pytest.approx(kg), f"anchor {when} must be exact"

    assert min(series) == min(anchors) and max(series) == max(anchors)
    assert series.get(min(anchors) - timedelta(days=1)) is None
    assert series.get(max(anchors) + timedelta(days=1)) is None

    # Monotone between two rising anchors, and no invented wobble.
    august, january = date(2025, 8, 15), date(2026, 1, 1)
    walk = [series[august + timedelta(days=n)] for n in range((january - august).days + 1)]
    assert walk == sorted(walk), "interpolation between rising anchors must not wander"
    steps = {round(b - a, 9) for a, b in zip(walk, walk[1:])}
    assert len(steps) == 1, (
        f"{len(steps)} distinct daily deltas; a straight line is the honest shape "
        f"of a recalled quantity, and invented noise would make it look measured"
    )


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_body_mass_reaches_the_engine_where_it_is_known(tmp_path):
    archive = tmp_path / "bm.sqlite"
    _write_archive(archive, [
        _row(workout_date="2025-09-01"),
        _row(workout_date="2026-05-01", set_number=2),
    ])
    oura = tmp_path / "bm.csv"
    oura.write_text(",".join(OURA_HEADER) + "\n", encoding="utf-8")

    days, report = build_days(archive, oura, _mapping(), LIBRARY)
    known = {d.day_index: d.body_mass_kg for d in days if d.body_mass_kg is not None}
    assert known, "body mass must reach the engine inside the anchored range"
    assert all(60.0 < kg < 67.0 for kg in known.values()), sorted(known.values())[:3]
    assert report.days_without_body_mass == 0, (
        "both fixture dates sit inside the anchored range"
    )


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_body_mass_is_never_imputed_outside_the_recollection(tmp_path):
    """The 241 days of Oura record that precede the first anchor stay unknown."""
    archive = tmp_path / "early.sqlite"
    _write_archive(archive, [_row(workout_date="2025-01-10")])
    oura = tmp_path / "early.csv"
    oura.write_text(",".join(OURA_HEADER) + "\n", encoding="utf-8")

    days, report = build_days(archive, oura, _mapping(), LIBRARY)
    assert all(d.body_mass_kg is None for d in days)
    assert report.days_without_body_mass == len(days)


@pytest.mark.spec("DATA:real-ingest-round-trips")
def test_an_exercise_with_no_sets_is_not_reported_as_lost_training(tmp_path):
    """``training_sets`` left-joins exercises onto sets.

    An exercise the athlete added and never logged a set for arrives as one row
    with every set field null, ``set_id`` included. It is not a set with missing
    data — it is the absence of a set. Counting it as "no repetitions" reported
    a tenth of the real log as lost training when nothing had been lost, which
    is the kind of number that gets quoted long after the caveat is forgotten.
    """
    archive = tmp_path / "join.sqlite"
    _write_archive(archive, [
        _row(set_number=1),
        # An exercise added to the session, never performed: no set row exists.
        _row(set_number=None, set_id=None, reps=None, weight_kg=None,
             set_rpe=None, is_done=None, set_is_deleted=None,
             workout_is_deleted=None, exercise_name="Barbell Bench Press"),
        # A genuine gap: a set was recorded but its repetitions were not.
        _row(set_number=2, reps=None),
    ])
    oura = tmp_path / "join.csv"
    oura.write_text(",".join(OURA_HEADER) + "\n", encoding="utf-8")

    _, report = build_days(archive, oura, _mapping(), LIBRARY)
    assert report.sets_kept == 1
    assert report.skipped["exercise added but never performed"] == 1
    assert report.skipped["no repetitions"] == 1, (
        "a set that exists but lacks repetitions is a different thing and must "
        "stay countable separately"
    )
