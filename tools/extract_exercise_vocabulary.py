"""Extract the athlete's exercise vocabulary from the sealed log (L3.10).

**This tool opens sealed data.** D9 sealed `data/real/` unread because data seen
during development is data tuned against, regardless of intent. L3.10 is the
one declared exception, and it exists because the exception is unavoidable: the
engine cannot run on a log whose exercise vocabulary it has never seen, and
discovering that vocabulary at L3.12 would mean making mapping decisions with
the athlete's results already on screen.

So the disclosure is taken deliberately, now, bounded, and recorded.

**What is read, and how the bound is enforced.** Exactly one query, written out
in full below, selecting exactly one column:

    SELECT DISTINCT exercise_name FROM training_sets ORDER BY exercise_name

No counts. No dates. No loads, repetitions, effort or set order. No workout
identifiers. `QUERY` is a module constant rather than a string built at the call
site, and `tests/test_vocabulary_extraction.py` asserts that this module's own
source contains no reference to any other column of `training_sets` — so the
bound is a property of the file that can be checked, not a claim in a docstring.

**Frequencies are excluded deliberately.** Knowing which exercises the athlete
trains most would let library curation be steered toward them, which is tuning
through the back door and would be invisible afterwards. `DISTINCT` discards
that, and discarding it inside the query means the counts are never in memory.

**The result is a superset, on purpose.** No filter is applied for deleted sets
or deleted workouts. A vocabulary that covers a name the athlete no longer uses
costs nothing; one that misses a name the adapter later meets fails at L3.12,
which is the run that cannot be repeated.

    python3 tools/extract_exercise_vocabulary.py            # report
    python3 tools/extract_exercise_vocabulary.py --write    # write the artefact
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

#: The sealed archive. **Copied to a temporary file and queried there**, so
#: SQLite never opens the sealed file at all.
#:
#: The first version of this tool used ``mode=ro`` in a URI, on the reasonable
#: assumption that read-only means read-only. It does not: the archive is in
#: WAL journal mode, and SQLite created ``-shm`` and ``-wal`` sidecar files
#: beside it on open. Nothing was written to the database — the ``-wal`` was
#: zero bytes and the archive's digest was unchanged — but two files appeared
#: inside a sealed directory, and ``tools/seal_real_data.py`` reported the seal
#: broken, which is exactly what it exists to do.
#:
#: Copying costs 1.7 MB and removes the whole question.
ARCHIVE = ROOT / "data" / "real" / "spotr" / "spotr_training_archive.sqlite"

#: Where the extracted vocabulary is committed. This file, not the archive, is
#: what every later stage reads.
VOCABULARY = ROOT / "data" / "real_vocabulary.json"

#: The single permitted query. One column, no aggregates, no predicates.
QUERY = "SELECT DISTINCT exercise_name FROM training_sets ORDER BY exercise_name"

#: Recorded so the disclosure is auditable after the fact.
DISCLOSURE = (
    "L3.10: the sorted distinct exercise-name strings, and nothing else. "
    "No counts, dates, loads, repetitions, effort, set order or identifiers."
)


def extract() -> list[str]:
    """Run the one permitted query, against a copy of the sealed archive."""
    if not ARCHIVE.exists():
        raise SystemExit(f"sealed archive not found: {ARCHIVE}")
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "archive.sqlite"
        shutil.copyfile(ARCHIVE, copy)
        connection = sqlite3.connect(copy)
        try:
            rows = connection.execute(QUERY).fetchall()
        finally:
            connection.close()
    names = [row[0] for row in rows if row[0] is not None and str(row[0]).strip()]
    return sorted({str(name).strip() for name in names})


def main(write: bool) -> int:
    names = extract()

    print(f"\n{len(names)} distinct exercise names in the athlete's log\n")
    print(f"query : {QUERY}")
    print(f"bound : {DISCLOSURE}\n")
    for name in names:
        print(f"  {name}")

    if not write:
        print("\nReport only. Pass --write to commit the vocabulary artefact.")
        return 0

    payload = {
        "extracted_on": datetime.now(timezone.utc).isoformat(),
        "source": str(ARCHIVE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
        "query": QUERY,
        "disclosure": DISCLOSURE,
        "stage": "L3.10",
        "distinct_names": len(names),
        "names": names,
    }
    VOCABULARY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {VOCABULARY.relative_to(ROOT)} — {len(names)} names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--write" in sys.argv))
