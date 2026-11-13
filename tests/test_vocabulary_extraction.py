"""Exercise vocabulary extraction and the frozen mapping (L3.10).

L3.10 is the one place the project deliberately opens sealed data, so the bound
on what it reads has to be a property of the code that can be checked, not a
promise in a docstring. These tests check it, and check that the mapping cannot
be used before it has been reviewed.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from rhome_eval.vocabulary import (
    ExerciseMapping,
    MappingError,
    load_mapping,
    mapping_path,
)

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / "tools" / "extract_exercise_vocabulary.py"
VOCABULARY = ROOT / "data" / "real_vocabulary.json"

#: Every other column of `training_sets`. The extractor must name none of them.
FORBIDDEN_COLUMNS = (
    "workout_uuid", "workout_date", "workout_timestamp_utc", "workout_title",
    "workout_notes", "workout_duration_seconds", "workout_personal_bests",
    "exercise_instance_id", "exercise_order", "exercise_notes", "exercise_id",
    "canonical_name", "muscle_group", "muscle_subgroup", "exercise_type",
    "set_id", "set_number", "reps", "min_reps", "max_reps", "weight_stored_lb",
    "weight_kg", "distance_stored", "set_duration_seconds", "set_wdf",
    "set_rpe", "is_done", "estimated_one_rep_max", "is_personal_best",
    "placeholder_weight", "placeholder_reps", "placeholder_distance",
)


def _executable_strings(path: Path) -> list[str]:
    """String literals the module actually evaluates, docstrings excluded.

    The same distinction Guardrail 1 draws in ``rhome_core.architecture``: a
    module explaining a boundary it must not cross should not be reported for
    breaching it. Comments never reach the AST, and docstrings are skipped, so
    what remains is what the code does rather than what it says about itself.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


# --- the bound on what may be read -------------------------------------------

@pytest.mark.spec("DATA:vocabulary-extraction-bounded")
def test_the_extractor_names_no_column_but_the_exercise_name():
    """D9's exception, enforced by reading the tool's own source.

    The disclosure at L3.10 is bounded to the sorted distinct exercise-name
    strings. A docstring saying so is worth nothing after the fact; this asserts
    it of the file, so widening the extraction cannot happen quietly.
    """
    executable = _executable_strings(EXTRACTOR)
    named = sorted(
        {column for column in FORBIDDEN_COLUMNS for text in executable if column in text}
    )
    assert not named, (
        f"the extractor references {named} in executable code, which is outside "
        f"L3.10's declared bound of exercise names only"
    )
    assert any("exercise_name" in text for text in executable)


@pytest.mark.spec("DATA:vocabulary-extraction-bounded")
def test_the_extractor_issues_exactly_one_query_and_it_is_a_constant():
    """A query built at the call site is a query that can quietly grow."""
    import tools.extract_exercise_vocabulary as extractor  # noqa: PLC0415

    query = extractor.QUERY.lower()
    assert query == (
        "select distinct exercise_name from training_sets order by exercise_name"
    )
    for banned in ("count(", "sum(", "group by", "join", "where", "*"):
        assert banned not in query, f"the query contains {banned!r}"

    tree = ast.parse(EXTRACTOR.read_text(encoding="utf-8"))
    executes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
    ]
    assert len(executes) == 1, f"{len(executes)} execute() calls; expected one"
    assert isinstance(executes[0].args[0], ast.Name), (
        "the query must be passed as the module constant, not built inline"
    )


@pytest.mark.spec("DATA:vocabulary-extraction-bounded")
def test_the_extractor_never_opens_the_sealed_file_with_sqlite():
    """SQLite's read-only mode is not read-only enough.

    The first version opened the archive with ``mode=ro`` and SQLite created
    ``-shm`` and ``-wal`` sidecar files beside it, because the database is in
    WAL journal mode. Nothing was written to the database, but two files
    appeared inside a sealed directory and ``tools/seal_real_data.py`` reported
    the seal broken — which is what it is for. The archive is now copied and the
    copy is queried.
    """
    assert "shutil.copyfile" in EXTRACTOR.read_text(encoding="utf-8"), (
        "the archive must be copied, not opened in place"
    )
    opened = [text for text in _executable_strings(EXTRACTOR) if "mode=ro" in text]
    assert not opened, (
        "mode=ro still creates WAL sidecar files inside the sealed directory"
    )


@pytest.mark.spec("DATA:vocabulary-extraction-bounded")
def test_the_committed_vocabulary_records_its_own_provenance():
    if not VOCABULARY.exists():
        pytest.skip("vocabulary not extracted")
    payload = json.loads(VOCABULARY.read_text(encoding="utf-8"))
    for field in ("extracted_on", "source", "source_sha256", "query", "disclosure"):
        assert payload.get(field), f"the vocabulary does not record {field}"
    assert payload["names"], "no names extracted"
    assert payload["distinct_names"] == len(payload["names"])
    assert payload["names"] == sorted(set(payload["names"])), (
        "names must be sorted and distinct, so no frequency survives the order"
    )


# --- the freeze ---------------------------------------------------------------

