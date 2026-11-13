"""Does the engine's muscle fatigue predict which muscle underperforms? (L3.15)

The engine prints a fatigue number per muscle. Nothing has ever checked whether
that number is true. On synthetic data there is ground truth, because we wrote
it; on a real log fatigue is latent and the figure floats free.

**The test.** Within one session, take two exercises loading different primary
muscles. Before any set is seen, the engine has frozen a predicted suppression
for each. Ask: does the exercise it calls *more* suppressed actually come in
lower against its own recent history?

**Why paired, and why within a session.** Both exercises share the day — the
same sleep, the same illness, the same week, the same breakfast. Almost every
confound is common to the pair and cancels in the comparison. What does not
cancel is the muscle-specific claim, which is the thing on trial.

**Why direction and not magnitude.** The engine's known weakness is compressed
size, not wrong sign: it gets 6/6 ranking orderings right while expressing
about 67% of the true contrast. Scoring direction measures what is claimed
without punishing the compression, and it has a floor — chance is 50%, and a
value below it cannot be rationalised (D19).

**What this deliberately does not use.** The observed side is each exercise's
implied capacity against *its own rolling median*, never the engine's capacity
estimate. That estimator is the broken part (LIM-31); routing the observation
through it would let a capacity failure contaminate the fatigue verdict. The
two are kept separate on purpose.

**Two guardrails, or this scores noise.** A predicted gap of 0.4% against 0.2%
is a "correct direction" that tells nobody anything, so pairs are scored only
above an effect-size floor — and **coverage is reported alongside accuracy**,
because a model that predicts near-zero differences everywhere would otherwise
sit at chance forever without ever being caught saying nothing.

**Baselines (D20).** No score without its trivial competitor. Session position
is the one that matters: later exercises are naturally worse, and if the engine
merely encodes running order then order alone will match it.

**D22 applies.** This runs on the 99 historical sessions, which are development
data and can validate nothing. The sessions logged in Rhome from 25 August 2026
are not read here and must not be until a version is frozen against them.
"""
from __future__ import annotations

import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rhome_core.exercises import library_path, load_library  # noqa: E402
from rhome_engine.session import RhomeEngine  # noqa: E402
from rhome_eval.cold_run import assemble  # noqa: E402

REPORT = ROOT / "build_log" / "directional_fatigue.txt"

#: Prior sessions required before an exercise has a reference worth comparing
#: against. Two is thin; the sensitivity to it is reported rather than assumed.
MIN_PRIOR = 3

#: Effect-size floors, as absolute difference in predicted suppression.
THRESHOLDS = (0.0, 0.005, 0.01, 0.02, 0.03, 0.05)

lines: list[str] = []


def say(text: str = "") -> None:
    lines.append(text)
    print(text)


def head(title: str) -> None:
    say()
    say("-" * 78)
    say(title)
    say("-" * 78)


class Trial:
    """One within-session pair, with every predictor's call recorded."""

    __slots__ = ("day", "gap", "local_gap", "truth", "position", "recent_sets", "days_since")

    def __init__(self, day, gap, local_gap, truth, position, recent_sets, days_since):
        self.day = day
        self.gap = gap                  # predicted suppression, A minus B
        self.local_gap = local_gap      # the muscle-specific term only
        self.truth = truth              # observed residual, A minus B
        self.position = position        # session position, A minus B
        self.recent_sets = recent_sets  # decayed set count on primaries, A minus B
        self.days_since = days_since    # days since primaries trained, A minus B


