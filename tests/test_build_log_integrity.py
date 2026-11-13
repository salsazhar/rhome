"""The build log must describe what was actually built.

Checkpoint 0 was recorded as passed while L0.4 had never been implemented. The
gap survived because the checkpoint reviewed the artefacts it expected to see
and never asked whether its own layer's stages were complete. Layer 1 did not
notice, because the simulator correctly uses its own relative-intensity curve
rather than the engine's; the omission surfaced only when L2.1 first needed it.

A checkpoint that can pass over an unbuilt stage is not a gate. These tests
make the index self-checking.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parents[1] / "build_log" / "INDEX.md"
BUILD_LOG = INDEX.parent

DONE = {"✅", "⚠️"}
PENDING = {"⬜", "⛔"}

STAGE = re.compile(r"^L\d+\.\d+$")
ROW = re.compile(r"^\|\s*(L\d+\.\d+|—)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|")


def _rows():
    """Every stage and checkpoint row, in document order."""
    out = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if not match:
            continue
        stage, name, status = match.groups()
        out.append((stage, name, status))
    return out


def test_the_index_lists_stages():
    rows = _rows()
    assert len(rows) > 20, "the index parses to almost nothing; the format changed"


@pytest.mark.spec("ARCH:build-log-self-checking")
def test_no_checkpoint_passes_over_an_unbuilt_stage():
    """The failure that let Checkpoint 0 pass with L0.4 unbuilt."""
    pending: list[str] = []
    for stage, name, status in _rows():
        is_checkpoint = "Checkpoint" in name
        if is_checkpoint and status in DONE:
            assert not pending, (
                f"{name} is marked passed, but these stages before it are not "
                f"complete: {pending}"
            )
        elif not is_checkpoint:
            if status in PENDING:
                pending.append(stage)
            elif status in DONE and stage in pending:
                pending.remove(stage)


@pytest.mark.spec("ARCH:build-log-self-checking")
def test_every_completed_stage_has_a_build_log_entry():
    missing = []
    for stage, name, status in _rows():
        # Rows with no stage number — audits, investigations — carry their own
        # document and are checked by the entry/row test below instead.
        if not STAGE.match(stage) or "Checkpoint" in name or status not in DONE:
            continue
        slug = stage.replace(".", ".")
        matches = list(BUILD_LOG.glob(f"{slug}_*.md"))
        if not matches:
            missing.append(stage)
    assert not missing, f"marked complete but no build-log entry: {missing}"


def test_every_build_log_entry_has_an_index_row():
    """The reverse: work recorded but not tracked."""
    indexed = {stage for stage, _, _ in _rows() if stage != "—"}
    orphaned = []
    stage_file = re.compile(r"^(L\d+\.\d+)_")
    for path in BUILD_LOG.glob("L*.md"):
        match = stage_file.match(path.name)
        if match and match.group(1) not in indexed:
            orphaned.append(path.name)
    assert not orphaned, f"build-log entries with no index row: {orphaned}"


@pytest.mark.parametrize("stage", ["L0.1", "L0.2", "L0.3", "L0.4"])
def test_layer_zero_is_complete(stage):
    """Layer 0 is the substrate everything else rests on."""
    statuses = {s: st for s, _, st in _rows()}
    assert statuses.get(stage) in DONE, f"{stage} is {statuses.get(stage)}"
