"""Dataset generation and output (``DATA.md`` §18, §20, §21)."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict

import pytest

from rhome_core.exercises import load_library
from rhome_sim.dataset import (
    DATASET_VERSION,
    verify_checksums,
    write_dataset,
)
from rhome_sim.generate import simulate

LIBRARY = load_library()
INCREMENTS = {"barbell": 2.5, "machine": 5.0, "cable": 2.5, "dumbbell": 2.0, "bodyweight": 2.5}


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    root = tmp_path_factory.mktemp("dataset") / "athlete_a"
    result = simulate(20260822)
    report = write_dataset(result, root)
    return root, result, report


def _rows(root, relative):
    with (root / relative).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# --- layout (DATA.md §20) --------------------------------------------------

@pytest.mark.spec("DATA:output-layout")
@pytest.mark.parametrize(
    "relative",
    [
        "observable/daily_recovery.csv", "observable/workouts.csv",
        "observable/sets.csv", "observable/exercise_metadata.csv",
        "observable/performance_tests.csv",
        "hidden/latent_daily.csv", "hidden/latent_sets.csv",
        "hidden/scenario_manifest.csv",
        "metadata/generation_config.json", "metadata/schema_version.json",
        "metadata/quality_report.json",
    ],
)
def test_every_documented_file_is_written(written, relative):
    root, _, _ = written
    assert (root / relative).exists(), f"missing {relative}"
    assert (root / relative).stat().st_size > 0


@pytest.mark.spec("DATA:output-layout")
@pytest.mark.guardrail(1)
def test_no_latent_column_leaks_into_the_observable_tables(written):
    """The separation is physical, which is what makes Guardrail 1 meaningful."""
    root, _, _ = written
    for name in ("daily_recovery.csv", "workouts.csv", "sets.csv", "performance_tests.csv"):
        columns = _rows(root, f"observable/{name}")[0].keys()
        leaked = [c for c in columns if c.startswith("true_") or "scenario" in c
                  or "shock" in c or "latent" in c]
        assert not leaked, f"{name} exposes simulator-only columns: {leaked}"


def test_the_hidden_tables_carry_the_ground_truth(written):
    root, _, _ = written
    columns = set(_rows(root, "hidden/latent_daily.csv")[0])
    assert any(c.startswith("true_fatigue_") for c in columns)
    assert "true_recovery_propensity" in columns
    assert "true_stress" in columns
    assert "scenario_labels" in columns


# --- config and reproducibility (DATA.md §20) ------------------------------

@pytest.mark.spec("DATA:generation-config")
def test_the_config_records_everything_needed_to_regenerate(written):
    root, result, _ = written
    config = json.loads((root / "metadata" / "generation_config.json").read_text())
    assert config["seed"] == result.seed
    assert config["dataset_version"] == DATASET_VERSION
    assert config["n_days"] == len(result.days)
    for block in ("physiology", "recovery", "performance", "missingness"):
        assert config["simulator_constants"][block]
    assert config["athlete"]["local_half_life_h"]
    assert config["athlete"]["rep_endurance"]
    assert config["scenario_schedule"]


def test_the_commit_hash_is_recorded(written):
    """Seed alone is not enough: the same seed on different code differs."""
    root, _, _ = written
    config = json.loads((root / "metadata" / "generation_config.json").read_text())
    assert "commit_hash" in config


@pytest.mark.spec("DATA:reproducible-under-seed")
def test_regeneration_reproduces_the_dataset_byte_for_byte(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_dataset(simulate(7, n_days=120), first)
    write_dataset(simulate(7, n_days=120), second)

    a = json.loads((first / "metadata" / "checksums.json").read_text())
    b = json.loads((second / "metadata" / "checksums.json").read_text())
    differing = [k for k in a if k != "metadata/generation_config.json" and a[k] != b.get(k)]
    assert not differing, f"regeneration differs in {differing}"


@pytest.mark.spec("DATA:reproducible-under-seed")
def test_checksums_verify_and_detect_tampering(written):
    root, _, _ = written
    assert verify_checksums(root) == [], "freshly written dataset fails its own checksums"

    # Bytes, not text: reading and rewriting as text normalises line endings
    # and would change the checksum on restore.
    target = root / "observable" / "sets.csv"
    original = target.read_bytes()
    target.write_bytes(original.replace(b"w_0000", b"w_9999", 1))
    try:
        assert "observable/sets.csv" in verify_checksums(root), (
            "an edited file was not detected"
        )
    finally:
        target.write_bytes(original)
    assert verify_checksums(root) == []


# --- realism invariants (DATA.md §18) --------------------------------------

@pytest.mark.spec("DATA:realism-invariants")
def test_loads_land_on_realistic_increments(written):
    root, _, _ = written
    for row in _rows(root, "observable/sets.csv"):
        if row["set_type"] == "warmup":
            continue  # warm-up loads are a fraction of the working load
        step = INCREMENTS[LIBRARY[row["exercise_id"]].equipment.value]
        load = float(row["external_load_kg"])
        assert abs(load / step - round(load / step)) < 1e-6, (
            f"{row['exercise_id']} at {load} is not a multiple of {step}"
        )


@pytest.mark.spec("DATA:realism-invariants")
def test_no_physiologically_impossible_set(written):
    """``DATA.md`` §18: no 20 repetitions at 95% of one-repetition maximum."""
    root, result, _ = written
    latent = {(r["workout_id"], r["exercise_id"], r["set_number"]): r
              for r in _rows(root, "hidden/latent_sets.csv")}
    for row in _rows(root, "observable/sets.csv"):
        if row["set_type"] == "warmup":
            continue
        key = (row["workout_id"], row["exercise_id"], row["set_number"])
        intensity = float(latent[key]["true_relative_intensity"])
        reps = int(row["reps"])
        assert not (reps >= 12 and intensity > 0.85), (
            f"{reps} reps at {intensity:.0%} of maximum is not possible"
        )
        assert not (reps <= 2 and intensity < 0.55), (
            f"{reps} reps at {intensity:.0%} would not stop there"
        )


@pytest.mark.spec("DATA:realism-invariants")
def test_sleep_stages_never_exceed_total_sleep(written):
    root, _, _ = written
    for row in _rows(root, "observable/daily_recovery.csv"):
        if not row["total_sleep_min"]:
            continue
        total = float(row["total_sleep_min"])
        stages = float(row["rem_sleep_min"] or 0) + float(row["deep_sleep_min"] or 0)
        assert stages <= total


@pytest.mark.spec("DATA:realism-invariants")
def test_body_mass_moves_slowly_and_within_the_documented_range(written):
    root, _, report = written
    masses = [float(r["bodyweight_kg"]) for r in _rows(root, "observable/daily_recovery.csv")
              if r["bodyweight_kg"]]
    spread = report["body_mass_kg"]["max"] - report["body_mass_kg"]["min"]
    assert 3.0 <= spread <= 6.0, f"underlying mass moved {spread:.1f} kg over two years"
    # Day-to-day scale readings are noisier than the tissue trend beneath them.
    daily_steps = [abs(b - a) for a, b in zip(masses, masses[1:])]
    assert max(daily_steps) < 4.0
    assert 0.4 <= sum(daily_steps) / len(daily_steps) <= 1.5


@pytest.mark.spec("DATA:realism-invariants")
def test_every_set_belongs_to_a_recorded_workout(written):
    root, _, _ = written
    workouts = {r["workout_id"] for r in _rows(root, "observable/workouts.csv")}
    for row in _rows(root, "observable/sets.csv"):
        assert row["workout_id"] in workouts


def test_set_numbers_are_unique_and_contiguous_within_an_exercise(written):
    root, _, _ = written
    seen = defaultdict(list)
    for row in _rows(root, "observable/sets.csv"):
        seen[(row["workout_id"], row["exercise_id"])].append(int(row["set_number"]))
    for key, numbers in seen.items():
        assert len(numbers) == len(set(numbers)), f"duplicate set numbers in {key}"
        assert numbers == list(range(1, len(numbers) + 1)), f"gap in set numbers in {key}"


def test_warm_ups_carry_no_effort_rating(written):
    """They are stored for context and contribute no dose."""
    root, _, _ = written
    for row in _rows(root, "observable/sets.csv"):
        if row["set_type"] == "warmup":
            assert not row["rpe"] and not row["rir"]


def test_all_four_set_types_are_present(written):
    root, _, report = written
    types = report["sets_by_type"]
    for expected in ("warmup", "working", "backoff", "drop"):
        assert types.get(expected, 0) > 0, f"no {expected} sets were generated"
    assert types["working"] > types["backoff"] > types["drop"]


def test_personal_records_are_never_flagged_on_warm_ups_or_drops(written):
    root, _, _ = written
    for row in _rows(root, "observable/sets.csv"):
        if row["set_type"] in ("warmup", "drop"):
            assert row["is_pr"] == "False"


# --- scale (DATA.md §4.2) --------------------------------------------------

def test_the_dataset_is_the_documented_size(written):
    _, _, report = written
    assert report["days"] == 730
    assert 470 <= report["sessions"] <= 510
    assert 7500 <= report["sets_dose_bearing"] <= 8500
    assert 60 <= report["performance_test_sets"] <= 120


def test_the_quality_report_agrees_with_the_files(written):
    root, _, report = written
    assert report["days"] == len(_rows(root, "observable/daily_recovery.csv"))
    assert report["sessions"] == len(_rows(root, "observable/workouts.csv"))
    assert report["sets_total"] == len(_rows(root, "observable/sets.csv"))
    assert report["performance_test_sets"] == len(_rows(root, "observable/performance_tests.csv"))


# --- library versioning (L3.9) ------------------------------------------------

@pytest.mark.spec("DATA:library-pinned-to-dataset")
def test_the_dataset_records_which_exercise_library_produced_it(written):
    """``DATA.md`` §20: the config must record everything needed to regenerate.

    The library was the one input it did not record. That gap is not benign:
    nineteen of the twenty-seven v0 exercise ids do not exist in the
    athlete-authored v1 library, so exchanging the file does not perturb a
    dataset, it invalidates it — and nothing in the artefact would have said
    which library it came from.
    """
    import json

    from rhome_core.exercises import library_path, library_pin

    root, _, _ = written
    config = json.loads((root / "metadata" / "generation_config.json").read_text())
    assert "exercise_library" in config, "the dataset does not record its library"

    pin = config["exercise_library"]
    actual = library_pin(library_path())
    assert pin["sha256"] == actual.digest, (
        "the recorded library digest does not match the library on disk"
    )
    assert pin["version"] == "v0", pin
    assert pin["exercises"] == 27, pin


@pytest.mark.spec("DATA:library-pinned-to-dataset")
def test_the_pin_is_content_addressed_not_declared(tmp_path):
    """A version string a human maintains is one that eventually lies.

    Editing a library by a single byte must change its identity, and must be
    reported as unregistered rather than silently keeping the old version.
    """
    from rhome_core.exercises import library_path, library_pin

    original = library_pin(library_path())
    assert original.version == "v0" and original.is_registered

    edited = tmp_path / "exercise_library.csv"
    text = library_path().read_text(encoding="utf-8")
    edited.write_text(text.replace("0.78", "0.79", 1), encoding="utf-8")

    tampered = library_pin(edited)
    assert tampered.digest != original.digest, "a byte change must change the digest"
    assert tampered.version == "unregistered", (
        "an unrecognised library must be reported as unregistered, not assumed "
        "to be the version it was edited from"
    )
    assert not tampered.is_registered
    assert not original.matches(tampered)


@pytest.mark.spec("DATA:library-pinned-to-dataset")
def test_every_registered_library_matches_its_recorded_digest():
    """The registry is checked against the files, in both directions."""
    from rhome_core.exercises import known_libraries, library_path, library_pin

    registry = known_libraries()
    assert registry, "no libraries registered"
    directory = library_path().parent

    for version, entry in registry.items():
        path = directory / entry["filename"]
        assert path.exists(), f"{version} names a file that does not exist: {path}"
        pin = library_pin(path)
        assert pin.digest == entry["sha256"], f"{version} has drifted from its digest"
        assert pin.exercises == entry["exercises"], (
            f"{version} records {entry['exercises']} exercises, file has {pin.exercises}"
        )
        assert pin.version == version


@pytest.mark.spec("DATA:library-pinned-to-dataset")
def test_a_dataset_cannot_be_written_without_a_library_pin(tmp_path):
    """The guard, exercised by a caller that gets it wrong."""
    from dataclasses import replace

    from rhome_core.exercises import ExerciseLibrary
    from rhome_sim.dataset import write_dataset
    from rhome_sim.generate import simulate

    result = simulate(7, n_days=60)
    unpinned = ExerciseLibrary(result.library.exercises, pin=None)
    result.library = unpinned

    with pytest.raises(ValueError, match="carries no pin"):
        write_dataset(result, tmp_path / "athlete_a")
