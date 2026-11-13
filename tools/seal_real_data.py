"""Seal the athlete's own recorded history (``BUILD_PLAN.md`` L3.9).

There is one athlete, one export, and one chance to run against it. Data seen
during development is data tuned against, whether or not anyone intends it —
so this tool records *that* the files exist and *that* they have not changed,
without reading a single value from them.

    python3 tools/seal_real_data.py seal      # first time
    python3 tools/seal_real_data.py verify    # any time after, including L3.9

``seal`` walks ``data/real/``, records each file's SHA-256, byte size and
extension, and writes ``data/real_manifest.json``. The manifest is committed;
the export itself never is. ``verify`` re-hashes and reports any file that was
added, removed or altered since sealing.

The tool prints file names, sizes and digests. It prints no content, no column
headers, no row counts and no dates, because each of those is a decision the
engine could be tuned toward.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VAULT = REPO_ROOT / "data" / "real"
MANIFEST = REPO_ROOT / "data" / "real_manifest.json"
_CHUNK = 1 << 20


def _provenance() -> dict[str, str]:
    """Where the build stood when the seal was applied.

    Recorded rather than hand-written, because a hand-written stage label is
    the kind of thing that stays at its first value while everything moves
    past it.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = "unknown"

    index = REPO_ROOT / "build_log" / "INDEX.md"
    completed = [
        m.group(1)
        for m in re.finditer(r"^\| (L\d+\.\d+) \|[^|]*\| ✅", index.read_text(encoding="utf-8"), re.M)
    ]
    return {"commit": commit, "last_completed_stage": completed[-1] if completed else "none"}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _scan() -> dict[str, dict[str, object]]:
    if not VAULT.is_dir():
        raise SystemExit(f"no export directory at {VAULT.relative_to(REPO_ROOT)}")
    # The directory's own README is documentation, not data. Sealing it would
    # mean an edit to the instructions read as a broken seal on the export.
    skip = {".DS_Store", "README.md"}
    files = sorted(p for p in VAULT.rglob("*") if p.is_file() and p.name not in skip)
    if not files:
        raise SystemExit(f"{VAULT.relative_to(REPO_ROOT)} is empty; nothing to seal")
    return {
        str(p.relative_to(VAULT)): {"sha256": _digest(p), "bytes": p.stat().st_size}
        for p in files
    }


def seal() -> int:
    if MANIFEST.exists():
        raise SystemExit(
            f"{MANIFEST.relative_to(REPO_ROOT)} already exists. The export is "
            f"already sealed; re-sealing would silently accept a changed file. "
            f"Run 'verify' instead, or delete the manifest deliberately."
        )
    entries = _scan()
    MANIFEST.write_text(
        json.dumps(
            {
                "sealed_on": date.today().isoformat(),
                **_provenance(),
                "note": "Sealed unread. Nothing may open these files before L3.9.",
                "files": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    total = sum(int(e["bytes"]) for e in entries.values())
    print(f"sealed {len(entries)} files, {total / 1e6:.1f} MB")
    for name, entry in entries.items():
        print(f"  {name}  {entry['bytes']:>10,} bytes  {entry['sha256'][:16]}")
    return 0


def verify() -> int:
    if not MANIFEST.exists():
        raise SystemExit("nothing sealed yet; run 'seal' first")
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    current = _scan()

    added = sorted(set(current) - set(recorded))
    removed = sorted(set(recorded) - set(current))
    changed = sorted(
        name
        for name in set(recorded) & set(current)
        if current[name]["sha256"] != recorded[name]["sha256"]
    )

    for name in removed:
        print(f"MISSING  {name}")
    for name in added:
        print(f"ADDED    {name}")
    for name in changed:
        print(f"CHANGED  {name}")

    if added or removed or changed:
        print(f"\nseal broken: {len(removed)} missing, {len(added)} added, "
              f"{len(changed)} changed")
        return 1
    print(f"seal intact: {len(recorded)} files unchanged since "
          f"{json.loads(MANIFEST.read_text(encoding='utf-8'))['sealed_on']}")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "seal":
        raise SystemExit(seal())
    if command == "verify":
        raise SystemExit(verify())
    raise SystemExit(__doc__)
