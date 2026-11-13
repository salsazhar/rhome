"""Model version freezing (L3.16, ``BUILD_PLAN.md`` L3.11 validation regime).

The regime D22 declares — score a version on sessions that post-date its
freeze — is only a procedure if the stamp cannot lie. So these tests do not
check that a version *can* be recorded; they check that the ways of making it
lie are closed:

- a changed parameter that leaves the digest alone,
- changed engine source that leaves the digest alone,
- a record edited after the fact,
- the same model frozen twice under two labels,
- a freeze date read from a tree with uncommitted engine changes,
- a file carved out of the digest that the engine can nonetheless import.

Each is attempted, not asserted about.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from rhome_core.parameters import CORE_PARAMETERS
from rhome_eval import version as V


#: A fixed answer for "when did the engine last change", so these tests are
#: about the record's integrity rather than about the state of the working
#: tree. The real git read has its own test below.
STAMP = ("2026-08-24T22:23:33+01:00", "39f385db29188a8c9321d8aa8a11aa8e67f3e738")


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    """A freshly captured version, recorded into a throwaway file."""
    monkeypatch.setattr(V, "VERSIONS_PATH", tmp_path / "model_versions.json")
    monkeypatch.setattr(V, "last_engine_change", lambda: STAMP)
    return V.record(V.capture("vtest", known_defects=("LIM-38",)))


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_a_changed_parameter_cannot_keep_the_same_digest():
    """Attempt the violation: move a registered value, keep the stamp."""
    before = V.parameters_digest()

    target = CORE_PARAMETERS["stimulus_primary_coeff"]
    moved = replace(target, value=target.value + 0.01)
    original = dict(CORE_PARAMETERS._parameters)
    CORE_PARAMETERS._parameters["stimulus_primary_coeff"] = moved
    try:
        after = V.parameters_digest()
    finally:
        CORE_PARAMETERS._parameters.clear()
        CORE_PARAMETERS._parameters.update(original)

    assert after != before, (
        "a registered parameter changed and the digest did not; a frozen "
        "version could then claim code it is not"
    )
    assert V.parameters_digest() == before, "restoring the value must restore the digest"


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_changed_engine_source_cannot_keep_the_same_digest(tmp_path, monkeypatch):
    """Attempt the violation: edit the engine, keep the stamp."""
    tree = tmp_path / "src" / "rhome_engine"
    tree.mkdir(parents=True)
    module = tree / "state.py"
    module.write_text("HALF_LIFE = 30.0\n", encoding="utf-8")

    monkeypatch.setattr(V, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(V, "ENGINE_PATHS", ("src/rhome_engine",))

    before = V.source_digest()
    module.write_text("HALF_LIFE = 42.0\n", encoding="utf-8")
    assert V.source_digest() != before, (
        "engine source changed and the digest did not"
    )


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_nothing_excluded_from_the_digest_can_reach_a_prediction():
    """The carve-out is a hole the moment the engine imports what it excludes.

    ``EXCLUDED_SOURCES`` exists so registering a conformance clause does not
    read as a model change. That is only safe while the excluded files cannot
    influence a prediction, which this checks by import rather than by belief.
    """
    engine = [
        p
        for root in ("src/rhome_engine", "src/rhome_core")
        for p in (V.REPO_ROOT / root).rglob("*.py")
    ]
    for entry in V.EXCLUDED_SOURCES:
        module = Path(entry).stem
        importers = [
            p.relative_to(V.REPO_ROOT)
            for p in engine
            if p != V.REPO_ROOT / entry
            and re.search(rf"\b(?:import|from)\s+[\w.]*\b{module}\b", p.read_text(encoding="utf-8"))
        ]
        assert not importers, (
            f"{entry} is excluded from the version digest but is imported by "
            f"{importers}; a change to it could move a prediction without "
            "moving the stamp"
        )


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_a_record_edited_after_the_fact_fails_verification(recorded):
    assert recorded.verify()
    tampered = replace(recorded, frozen_at="2020-01-01T00:00:00+00:00")
    assert not tampered.verify(), (
        "a freeze date was moved and the record still verified"
    )


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_the_same_model_cannot_be_frozen_twice_under_two_labels(recorded):
    with pytest.raises(V.VersionError, match="already recorded"):
        V.record(V.capture("vtest"))
    with pytest.raises(V.VersionError, match="nothing has changed"):
        V.record(V.capture("vtest-again"))


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_a_freeze_is_refused_while_engine_paths_are_dirty(monkeypatch):
    """A date read from a dirty tree describes code that is not what ran."""
    monkeypatch.setattr(
        V, "_git", lambda *args: " M src/rhome_engine/state.py" if args[0] == "status" else "x"
    )
    with pytest.raises(V.VersionError, match="uncommitted"):
        V.last_engine_change()


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_the_stamp_separates_sessions_before_and_after_it(recorded):
    """The whole point: which sessions are the prospective exam."""
    frozen = V._instant(recorded.frozen_at)
    before = frozen.replace(year=frozen.year - 1).isoformat()
    after = frozen.replace(year=frozen.year + 1).isoformat()

    assert not recorded.covers(before), "a session predating the freeze was counted"
    assert recorded.covers(after), "a session after the freeze was not counted"


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_drift_names_what_moved(recorded, monkeypatch):
    assert V.drift(recorded) == {}, "a freshly recorded version must not have drifted"

    monkeypatch.setattr(V, "parameters_digest", lambda: "0" * 32)
    moved = V.drift(recorded)
    assert "parameters" in moved


@pytest.mark.spec("ARCH:model-version-freeze-stamp")
def test_a_recorded_version_round_trips_through_the_file(recorded, tmp_path):
    payload = json.loads((tmp_path / "model_versions.json").read_text(encoding="utf-8"))
    assert [r["label"] for r in payload["versions"]] == ["vtest"]

    loaded = V.load_versions()[-1]
    assert loaded == recorded
    assert loaded.verify()
    assert loaded.known_defects == ("LIM-38",), (
        "a version's known defects must survive the record, or a later reader "
        "mistakes its score for a clean one"
    )