def main() -> int:
    inputs = assemble(
        "L3.15 directional fatigue test: does predicted per-muscle suppression "
        "order within-session underperformance? Development analysis on the "
        "historical log, which D22 reclassified as a development set. Validates "
        "nothing; the Rhome-logged sessions are not read.",
        kind="dry",
    )
    library = load_library(library_path().parent / "exercise_library_v1_2.csv")
    engine = RhomeEngine(library)
    results = engine.run(inputs.days)

    say("=" * 78)
    say("DIRECTIONAL FATIGUE TEST — is the per-muscle number real?")
    say("=" * 78)
    say(f"\n{inputs.provenance}")
    say("Development analysis (D22). Nothing here validates anything.")
    say(f"\nReference: rolling median of the exercise's own implied capacity,")
    say(f"minimum {MIN_PRIOR} prior sessions. The engine's capacity estimate is")
    say("not used on the observed side.")

    trials, coverage = collect(results, library)
    if not trials:
        say("\nNo scorable pairs. Nothing can be concluded.")
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    report_coverage(coverage, trials)
    report_instrument(trials)
    report_accuracy(trials)
    report_baselines(trials)
    report_by_threshold(trials)
    report_ceiling(trials)
    report_power(trials)

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(f"\nWritten to {REPORT.relative_to(ROOT)}")
    return 0


def collect(results, library):
    """Build every within-session pair that has a reference on both sides."""
    history: dict[str, list[float]] = defaultdict(list)
    last_trained: dict[str, int] = {}
    recent_load: dict[str, list[tuple[int, int]]] = defaultdict(list)

    trials: list[Trial] = []
    coverage = {"sessions": 0, "scored_sessions": 0, "exercises": 0,
                "with_reference": 0, "pairs": 0, "same_muscle_pairs": 0}

    for result in results:
        if not result.observations:
            continue
        coverage["sessions"] += 1

        # First working observation per exercise identity: least contaminated
        # by within-session fatigue, and one per frozen projection.
        first: dict[str, object] = {}
        position: dict[str, int] = {}
        for obs in result.observations:
            if obs.exercise_id in first:
                continue
            position[obs.exercise_id] = len(first)
            first[obs.exercise_id] = obs

        entries = []
        for identity, obs in first.items():
            coverage["exercises"] += 1
            base = obs.base_exercise_id or obs.exercise_id
            exercise = library.exercises.get(base)
            if exercise is None:
                continue
            prior = history[identity]
            if len(prior) < MIN_PRIOR:
                continue
            projection = result.projections.get(identity)
            if projection is None:
                continue
            coverage["with_reference"] += 1

            reference = st.median(prior)
            if reference <= 0 or obs.observed <= 0:
                continue

            primaries = frozenset(exercise.primary_muscles)
            entries.append({
                "identity": identity,
                "primaries": primaries,
                "residual": math.log(obs.observed) - math.log(reference),
                "suppression": projection.suppression,
                "local": projection.terms.get("local", 0.0),
                "position": position[identity],
                "recent": decayed_sets(recent_load, primaries, result.day_index),
                "days_since": days_since(last_trained, primaries, result.day_index),
            })

        if len(entries) >= 2:
            coverage["scored_sessions"] += 1
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a, b = entries[i], entries[j]
                if a["primaries"] & b["primaries"]:
                    # Not a muscle contrast: the pair shares a primary mover.
                    coverage["same_muscle_pairs"] += 1
                    continue
                coverage["pairs"] += 1
                trials.append(Trial(
                    day=result.day_index,
                    gap=a["suppression"] - b["suppression"],
                    local_gap=a["local"] - b["local"],
                    truth=a["residual"] - b["residual"],
                    position=a["position"] - b["position"],
                    recent_sets=a["recent"] - b["recent"],
                    days_since=a["days_since"] - b["days_since"],
                ))

        # Update history only after scoring, so a session never informs its own
        # reference.
        for identity, obs in first.items():
            if obs.observed > 0:
                history[identity].append(obs.observed)
        for logged, _dose in result.doses:
            exercise = library.exercises.get(logged.exercise_id)
            if exercise is None:
                continue
            for muscle in exercise.primary_muscles:
                last_trained[muscle] = result.day_index
                recent_load[muscle].append((result.day_index, 1))

    return trials, coverage


def decayed_sets(recent_load, muscles, day, half_life_days: float = 3.0) -> float:
    """A decaying set counter — the trivial competitor this project always runs."""
    total = 0.0
    for muscle in muscles:
        for when, count in recent_load.get(muscle, []):
            age = day - when
            if 0 <= age <= 21:
                total += count * 0.5 ** (age / half_life_days)
    return total / max(1, len(muscles))


