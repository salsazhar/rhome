"""Write a simulation to disk (``DATA.md`` §20, §21).

Produces the documented directory layout, splitting what a real application
could observe from what only the simulator knows.

The split is physical, not conventional. ``observable/`` holds what the engine
may read; ``hidden/`` holds the latent state and the scenario manifest, and
Guardrail 1 scans engine source for references to those filenames. Keeping the
two in separate directories is what makes that check meaningful.

The generated data is not committed to version control: it is reproducible from
the seed and the generation config. What *is* committed is a checksum manifest,
so a regeneration either reproduces the dataset byte for byte or fails loudly.
Without it, "evaluated against dataset 0.1.0" would be an unverifiable claim.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from rhome_core.muscles import Muscle
from rhome_sim.generate import SimulationResult
from rhome_sim.missingness import SIM_MISSINGNESS, raw_dirty_rows
from rhome_sim.performance import SIM_PERFORMANCE
from rhome_sim.physiology import SIM_PHYSIOLOGY
from rhome_sim.recovery import SIM_RECOVERY
from rhome_sim.scenarios import ScenarioEngine

__all__ = ["DATASET_VERSION", "SCHEMA_VERSION", "write_dataset", "verify_checksums"]

DATASET_VERSION = "0.1.1"
SCHEMA_VERSION = "0.6.0"

#: Day zero of the synthetic calendar. Arbitrary, but fixed, so dates are
#: reproducible and weekday patterns are stable across regenerations.
EPOCH = date(2024, 1, 1)


def _day_date(day_index: int) -> date:
    return EPOCH + timedelta(days=day_index)


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        # Explicit line terminator rather than csv's "\r\n" default: these
        # files are read by people in text editors as well as by pandas, and a
        # default that varies by platform is a poor property for an artefact
        # whose checksum is part of its identity.
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="raise", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) for c in columns})


def _commit_hash() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _constants(obj) -> dict:
    return asdict(obj) if is_dataclass(obj) else dict(obj)


# --- observable tables -----------------------------------------------------

def _daily_recovery_rows(result: SimulationResult) -> list[dict]:
    rows = []
    for day in result.days:
        wake = datetime.combine(_day_date(day.day_index), datetime.min.time()) + timedelta(hours=7.5)
        sleep_min = day.wearable.total_sleep_min
        rows.append({
            "date": _day_date(day.day_index).isoformat(),
            "sleep_start": (wake - timedelta(minutes=sleep_min or 0)).isoformat(timespec="minutes")
                            if sleep_min is not None else None,
            "sleep_end": wake.isoformat(timespec="minutes") if sleep_min is not None else None,
            "total_sleep_min": sleep_min,
            "sleep_efficiency": day.wearable.sleep_efficiency,
            "rem_sleep_min": day.wearable.rem_sleep_min if sleep_min is not None else None,
            "deep_sleep_min": day.wearable.deep_sleep_min if sleep_min is not None else None,
            "hrv_rmssd_ms": day.wearable.hrv_rmssd_ms,
            "resting_hr_bpm": day.wearable.resting_hr_bpm,
            "temperature_deviation_c": day.wearable.temperature_deviation_c,
            "steps": day.wearable.steps,
            "active_minutes": round((day.wearable.steps or 0) / 110.0, 1),
            "bodyweight_kg": day.wearable.body_mass_kg,
            "wearable_missingness": day.wearable_missingness,
        })
    return rows


def _workout_id(day_index: int) -> str:
    return f"w_{day_index:04d}"


def _workout_rows(result: SimulationResult) -> list[dict]:
    rows = []
    for day in result.days:
        if not day.sets and not day.anchor_sets:
            continue
        start = datetime.combine(_day_date(day.day_index), datetime.min.time()) + timedelta(hours=17)
        rows.append({
            "workout_id": _workout_id(day.day_index),
            "date": _day_date(day.day_index).isoformat(),
            "start_time": start.isoformat(timespec="minutes"),
            "duration_min": round(6.0 * len(day.sets) + 12.0, 1),
            "session_type": day.plan.session_type.value if day.plan else "other",
            "planned_session": day.plan.notes_code != "rescheduled" if day.plan else True,
            "session_rpe": None,
            "notes_code": day.plan.notes_code if day.plan else None,
        })
    return rows


def _set_rows(result: SimulationResult) -> list[dict]:
    rows = []
    for day in result.days:
        for performed in day.sets:
            rows.append({
                "workout_id": _workout_id(day.day_index),
                "exercise_id": performed.exercise_id,
                "set_number": performed.set_number,
                "set_type": performed.set_type,
                "external_load_kg": performed.load_kg,
                "reps": performed.reps,
                "rpe": performed.logged_rpe,
                "rir": performed.logged_rir,
                "is_pr": performed.is_pr,
            })
    return rows


def _performance_test_rows(result: SimulationResult) -> list[dict]:
    rows = []
    for day in result.days:
        for performed in day.anchor_sets:
            rows.append({
                "workout_id": _workout_id(day.day_index),
                "date": _day_date(day.day_index).isoformat(),
                "exercise_id": performed.exercise_id,
                "test_type": "low_fatigue_anchor",
                "external_load_kg": performed.load_kg,
                "reps": performed.reps,
                "rpe": performed.logged_rpe,
                "rir": performed.logged_rir,
            })
    return rows


def _exercise_metadata_rows(result: SimulationResult) -> list[dict]:
    def names(muscles):
        return "|".join(m.value for m in muscles)

    return [{
        "exercise_id": e.exercise_id, "name": e.name,
        "movement_pattern": e.movement_pattern.value, "equipment": e.equipment.value,
        "exercise_kind": e.exercise_kind.value,
        "primary_muscles": names(e.primary_muscles),
        "secondary_muscles": names(e.secondary_muscles),
        "stabiliser_muscles": names(e.stabiliser_muscles),
        "stimulus_primary_coeff": e.stimulus_primary_coeff,
        "stimulus_secondary_coeff": e.stimulus_secondary_coeff,
        "fatigue_stabiliser_coeff": e.fatigue_stabiliser_coeff,
        "compoundness": e.compoundness, "systemic_cost": e.systemic_cost,
        "bodyweight_fraction": e.bodyweight_fraction, "axial_load": e.axial_load,
        "eccentric_demand": e.eccentric_demand, "nuzzo_curve": e.nuzzo_curve.value,
        "unilateral": e.unilateral, "coefficient_source": e.coefficient_source.value,
    } for e in sorted(result.library, key=lambda x: x.exercise_id)]


# --- hidden tables ---------------------------------------------------------

def _latent_daily_rows(result: SimulationResult) -> list[dict]:
    rows = []
    for day in result.days:
        row = {
            "date": _day_date(day.day_index).isoformat(),
            "day_index": day.day_index,
            "true_neuromuscular_strain": round(day.state_on_waking.neuromuscular, 6),
            "true_systemic_fatigue": round(day.state_on_waking.systemic, 6),
            "true_recovery_propensity": round(day.latent.recovery_propensity, 6),
            "true_stress": round(day.latent.stress, 6),
            "true_sleep_h": round(day.latent.true_sleep_h, 4),
            "true_log_rmssd_deviation": round(day.latent.true_log_rmssd_deviation, 6),
            "true_resting_hr": round(day.latent.true_resting_hr, 4),
            "true_body_mass_kg": day.body_mass_kg,
            "body_mass_phase": day.body_mass_phase,
            "scenario_labels": "|".join(day.scenario_labels),
        }
        for muscle in Muscle:
            row[f"true_fatigue_{muscle.value}"] = round(
                day.state_on_waking.local_fatigue(muscle), 6
            )
            row[f"true_adaptation_{muscle.value}"] = round(
                day.state_on_waking.adaptation[muscle], 6
            )
        rows.append(row)
    return rows


def _latent_set_rows(result: SimulationResult) -> list[dict]:
    rows = []
    for day in result.days:
        for performed in day.sets:
            rows.append({
                "workout_id": _workout_id(day.day_index),
                "exercise_id": performed.exercise_id,
                "set_number": performed.set_number,
                "set_type": performed.set_type,
                "true_rir": performed.true_rir,
                "true_relative_intensity": performed.true_relative_intensity,
                "true_expressible_capacity": performed.true_expressible_capacity,
                "performance_shock": performed.performance_shock,
                "fatigue_factor": performed.fatigue_factor,
            })
    return rows


# --- writing ---------------------------------------------------------------

def _library_pin(result: SimulationResult) -> dict:
    """The pin of the library this simulation actually ran against."""
    pin = getattr(result.library, "pin", None)
    if pin is None:
        raise ValueError(
            "the simulation's library carries no pin; a dataset must record "
            "which exercise library produced it"
        )
    return pin.as_dict()


def write_dataset(result: SimulationResult, root: Path) -> dict:
    """Write the full dataset and return its quality report."""
    observable = root / "observable"
    hidden = root / "hidden"
    metadata = root / "metadata"

    daily = _daily_recovery_rows(result)
    workouts = _workout_rows(result)
    sets = _set_rows(result)
    anchors = _performance_test_rows(result)
    exercises = _exercise_metadata_rows(result)
    latent_daily = _latent_daily_rows(result)
    latent_sets = _latent_set_rows(result)
    manifest = ScenarioEngine(result.schedule).manifest_rows()

    _write_csv(observable / "daily_recovery.csv", daily, list(daily[0]))
    _write_csv(observable / "workouts.csv", workouts, list(workouts[0]))
    _write_csv(observable / "sets.csv", sets, list(sets[0]))
    _write_csv(observable / "performance_tests.csv", anchors, list(anchors[0]))
    _write_csv(observable / "exercise_metadata.csv", exercises, list(exercises[0]))
    _write_csv(hidden / "latent_daily.csv", latent_daily, list(latent_daily[0]))
    _write_csv(hidden / "latent_sets.csv", latent_sets, list(latent_sets[0]))
    _write_csv(hidden / "scenario_manifest.csv", manifest, list(manifest[0]))

    dirty = [{**r.fields, "defect": r.defect, "expected": r.expected} for r in raw_dirty_rows()]
    _write_csv(metadata / "raw_dirty.csv", dirty, list(dirty[0]))

    config = {
        "dataset_version": DATASET_VERSION,
        "schema_version": SCHEMA_VERSION,
        "seed": result.seed,
        "n_days": len(result.days),
        "commit_hash": _commit_hash(),
        # Which exercise library produced this dataset (L3.9). Pinned by
        # digest rather than by name: nineteen of the twenty-seven v0 exercise
        # ids do not exist in the v1 library, so exchanging the file does not
        # perturb a dataset, it invalidates it — and until this was recorded,
        # nothing in the artefact said which library it had been built from.
        "exercise_library": _library_pin(result),
        "athlete": {
            "athlete_id": result.athlete.athlete_id,
            "initial_body_mass_kg": result.athlete.initial_body_mass_kg,
            "systemic_half_life_h": result.athlete.systemic_half_life_h,
            "neuromuscular_half_life_h": result.athlete.neuromuscular_half_life_h,
            "local_half_life_h": {m.value: v for m, v in result.athlete.local_half_life_h.items()},
            "rep_endurance": dict(result.athlete.rep_endurance),
            "rir_bias": dict(result.athlete.rir_bias),
            "initial_capacity_kg": dict(result.athlete.initial_capacity_kg),
        },
        "simulator_constants": {
            "physiology": _constants(SIM_PHYSIOLOGY),
            "recovery": _constants(SIM_RECOVERY),
            "performance": _constants(SIM_PERFORMANCE),
            "missingness": _constants(SIM_MISSINGNESS),
        },
        "scenario_schedule": manifest,
    }
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "generation_config.json").write_text(
        json.dumps(config, indent=2, default=str), encoding="utf-8"
    )
    (metadata / "schema_version.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION,
                    "dataset_version": DATASET_VERSION,
                    "documents": {"DATA.md": "0.7.0", "MODEL.tex": "0.5",
                                  "PRODUCT.md": "0.3", "RESEARCH.md": "0.3"}}, indent=2),
        encoding="utf-8",
    )

    report = _quality_report(result, daily, workouts, sets, anchors)
    (metadata / "quality_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    checksums = _checksums(root)
    (metadata / "checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    return report


def _quality_report(result, daily, workouts, sets, anchors) -> dict:
    from collections import Counter

    dose = [s for s in sets if s["set_type"] in ("working", "backoff")]
    types = Counter(s["set_type"] for s in sets)
    missing = Counter(d["wearable_missingness"] for d in daily)
    return {
        "dataset_version": DATASET_VERSION,
        "days": len(daily),
        "sessions": len(workouts),
        "sets_total": len(sets),
        "sets_dose_bearing": len(dose),
        "sets_by_type": dict(types),
        "performance_test_sets": len(anchors),
        "personal_records": sum(1 for s in sets if s["is_pr"]),
        "wearable_missingness": {k: round(100 * v / len(daily), 2) for k, v in missing.items()},
        "sets_without_effort": round(
            100 * sum(1 for s in dose if s["rir"] is None) / len(dose), 2
        ),
        "days_without_body_mass": round(
            100 * sum(1 for d in daily if d["bodyweight_kg"] is None) / len(daily), 2
        ),
        "body_mass_kg": {
            "start": result.days[0].body_mass_kg,
            "end": result.days[-1].body_mass_kg,
            "min": min(d.body_mass_kg for d in result.days),
            "max": max(d.body_mass_kg for d in result.days),
        },
        "capacity_change_pct": {
            e: round(100 * (result.athlete.initial_capacity_kg[e] and
                            (_final_capacity(result, e) / result.athlete.initial_capacity_kg[e] - 1)), 1)
            for e in ("bench_press", "back_squat", "deadlift", "overhead_press")
        },
    }


def _final_capacity(result: SimulationResult, exercise_id: str) -> float:
    """Recover final capacity from the last recorded expressible value."""
    for day in reversed(result.days):
        for performed in reversed(day.sets):
            if performed.exercise_id == exercise_id and performed.fatigue_factor > 0:
                return performed.true_expressible_capacity / performed.fatigue_factor
    return result.athlete.initial_capacity_kg[exercise_id]


def _checksums(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*.csv")) + sorted(root.rglob("*.json")):
        if path.name == "checksums.json":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out[str(path.relative_to(root))] = digest
    return out


def verify_checksums(root: Path) -> list[str]:
    """Return the paths whose contents no longer match the recorded manifest."""
    recorded = json.loads((root / "metadata" / "checksums.json").read_text(encoding="utf-8"))
    current = _checksums(root)
    mismatched = [p for p in sorted(set(recorded) | set(current))
                  if recorded.get(p) != current.get(p)]
    return mismatched
