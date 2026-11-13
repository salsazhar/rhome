"""Simulation runner: drives the whole chain day by day.

Composes the athlete, physiology, recovery, programme, performance and scenario
components into one deterministic pass over the calendar. L1.8 adds writing the
result to disk, the generation config and the quality report; this module owns
the loop itself.

The daily order matters and follows ``DATA.md`` §9.5. Recovery physiology for a
day is resolved on waking, using the systemic load carried *into* the day, and
training happens afterwards. Reversing that would let a session influence the
autonomic data recorded before it took place.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from rhome_core.exercises import ExerciseLibrary, load_library
from rhome_core.seeding import RootSeed
from rhome_sim.athlete import AthleteParameters, sample_athlete
from rhome_sim.missingness import MissingnessModel
from rhome_sim.performance import PerformanceModel, RealisedSet
from rhome_sim.physiology import LatentState, Physiology
from rhome_sim.programme import Prescription, ProgrammeGenerator, SessionPlan
from rhome_sim.recovery import LatentDay, RecoveryModel, WearableReading
from rhome_sim.scenarios import (
    SCENARIO_SCHEDULE,
    Scenario,
    ScenarioEngine,
    ScenarioWindow,
)

__all__ = ["DayRecord", "SimulationResult", "simulate"]

#: Hours after waking at which training happens.
_TRAINING_OFFSET_H = 9.0
_WAKE_OFFSET_H = 8.0

#: Body-mass phases across the two years (``DATA.md`` §12): a modest gain, a
#: maintenance stretch, a cut, then a second gain. Values are kilograms per day
#: of underlying tissue mass, which the daily scale reading then obscures.
_BODY_MASS_PHASES: tuple[tuple[int, int, float, str], ...] = (
    (0, 239, +0.0160, "gain"),
    (240, 449, +0.0005, "maintenance"),
    (450, 599, -0.0200, "cut"),
    (600, 9999, +0.0090, "gain"),
)


def _body_mass_drift(day_index: int) -> tuple[float, str]:
    for first, last, per_day, label in _BODY_MASS_PHASES:
        if first <= day_index <= last:
            return per_day, label
    return 0.0, "maintenance"


#: Exercises used as periodic performance anchors (``DATA.md`` §5.5), and how
#: often each is tested. Anchors are performed in a deliberately low-fatigue
#: state and carry reduced reporting noise, which is what earns them the
#: heavier weight the engine gives them.
_ANCHOR_EXERCISES: tuple[str, ...] = (
    "bench_press", "back_squat", "deadlift", "overhead_press", "weighted_pullup",
)
_ANCHOR_INTERVAL_DAYS = 28

#: Smallest load change available on each kind of equipment, in kilograms.
_EQUIPMENT_INCREMENT = {
    "barbell": 2.5, "machine": 5.0, "cable": 2.5, "dumbbell": 2.0, "bodyweight": 2.5,
}


@dataclass
class DayRecord:
    """Everything that happened on one simulated day."""

    day_index: int
    latent: LatentDay
    wearable: WearableReading
    plan: SessionPlan | None
    sets: list[RealisedSet]
    scenario_labels: tuple[str, ...]
    #: ``none`` / ``partial`` / ``full``, per ``DATA.md`` §5.1.
    wearable_missingness: str
    body_mass_kg: float
    #: Latent physiological state snapshot, taken on waking.
    state_on_waking: LatentState
    body_mass_phase: str = "maintenance"
    #: Sets performed as standardised anchors rather than ordinary training.
    anchor_sets: list[RealisedSet] = field(default_factory=list)


@dataclass
class SimulationResult:
    seed: int
    athlete: AthleteParameters
    library: ExerciseLibrary
    days: list[DayRecord] = field(default_factory=list)
    schedule: tuple[ScenarioWindow, ...] = ()

    @property
    def sets(self) -> list[RealisedSet]:
        return [s for day in self.days for s in day.sets]

    @property
    def sessions(self) -> list[DayRecord]:
        return [d for d in self.days if d.sets]

    def days_in(self, first: int, last: int) -> list[DayRecord]:
        return [d for d in self.days if first <= d.day_index <= last]


def simulate(
    seed: int,
    n_days: int = 730,
    schedule: tuple[ScenarioWindow, ...] = SCENARIO_SCHEDULE,
    library: ExerciseLibrary | None = None,
) -> SimulationResult:
    """Run the full simulation. Deterministic under ``seed``."""
    library = library or load_library()
    root = RootSeed(seed)
    athlete = sample_athlete(seed, library=library)

    physiology = Physiology(athlete)
    recovery = RecoveryModel(athlete, root.stream("sim.recovery"))
    programme = ProgrammeGenerator(library, root.stream("sim.programme"))
    performance = PerformanceModel(athlete, library, root.stream("sim.performance"))
    scenarios = ScenarioEngine(schedule)
    mass_rng = root.stream("sim.body_mass")
    missingness = MissingnessModel(root.stream("sim.missingness"))
    last_anchor: dict[str, int] = {}

    plans = {p.day_index: p for p in programme.plan_days(n_days)}
    result = SimulationResult(seed=seed, athlete=athlete, library=library, schedule=schedule)
    body_mass = athlete.initial_body_mass_kg

    for day_index in range(n_days):
        modifiers = scenarios.modifiers_for(day_index)

        # Recovery resolves on waking, from the load carried into the day.
        latent = recovery.step(
            day_index,
            systemic_load=physiology.state.systemic,
            stress_shock=modifiers.stress_shock,
            sleep_override_h=modifiers.sleep_override_h,
            temperature_offset=modifiers.temperature_offset,
            steps_override=modifiers.steps_override,
            propensity_bonus=modifiers.recovery_bonus,
        )
        propensity = latent.recovery_propensity

        wake_h = day_index * 24.0 + _WAKE_OFFSET_H
        physiology.advance_to(wake_h, recovery_propensity=propensity)
        state_on_waking = physiology.state.copy()
        wearable = recovery.observe(latent, body_mass_kg=body_mass)
        wearable = missingness.apply_to_body_mass(wearable)
        travelling = Scenario.TRAVEL.value in scenarios.labels_for(day_index)
        wearable, missing_label = missingness.apply_to_wearable(
            wearable, travelling=travelling
        )

        # Body mass drifts slowly through phases; the daily reading's noise is
        # added at observation, so this is the underlying tissue mass.
        drift, phase = _body_mass_drift(day_index)
        body_mass += drift + float(mass_rng.normal(0.0, 0.025))

        plan = plans.get(day_index)
        sets: list[RealisedSet] = []
        anchors: list[RealisedSet] = []
        if plan is not None and not modifiers.force_rest:
            if modifiers.volume_multiplier != 1.0 or modifiers.rir_offset != 0.0:
                plan = _apply_modifiers(plan, modifiers)
            if plan.prescriptions:
                physiology.advance_to(
                    day_index * 24.0 + _WAKE_OFFSET_H + _TRAINING_OFFSET_H,
                    recovery_propensity=propensity,
                )
                sets = performance.realise_session(
                    plan,
                    physiology,
                    body_mass,
                    adaptation_multiplier=modifiers.adaptation_multiplier,
                    force_bad_session=modifiers.force_bad_session,
                )
                # Some sets are logged without an effort rating at all.
                sets = [
                    replace(s, logged_rir=None, logged_rpe=None)
                    if missingness.effort_is_missing() else s
                    for s in sets
                ]
                sets = _add_warmups_and_variants(
                    sets, library, performance, physiology, body_mass,
                    root.stream(f"sim.setvariants.{day_index}"),
                )
                anchors = _anchor_sets(
                    day_index, plan, library, performance, physiology, body_mass,
                    root.stream(f"sim.anchor.{day_index}"), last_anchor,
                )
                sets = _mark_personal_records(sets, performance)

        result.days.append(
            DayRecord(
                day_index=day_index,
                latent=latent,
                wearable=wearable,
                plan=plan if sets else None,
                sets=sets,
                scenario_labels=scenarios.labels_for(day_index),
                wearable_missingness=missing_label,
                body_mass_phase=phase,
                anchor_sets=anchors,
                body_mass_kg=round(body_mass, 3),
                state_on_waking=state_on_waking,
            )
        )

    return result


def _apply_modifiers(plan: SessionPlan, modifiers) -> SessionPlan:
    """Scale a planned session's volume and effort.

    Scenario blocks act on the ordinary plan rather than replacing it, so a
    deload session and an accumulation session differ only by these dials.
    """
    scaled = []
    for prescription in plan.prescriptions:
        sets = max(1, int(round(prescription.sets * modifiers.volume_multiplier)))
        scaled.append(
            Prescription(
                exercise_id=prescription.exercise_id,
                sets=sets,
                rep_low=prescription.rep_low,
                rep_high=prescription.rep_high,
                target_rir=max(0.0, prescription.target_rir + modifiers.rir_offset),
            )
        )
    return SessionPlan(
        day_index=plan.day_index,
        session_type=plan.session_type,
        prescriptions=tuple(scaled),
        is_deload=plan.is_deload or modifiers.volume_multiplier < 0.75,
        notes_code=plan.notes_code,
    )


# --- set types and anchors -------------------------------------------------

def _add_warmups_and_variants(
    sets: list[RealisedSet],
    library: ExerciseLibrary,
    performance: PerformanceModel,
    physiology: Physiology,
    body_mass_kg: float,
    rng,
) -> list[RealisedSet]:
    """Add warm-up, back-off and drop sets to a session's working sets.

    Warm-ups precede compound work and carry no dose (``MODEL.tex`` §Set types).
    A second, lighter prescription of the same exercise is a back-off rather
    than a fresh working set. Drop segments occasionally extend an isolation
    exercise past its last working set.
    """
    if not sets:
        return sets

    # Group by prescription, not by exercise. Sets restart their numbering with
    # each prescription, so a reset marks a new one. Grouping by exercise would
    # class a within-prescription load reduction as a back-off, when a back-off
    # is a separate, deliberately lighter prescription.
    groups: list[list[RealisedSet]] = []
    for performed in sets:
        if performed.set_number == 1 or not groups:
            groups.append([])
        groups[-1].append(performed)

    top_load: dict[str, float] = {}
    for group in groups:
        eid = group[0].exercise_id
        top_load[eid] = max(top_load.get(eid, 0.0), max(s.load_kg for s in group))

    by_exercise: dict[str, list[list[RealisedSet]]] = {}
    for group in groups:
        by_exercise.setdefault(group[0].exercise_id, []).append(group)

    out: list[RealisedSet] = []
    for exercise_id, exercise_groups in by_exercise.items():
        exercise = library[exercise_id]
        performed_sets = [s for g in exercise_groups for s in g]
        number = 0

        if exercise.compoundness >= 0.50:
            heaviest = top_load[exercise_id]
            for fraction, reps in ((0.45, 8), (0.70, 5)):
                number += 1
                out.append(
                    replace(
                        performed_sets[0],
                        set_number=number,
                        set_type="warmup",
                        load_kg=round(max(0.0, heaviest * fraction), 1),
                        reps=reps,
                        logged_rpe=None,
                        logged_rir=None,
                        true_rir=float(max(4, 12 - reps)),
                    )
                )

        # A prescription whose top load is below the exercise's heaviest of the
        # day is a back-off block.
        heaviest = top_load[exercise_id]
        for group in exercise_groups:
            group_top = max(s.load_kg for s in group)
            set_type = "backoff" if group_top < heaviest - 1e-9 else "working"
            for performed in group:
                number += 1
                out.append(replace(performed, set_number=number, set_type=set_type))

        # Drop segments: occasional, principally on isolation work.
        if exercise.compoundness < 0.35 and rng.random() < 0.06:
            last = performed_sets[-1]
            load = last.load_kg
            step = _EQUIPMENT_INCREMENT[exercise.equipment.value]
            for _ in range(int(rng.integers(1, 3))):
                number += 1
                # Stripping plates lands on real increments, like any other load.
                load = max(0.0, round(load * 0.75 / step) * step)
                out.append(
                    replace(
                        last,
                        set_number=number,
                        set_type="drop",
                        load_kg=load,
                        reps=max(3, int(last.reps * 0.6)),
                        logged_rir=0.0,
                        logged_rpe=10.0,
                        true_rir=0.0,
                    )
                )
    return out


def _anchor_sets(
    day_index: int,
    plan: SessionPlan,
    library: ExerciseLibrary,
    performance: PerformanceModel,
    physiology: Physiology,
    body_mass_kg: float,
    rng,
    last_anchor: dict[str, int],
) -> list[RealisedSet]:
    """Standardised low-fatigue anchor efforts (``DATA.md`` §5.5).

    Performed early in a session, on a rotating schedule, and only when the
    athlete is reasonably fresh -- an anchor taken in a fatigued state would
    carry no more information than an ordinary set while claiming to carry more.
    """
    if physiology.state.systemic > 0.60:
        return []

    trained_today = {p.exercise_id for p in plan.prescriptions}
    out: list[RealisedSet] = []
    for exercise_id in _ANCHOR_EXERCISES:
        if exercise_id not in trained_today:
            continue
        if day_index - last_anchor.get(exercise_id, -_ANCHOR_INTERVAL_DAYS) < _ANCHOR_INTERVAL_DAYS:
            continue
        last_anchor[exercise_id] = day_index
        anchor = Prescription(exercise_id, sets=1, rep_low=1, rep_high=3, target_rir=0.0)
        out.extend(
            performance.realise_prescription(
                anchor, physiology, body_mass_kg, session_shock=1.0
            )
        )
    return out


def _mark_personal_records(
    sets: list[RealisedSet], performance: PerformanceModel
) -> list[RealisedSet]:
    """Flag observable personal records from prior logs only.

    Warm-ups and drop segments are excluded: neither is an attempt at a record.
    """
    eligible = [s for s in sets if s.set_type in ("working", "backoff")]
    flags = performance.mark_personal_records(eligible)
    lookup = {id(s): f for s, f in zip(eligible, flags)}
    return [replace(s, is_pr=lookup.get(id(s), False)) for s in sets]