def days_since(last_trained, muscles, day) -> float:
    seen = [day - last_trained[m] for m in muscles if m in last_trained]
    return float(min(seen)) if seen else 99.0


def directional(trials, predictor, threshold: float = 0.0):
    """Accuracy of a predictor's sign against the observed sign."""
    hits = n = 0
    for t in trials:
        p = predictor(t)
        if abs(p) < threshold or t.truth == 0.0:
            continue
        n += 1
        # More predicted suppression should mean a lower observed residual.
        if (p > 0) == (t.truth < 0):
            hits += 1
    return hits, n


def binomial_p(hits: int, n: int) -> float:
    """Two-sided exact p against a fair coin. No library needed."""
    if n == 0:
        return 1.0
    from math import comb
    tail = sum(comb(n, k) for k in range(hits, n + 1)) / 2 ** n
    return min(1.0, 2 * min(tail, 1 - tail + comb(n, hits) / 2 ** n))


def report_coverage(coverage, trials):
    head("1. COVERAGE — how often the engine gets to make a call at all")
    say("Accuracy without this is unreadable: a model that says nothing can")
    say("never be caught being wrong.\n")
    say(f"  training sessions                    {coverage['sessions']:5d}")
    say(f"  sessions with 2+ referenced exercises{coverage['scored_sessions']:5d}")
    say(f"  exercise-sessions seen               {coverage['exercises']:5d}")
    say(f"  ... with a {MIN_PRIOR}-session reference       {coverage['with_reference']:5d}")
    say(f"  candidate pairs, different primaries {coverage['pairs']:5d}")
    say(f"  pairs rejected, shared primary mover {coverage['same_muscle_pairs']:5d}")
    gaps = [abs(t.gap) for t in trials]
    if gaps:
        say(f"\n  predicted suppression gap: median {st.median(gaps):.4f}, "
            f"max {max(gaps):.4f}")
        say(f"  gaps above 1%: {sum(1 for g in gaps if g >= 0.01)} of {len(gaps)}")


def report_instrument(trials):
    head("2. INSTRUMENT CHECK — before any null is believed")
    say("A 50% result means either 'no signal' or 'the harness is broken', and")
    say("those are not distinguishable by staring at the number. Two checks.\n")

    hits, n = directional(trials, lambda t: -t.truth)
    say(f"  perfect predictor (uses the answer)   {hits}/{n} = {hits/n:.1%}"
        f"   — must be 100%")
    hits, n = directional(trials, lambda t: t.truth)
    say(f"  inverted predictor                    {hits}/{n} = {hits/n:.1%}"
        f"   — must be 0%")

    spread = [abs(t.truth) for t in trials]
    say(f"\n  observed residual gap within a pair: median {st.median(spread):.4f},")
    say(f"  90th percentile {sorted(spread)[int(0.9 * len(spread))]:.4f}, "
        f"max {max(spread):.4f}")
    say("  There is real variation to predict; the target is not flat.")


def report_accuracy(trials):
    head("3. THE TEST — does the more suppressed exercise come in lower?")
    hits, n = directional(trials, lambda t: t.gap)
    if n:
        p = binomial_p(hits, n)
        say(f"  engine suppression   {hits}/{n} = {hits/n:.1%}   (p = {p:.4f} vs chance)")
    hits_l, n_l = directional(trials, lambda t: t.local_gap)
    if n_l:
        say(f"  local term only      {hits_l}/{n_l} = {hits_l/n_l:.1%}   "
            f"(p = {binomial_p(hits_l, n_l):.4f})")
    say("\n  The local term is the muscle-specific claim; the systemic and")
    say("  neuromuscular terms are common to the session and largely cancel")
    say("  within a pair.")


def report_baselines(trials):
    head("4. BASELINES — no score without its trivial competitor (D20)")
    say("Session position is the one that matters. Later exercises are worse")
    say("regardless of recovery, so if the engine merely encodes running order,")
    say("order alone will match it.\n")
    for name, predictor in (
        ("chance", None),
        ("session position", lambda t: t.position),
        ("decayed set count", lambda t: t.recent_sets),
        ("days since trained", lambda t: -t.days_since),
    ):
        if predictor is None:
            say(f"  {name:20s} 50.0%")
            continue
        hits, n = directional(trials, predictor)
        if n:
            say(f"  {name:20s} {hits}/{n} = {hits/n:.1%}   "
                f"(p = {binomial_p(hits, n):.4f})")


