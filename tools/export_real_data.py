"""Export the athlete's own data into readable form (post-L3.12).

The seal existed to protect one measurement: the engine's first contact with
data it could not have been tuned against. That measurement happened at L3.12,
the result is recorded, and the seal's purpose is discharged. Keeping the data
locked in a SQLite blob now protects nothing and only stops the athlete looking
at their own training.

So this writes it out flat, for the athlete and for any tool they point at it.

**What survives the transition, and must.** The originals in ``data/real/`` are
not touched, ``data/real_manifest.json`` still checksums them, and
``data/real_openings.json`` still records every opening. Provenance is the part
worth keeping — being able to prove *which* bytes produced the L3.12 result
matters more now than before, because from here the data is a development set
and results on it are a weaker claim (D22).

The export is derived, never authoritative. Regenerate it freely; the sealed
originals remain the source of truth.

    python3 tools/export_real_data.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ARCHIVE = ROOT / "data" / "real" / "spotr" / "spotr_training_archive.sqlite"
OURA = ROOT / "data" / "real" / "oura" / "oura_2024-12-17_2026-08-23_trends.csv"
OUT = ROOT / "data" / "real_export"

#: Tables worth flattening. The rest of the archive is app plumbing — sync
#: flags, subscription state, TikTok analytics from the phone export — and
#: carries nothing about training.
TABLES = ("training_sets", "workouts", "exercises", "health_data")


def _dump(connection: sqlite3.Connection, table: str, path: Path) -> int:
    cursor = connection.execute(f"SELECT * FROM {table}")
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    if not ARCHIVE.exists():
        raise SystemExit(f"no archive at {ARCHIVE}")
    OUT.mkdir(parents=True, exist_ok=True)

    written: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as scratch:
        # Copied before opening: SQLite's read-only mode still writes WAL
        # sidecar files beside the database (LIM-27).
        copy = Path(scratch) / "archive.sqlite"
        shutil.copyfile(ARCHIVE, copy)
        connection = sqlite3.connect(copy)
        try:
            for table in TABLES:
                written[table] = _dump(connection, table, OUT / f"{table}.csv")
        finally:
            connection.close()

    shutil.copyfile(OURA, OUT / "oura_trends.csv")
    with OURA.open(encoding="utf-8-sig") as handle:
        written["oura_trends"] = sum(1 for _ in handle) - 1

    # The engine's own view of the same data: what it actually ingested, after
    # the frozen mapping and every skip rule. This is the file to read when
    # asking why the engine saw what it saw.
    from rhome_core.exercises import library_path, load_library  # noqa: PLC0415

    from rhome_eval.spotr import build_days  # noqa: PLC0415
    from rhome_eval.vocabulary import load_mapping  # noqa: PLC0415

    from rhome_eval.spotr import load_equipment_contexts  # noqa: PLC0415

    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    days, report = build_days(
        ARCHIVE, OURA, load_mapping(), library,
        equipment_contexts=load_equipment_contexts(),
    )
    with (OUT / "engine_input.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "day_index", "workout_id", "exercise_id", "set_number", "set_type",
            "load_kg", "reps", "rpe", "rir", "is_pr", "equipment_context",
            "body_mass_kg", "steps",
            "hrv_rmssd_ms", "resting_hr_bpm", "total_sleep_min",
            "sleep_efficiency", "temperature_deviation_c",
        ])
        rows = 0
        for day in days:
            r = day.reading
            for logged in day.sets:
                writer.writerow([
                    day.day_index, logged.workout_id, logged.exercise_id,
                    logged.set_number, logged.set_type, logged.load_kg,
                    logged.reps, logged.rpe, logged.rir, logged.is_pr,
                    logged.equipment_context,
                    day.body_mass_kg, day.steps, r.hrv_rmssd_ms,
                    r.resting_hr_bpm, r.total_sleep_min, r.sleep_efficiency,
                    r.temperature_deviation_c,
                ])
                rows += 1
    written["engine_input"] = rows

    manifest = {
        "exported_on": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Derived from the sealed originals, which are unchanged. This "
            "export is never authoritative; data/real_manifest.json checksums "
            "the source and data/real_openings.json records every opening."
        ),
        "source_archive_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        "source_oura_sha256": hashlib.sha256(OURA.read_bytes()).hexdigest(),
        "library": "v1.2",
        "rows": written,
        "ingestion": report.summary(),
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\nexported to {OUT.relative_to(ROOT)}/\n")
    for name, count in written.items():
        print(f"  {name + '.csv':24s} {count:6d} rows")
    print(f"\n  {report.summary()}")
    print("\nThe sealed originals are untouched and still checksummed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