def _write(tmp_path: Path, **overrides) -> Path:
    payload = {
        "stage": "L3.10",
        "library": "v1.1",
        "reviewed": True,
        "mappings": [
            {"logged_name": "Barbell Bench Press", "verdict": "exact",
             "exercise_id": "barbell_bench_press"},
            {"logged_name": "Jackknife", "verdict": "derive", "exercise_id": None},
        ],
    }
    payload.update(overrides)
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_an_unreviewed_mapping_is_refused(tmp_path):
    """The guard, exercised by a caller that has not done the review."""
    with pytest.raises(MappingError, match="not reviewed"):
        load_mapping(_write(tmp_path, reviewed=False))


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_a_missing_mapping_is_refused(tmp_path):
    with pytest.raises(MappingError, match="no exercise mapping"):
        load_mapping(tmp_path / "absent.json")


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_a_name_neither_mapped_nor_marked_for_derivation_is_refused(tmp_path):
    """Silently dropping a name would delete training load from the history."""
    path = _write(tmp_path, mappings=[
        {"logged_name": "Pec Deck", "verdict": "review", "exercise_id": None},
    ])
    with pytest.raises(MappingError, match="neither mapped nor marked"):
        load_mapping(path)


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_a_reviewed_mapping_loads_and_distinguishes_derive_from_absent(tmp_path):
    mapping = load_mapping(_write(tmp_path))
    assert len(mapping) == 2
    assert mapping.library_id("Barbell Bench Press") == "barbell_bench_press"
    assert mapping.library_id("Jackknife") is None, "derive is a value, not an absence"
    assert mapping.derived_names == ("Jackknife",)
    assert mapping.digest

    with pytest.raises(MappingError, match="no mapping for logged exercise"):
        mapping.library_id("Zercher Squat")


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_the_digest_changes_when_the_mapping_changes(tmp_path):
    """Content-addressed, so a later run can prove which mapping it used."""
    first = load_mapping(_write(tmp_path))
    other = tmp_path / "second.json"
    payload = json.loads((tmp_path / "mapping.json").read_text(encoding="utf-8"))
    payload["mappings"][0]["exercise_id"] = "paused_barbell_bench_press"
    other.write_text(json.dumps(payload), encoding="utf-8")

    assert load_mapping(other).digest != first.digest


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_the_committed_mapping_is_reviewed_frozen_and_complete():
    """The real artefact, reviewed by the athlete and frozen.

    Until the review this asserted the *opposite* — that the mapping was
    unreviewed and refused to load — and failed deliberately the moment
    ``reviewed`` was set, which is what re-pointed it here.
    """
    if not mapping_path().exists() or not VOCABULARY.exists():
        pytest.skip("mapping not proposed")

    mapping = load_mapping()
    names = json.loads(VOCABULARY.read_text(encoding="utf-8"))["names"]

    assert set(mapping.resolved) == set(names), (
        "every logged name must be mapped, and no others"
    )
    assert mapping.library == "v1.2"
    assert len(mapping.digest) == 64

    payload = json.loads(mapping_path().read_text(encoding="utf-8"))
    assert payload["reviewed"] is True
    assert payload.get("reviewed_on"), "a freeze must record when it happened"


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_every_mapped_id_exists_in_the_library_it_names():
    """A mapping to an id the library does not have would fail at L3.12.

    L3.12 is a one-shot run. An id that resolves to nothing must be caught now,
    while it is a typo, rather than then, when it is a wasted opening.
    """
    from rhome_core.exercises import load_library, library_path as lib_path

    mapping = load_mapping()
    library = load_library(lib_path().parent / "exercise_library_v1_2.csv")

    missing = sorted(
        {eid for eid in mapping.resolved.values() if eid is not None and eid not in library}
    )
    assert not missing, f"{len(missing)} mapped ids are absent from v1.2: {missing}"

    resolved = sum(1 for v in mapping.resolved.values() if v is not None)
    assert resolved >= 60, f"only {resolved} names resolved to a library exercise"


def test_repair_unmerges_the_confirmed_incomparable_machine_scales():
    mapping = load_mapping().resolved
    assert mapping["Calf Raise"] == "standing_calf_raise_machine"
    assert mapping["Seated Machine Calf Raise"] == "plate_loaded_seated_calf_raise"
    assert mapping["Seated Machine Leg Extension"] == "selectorized_leg_extension"
    assert mapping["Machine Leg Extension"] == "leg_extension"


@pytest.mark.spec("DATA:mapping-frozen-before-use")
def test_the_review_is_recorded_as_having_changed_something():
    """What the review was worth, kept as a number rather than an impression.

    The athlete overrode the matcher on 18 of 68 rows. If that figure ever went
    to zero the review would have become a rubber stamp, and the mapping would
    be the matcher's opinion wearing the athlete's authority.
    """
    payload = json.loads(mapping_path().read_text(encoding="utf-8"))
    overridden = [r for r in payload["mappings"] if r.get("changed_by_review")]
    assert len(overridden) > 10, (
        f"only {len(overridden)} rows were changed by review; a review that "
        f"changes almost nothing is not evidence the mapping was checked"
    )


@pytest.mark.spec("DATA:vocabulary-extraction-bounded")
def test_the_bound_check_catches_a_widened_extraction(tmp_path):
    """D3: a check that has never rejected anything is not known to work.

    Plants an extractor that reaches for one more column and requires the same
    inspection used above to catch it — and requires prose *about* a column not
    to be caught, since that is the failure mode the docstring exemption exists
    for and the one this test file itself tripped on first.
    """
    widened = tmp_path / "widened.py"
    widened.write_text(
        '"""Mentions set_rpe and weight_kg in prose, which is allowed."""\n'
        'QUERY = "SELECT DISTINCT exercise_name, set_rpe FROM training_sets"\n',
        encoding="utf-8",
    )
    executable = _executable_strings(widened)
    caught = [c for c in FORBIDDEN_COLUMNS for text in executable if c in text]
    assert "set_rpe" in caught, "a widened query must be caught"
    assert "weight_kg" not in caught, "a column named only in prose must not be"

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        '"""Explains that set_rpe must never be read."""\n'
        'QUERY = "SELECT DISTINCT exercise_name FROM training_sets"\n',
        encoding="utf-8",
    )
    assert not [
        c for c in FORBIDDEN_COLUMNS for text in _executable_strings(innocent) if c in text
    ], "prose describing the boundary must not be reported as breaching it"