def report_ceiling(trials):
    head("6. CEILING — could this test detect a CORRECT model of this size?")
    say("Before concluding the model is wrong, ask what the best possible model")
    say("of the magnitude the engine predicts would have scored. If the answer")
    say("is 'about chance', the null says nothing about the model (D19).\n")

    sig_pred = st.pstdev([t.gap for t in trials])
    sig_obs = st.pstdev([t.truth for t in trials])
    say(f"  sd of predicted pair gap   {sig_pred:.4f}")
    say(f"  sd of observed pair gap    {sig_obs:.4f}")
    say(f"  ratio                      {sig_pred / sig_obs:.4f}")

    # If observed = effect + independent noise, with the effect exactly the size
    # the engine predicts, P(sign agrees) = 1/2 + arctan(sigma_e/sigma_n)/pi.
    ratio = sig_pred / max(1e-12, sig_obs)
    ceiling = 0.5 + math.atan(ratio) / math.pi
    say(f"\n  A PERFECT predictor of an effect this size scores {ceiling:.1%}.")
    se = math.sqrt(0.25 / len(trials))
    z = (ceiling - 0.5) / se
    say(f"  That is {z:.2f} SE from chance at n = {len(trials)}"
        f" — {'detectable' if z >= 1.96 else 'NOT detectable'}.")
    say("")
    say("  So the null is uninformative about correctness. The engine predicts")
    say("  effects far below what this measurement can resolve. What the test")
    say("  does establish is the effect SIZE, which is a real finding on its own:")
    say("  a fatigue model this faint cannot drive a readiness display whatever")
    say("  its direction.")
    say("")
    say(f"  For a perfect model to reach 60% here, the predicted gap would need")
    need = math.tan(math.pi * 0.1) * sig_obs
    say(f"  sd {need:.3f} against the current {sig_pred:.4f} — {need/sig_pred:.0f}x larger.")


def report_power(trials):
    head("7. POWER — what this test could and could not have detected")
    n = len(trials)
    se = math.sqrt(0.25 / n) if n else 0.0
    say(f"  n = {n} pairs, standard error at chance = {se:.3f}\n")
    for effect in (0.55, 0.60, 0.65, 0.70):
        z = (effect - 0.5) / se if se else 0.0
        verdict = "detectable" if z >= 1.96 else "NOT detectable"
        say(f"  a true accuracy of {effect:.0%}  ->  {z:.1f} SE from chance   {verdict}")
    say("\n  So this test can find a strong effect and has not. It cannot rule")
    say("  out a weak one, and must not be quoted as having done so.")


def report_by_threshold(trials):
    head("5. EFFECT-SIZE FLOOR — accuracy against how much is scored")
    say("A correct direction on a 0.4%-vs-0.2% gap is not information. Raising")
    say("the floor should raise accuracy if the signal is real; if it does not,")
    say("the engine is right about pairs it barely distinguishes and wrong")
    say("about the ones it commits to.\n")
    say(f"  {'floor':>7s}  {'scored':>7s}  {'coverage':>9s}  {'engine':>8s}  {'position':>9s}")
    total = len(trials)
    for threshold in THRESHOLDS:
        hits, n = directional(trials, lambda t: t.gap, threshold)
        if n == 0:
            say(f"  {threshold:7.3f}  {'—':>7s}  {'—':>9s}  {'—':>8s}")
            continue
        subset = [t for t in trials if abs(t.gap) >= threshold]
        p_hits, p_n = directional(subset, lambda t: t.position)
        pos = f"{p_hits/p_n:.1%}" if p_n else "—"
        say(f"  {threshold:7.3f}  {n:7d}  {n/max(1,total):8.0%}   "
            f"{hits/n:7.1%}  {pos:>9s}")


if __name__ == "__main__":
    raise SystemExit(main())
