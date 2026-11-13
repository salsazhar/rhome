"""Extract the source's categorical vocabularies (L3.11).

**A second disclosure, smaller than L3.10's and bounded the same way.**

L3.10 took the exercise names because the engine cannot run on a vocabulary it
has never seen. This takes the *encodings*, for the same reason: an adapter
cannot map `set_wdf` to a set type without knowing what values `set_wdf` takes,
and guessing would be worse than asking — a warm-up read as a working set
corrupts every dose downstream, silently, in a run that happens once.

**What is read.** The distinct values of four categorical columns, and nothing
else:

| column | why the adapter needs it |
|---|---|
| `training_sets.set_wdf` | maps to our warmup / working / backoff / drop |
| `training_sets.exercise_type` | distinguishes weighted reps from bodyweight and timed work |
| `health_data.data_type` | locates body mass among whatever else is recorded |
| `user.default_weight_unit` | decides whether `weight_stored_lb` or `weight_kg` is authoritative |

No counts. No dates. No loads, repetitions, effort or set order. These are
vocabularies and conventions — knowing that `set_wdf` takes three values says
nothing about how the athlete trains, in the way that knowing a column exists
says nothing.

**The bound is mechanical.** `PERMITTED` is a module constant of
`(table, column)` pairs, every query is built from it alone, and
`tests/test_source_conventions.py` asserts the tool names no other column of the
tables it touches.

**The archive is copied before it is opened** (LIM-27): SQLite's `mode=ro` still
creates WAL sidecar files inside the sealed directory, which broke the seal once
already.

    python3 tools/extract_source_conventions.py            # report
    python3 tools/extract_source_conventions.py --write    # write the artefact
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE = ROOT / "data" / "real" / "spotr" / "spotr_training_archive.sqlite"
CONVENTIONS = ROOT / "data" / "real_conventions.json"

#: The only columns this tool may read, and the only ones it does read. Every
#: query is generated from this table, so widening the disclosure means editing
#: a constant that a test inspects.
PERMITTED: tuple[tuple[str, str], ...] = (
    ("training_sets", "set_wdf"),
    ("training_sets", "exercise_type"),
    ("health_data", "data_type"),
    ("user", "default_weight_unit"),
)

DISCLOSURE = (
    "L3.11: the distinct values of four categorical columns — set_wdf, "
    "exercise_type, health_data.data_type and default_weight_unit — and "
    "nothing else. No counts, dates, loads, repetitions, effort or set order."
)


def extract() -> dict[str, list]:
    """Read each permitted column's distinct values, against a copy."""
    if not ARCHIVE.exists():
        raise SystemExit(f"sealed archive not found: {ARCHIVE}")

    found: dict[str, list] = {}
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "archive.sqlite"
        shutil.copyfile(ARCHIVE, copy)
        connection = sqlite3.connect(copy)
        try:
            for table, column in PERMITTED:
                query = f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}"
                rows = connection.execute(query).fetchall()
                found[f"{table}.{column}"] = sorted(
                    str(r[0]) for r in rows if r[0] is not None
                )
        finally:
            connection.close()
    return found


def main(write: bool) -> int:
    found = extract()

    print(f"\n{DISCLOSURE}\n")
    for key, values in found.items():
        print(f"  {key}")
        print(f"    {values}\n")

    if not write:
        print("Report only. Pass --write to commit the conventions artefact.")
        return 0

    payload = {
        "extracted_on": datetime.now(timezone.utc).isoformat(),
        "source": str(ARCHIVE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        "stage": "L3.11",
        "disclosure": DISCLOSURE,
        "permitted_columns": [f"{t}.{c}" for t, c in PERMITTED],
        "vocabularies": found,
    }
    CONVENTIONS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {CONVENTIONS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--write" in sys.argv))
