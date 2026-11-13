"""Freeze a model version, or check one (``D22``, ``BUILD_PLAN.md`` L3.16).

D22 made the recurring exam prospective: a version is scored on the sessions
logged *after* it was frozen, because those cannot have been fitted to. That
needs a record of what "it" was and when. Before this tool, freeze dates were
prose and nothing could be proved from them.

    python3 tools/freeze_version.py show     # what the tree is right now
    python3 tools/freeze_version.py freeze <label> [--defect LIM-38 ...]
    python3 tools/freeze_version.py verify   # has anything moved since?
    python3 tools/freeze_version.py list     # every version recorded

The freeze date is **read from git**, not supplied. It is the date of the last
commit touching anything that decides what the engine predicts, so freezing
today does not backdate a claim and does not forfeit the days since the engine
actually stopped changing. Uncommitted changes in those paths are refused,
because the date would then describe code that is not what ran.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rhome_eval.version import (  # noqa: E402
    VERSIONS_PATH,
    VersionError,
    capture,
    drift,
    latest,
    load_versions,
    record,
)


def _describe(version, indent: str = "  ") -> None:
    print(f"{indent}label             {version.label}")
    print(f"{indent}frozen at         {version.frozen_at}")
    print(f"{indent}  (derived from the last commit touching engine paths)")
    print(f"{indent}commit            {version.commit[:12]}")
    print(f"{indent}parameters        {version.parameters_digest}")
    print(f"{indent}engine source     {version.source_digest}")
    print(f"{indent}library           {version.library.get('version')} "
          f"({version.library.get('exercises')} exercises)")
    print(f"{indent}version digest    {version.digest}")
    if version.inputs:
        print(f"{indent}ingest inputs     {len(version.inputs)} pinned by content")
    if version.known_defects:
        print(f"{indent}known defects     {', '.join(version.known_defects)}")
        print(f"{indent}  — a score from this version carries these; it is not a clean run")
    if version.note:
        print(f"{indent}note              {version.note}")


def show() -> int:
    version = capture("(uncommitted preview)")
    print("The model as the working tree stands:\n")
    _describe(version)
    print("\nSessions logged after the freeze date above are this model's")
    print("prospective exam. Nothing is recorded by 'show'.")
    return 0


def freeze(label: str, defects: tuple[str, ...]) -> int:
    version = capture(
        label,
        note="Frozen so D22's prospective regime has a dated reference.",
        known_defects=defects,
    )
    record(version)
    print(f"Recorded {label} in {VERSIONS_PATH.relative_to(ROOT)}\n")
    _describe(version)
    return 0


def verify() -> int:
    version = latest()
    if version is None:
        print("no version frozen yet; run 'freeze <label>' first")
        return 1
    moved = drift(version)
    print(f"Latest recorded version: {version.label}, frozen {version.frozen_at}\n")
    if not moved:
        print("intact — parameters, engine source and ingest inputs all match")
        return 0
    for name, why in sorted(moved.items()):
        print(f"  MOVED  {name:<40s} {why}")
    print(f"\n{len(moved)} component(s) have changed since {version.label} was")
    print("frozen. Any score claimed for that version must come from code")
    print("matching it — freeze a new version before scoring again.")
    return 1


def show_list() -> int:
    versions = load_versions()
    if not versions:
        print("no versions recorded")
        return 0
    print(f"{len(versions)} version(s) recorded:\n")
    for version in versions:
        _describe(version, indent="  ")
        print()
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    command = argv[0] if argv else ""
    try:
        if command == "show":
            raise SystemExit(show())
        if command == "verify":
            raise SystemExit(verify())
        if command == "list":
            raise SystemExit(show_list())
        if command == "freeze":
            if len(argv) < 2:
                raise SystemExit("freeze needs a label, e.g. 'freeze v0'")
            marked = tuple(
                argv[i + 1] for i, a in enumerate(argv) if a == "--defect" and i + 1 < len(argv)
            )
            raise SystemExit(freeze(argv[1], marked))
    except VersionError as exc:
        raise SystemExit(f"refused: {exc}") from exc
    raise SystemExit(__doc__)
