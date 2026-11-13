"""The explanation trace (``MODEL.tex`` §Explanation trace).

Product success criterion 10 requires every displayed state to be auditable.
Because each state is a sum of exponentially decaying impulses, the trace is an
*exact* decomposition rather than a plausible account written afterwards, and
that exactness is what makes it testable: shares sum to one, and the state
rebuilds from the contributors listed.

The parameter block is the part that separates an audit trail from a
convincing story. It lets a reviewer see that a displayed number rests on a
particular set of Grade C priors. It is collected by reading the source of the
modules that compute each channel rather than by hand, so a parameter added to
a computation appears in the trace without anyone remembering to list it.

Driver strings are generated from fixed templates, never freely. Every string
is checked against the claim boundaries of ``RESEARCH.md`` §17 before it is
returned, and the check is a test rather than a review.
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rhome_core.muscles import Muscle
from rhome_core.parameters import CORE_PARAMETERS, Parameter
from rhome_engine.confidence import Confidence
from rhome_engine.ledger import Channel, Contribution, ContributionLedger
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_engine.recovery import RecoveryContext
from rhome_engine.state import EngineState

__all__ = [
    "ClaimBoundaryError",
    "Modifier",
    "TraceRecord",
    "TraceBuilder",
    "check_claim_boundaries",
    "display_value",
]


def display_value(latent: float) -> float:
    """Map a non-negative latent state to the 0–100 display index.

    ``MODEL.tex`` §Display: this is an *index*, not a claim that a muscle is
    biologically some percentage fatigued. The distinction is the reason
    driver strings carry no percentage at all.
    """
    return 100.0 * (1.0 - math.exp(-latent))


# --- claim boundaries (RESEARCH.md §17) -------------------------------------

#: Phrasings the research specification forbids. Each entry pairs a pattern
#: with the boundary it crosses, so a failure says which rule was broken
#: rather than merely that one was.
_FORBIDDEN: tuple[tuple[str, str], ...] = (
    (r"\bCNS\b", "'CNS fatigue' is the framing MODEL.tex replaces with neuromuscular strain"),
    (r"\d\s*%", "a percentage in prose reads as a measured biological quantity"),
    (r"\bper cent\b", "a percentage in prose reads as a measured biological quantity"),
    (r"\bovertrain", "overtraining is a diagnosis"),
    (r"\binjury risk\b", "no injury-risk claim is supported"),
    (r"\bACWR\b", "no threshold attaches to the load-trace ratio"),
    (r"\b(ill|illness|sick|infection)\b", "illness is a diagnosis"),
    (r"\bprove[sd]?\b", "the model estimates; it does not prove"),
    (r"\b(should|shouldn't|must|need to|ought to)\b", "a recommendation, not an estimate"),
    (r"\b(don't|do not|avoid|skip|rest today|take.*off)\b", "a recommendation, not an estimate"),
    (r"\brecovered\b", "'recovered' asserts a biological state rather than a model estimate"),
    (r"\b(diagnos|overreach|burnout)", "a diagnosis"),
)


class ClaimBoundaryError(ValueError):
    """A generated string crossed a boundary in ``RESEARCH.md`` §17."""


def check_claim_boundaries(text: str) -> str:
    """Return ``text`` unchanged, or raise saying which boundary it crossed."""
    for pattern, reason in _FORBIDDEN:
        if re.search(pattern, text, flags=re.IGNORECASE):
            raise ClaimBoundaryError(
                f"driver string crosses a claim boundary ({reason}): {text!r}"
            )
    return text


# --- parameters actually read by a computation ------------------------------

_VALUE_CALL = re.compile(r"^(ENGINE_PARAMETERS|CORE_PARAMETERS)$")

#: Which modules compute which channel. Read rather than declared: the point is
#: that the trace reports what the code uses, not what someone believed it did.
_CHANNEL_MODULES: dict[str, tuple[str, ...]] = {
    Channel.LOCAL_FATIGUE: ("dose", "state", "core:exercises", "core:intensity"),
    Channel.NEUROMUSCULAR: ("dose", "state", "core:exercises", "core:intensity"),
    Channel.SYSTEMIC: ("dose", "state", "core:exercises", "core:intensity"),
    Channel.ADAPTATION: ("dose", "state", "core:exercises", "core:intensity"),
}


@lru_cache(maxsize=None)
def _parameters_read_by(module_name: str) -> tuple[str, ...]:
    """Every registry lookup appearing in a module's source, by AST.

    Scanning the source is deliberate. A hand-maintained list of "parameters
    this channel uses" is exactly the kind of thing that stays at its first
    value while the code moves on, and the parameter block exists to be
    trustworthy.
    """
    if module_name.startswith("core:"):
        path = Path(__file__).parents[1] / "rhome_core" / f"{module_name[5:]}.py"
    else:
        path = Path(__file__).with_name(f"{module_name}.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "value" or not isinstance(node.func.value, ast.Name):
            continue
        if not _VALUE_CALL.match(node.func.value.id) or not node.args:
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            names.append(argument.value)
    return tuple(sorted(set(names)))


def _parameters_for(channel: str) -> tuple[Parameter, ...]:
    found: dict[str, Parameter] = {}
    for module in _CHANNEL_MODULES.get(channel, ()):
        for name in _parameters_read_by(module):
            if name in ENGINE_PARAMETERS:
                found[name] = ENGINE_PARAMETERS[name]
            elif name in CORE_PARAMETERS:
                found[name] = CORE_PARAMETERS[name]
    return tuple(found[k] for k in sorted(found))


# --- the record --------------------------------------------------------------

@dataclass(frozen=True)
class Modifier:
    """One thing that changed a state without depositing into it."""

    name: str
    value: float
    deviation: float
    detail: str


@dataclass(frozen=True)
class TraceRecord:
    """Everything behind one displayed number."""

    state_id: str
    value: float
    display_value: float
    confidence: Confidence | None
    contributors: tuple[Contribution, ...] = ()
    modifiers: tuple[Modifier, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    driver: str = ""

    def share_total(self) -> float:
        return sum(c.share for c in self.contributors)

    def reconstruct(self) -> float:
        """Rebuild the state from the contributors listed.

        If this disagrees with ``value``, the decomposition has lost something
        and the explanation is describing a number the engine did not produce.
        """
        return sum(c.surviving for c in self.contributors)

    def grades(self) -> dict[str, int]:
        counts = {"A": 0, "B": 0, "C": 0}
        for parameter in self.parameters:
            counts[parameter.grade] += 1
        return counts


# --- building ---------------------------------------------------------------

#: Human names for the model groups, for driver strings.
_MUSCLE_NAMES = {
    "abs": "abs", "adductors": "adductors", "anterior_delts": "front delts",
    "biceps": "biceps", "calves": "calves", "chest": "chest",
    "forearms": "forearms", "glutes": "glutes", "hamstrings": "hamstrings",
    "lateral_delts": "side delts", "lats": "lats",
    "posterior_delts": "rear delts", "quads": "quads",
    "spinal_erectors": "lower back", "triceps": "triceps",
    "upper_back": "upper back",
}

_CHANNEL_NAMES = {
    Channel.LOCAL_FATIGUE: "Estimated local fatigue",
    Channel.NEUROMUSCULAR: "Estimated neuromuscular strain",
    Channel.SYSTEMIC: "Estimated systemic load",
    Channel.ADAPTATION: "Estimated accumulated stimulus",
}


class TraceBuilder:
    """Assembles trace records from the ledger and the day's context."""

    def __init__(self, ledger: ContributionLedger) -> None:
        self.ledger = ledger

    def record(
        self,
        channel: str,
        subject: str,
        state: EngineState,
        context: RecoveryContext | None = None,
        confidence: Confidence | None = None,
    ) -> TraceRecord:
        value = self._state_value(channel, subject, state)
        contributors = self.ledger.contributions(
            channel, subject, value, state.t_h, state.rho_clock
        )
        modifiers = self._modifiers(channel, context)
        return TraceRecord(
            state_id=self._state_id(channel, subject),
            value=value,
            display_value=display_value(value),
            confidence=confidence,
            contributors=contributors,
            modifiers=modifiers,
            parameters=_parameters_for(channel),
            driver=self.driver(channel, subject, contributors, modifiers),
        )

    # --- pieces ------------------------------------------------------------

    @staticmethod
    def _state_id(channel: str, subject: str) -> str:
        prefix = {
            Channel.LOCAL_FATIGUE: "F", Channel.NEUROMUSCULAR: "N",
            Channel.SYSTEMIC: "G", Channel.ADAPTATION: "A",
        }[channel]
        return f"{prefix}.{subject}" if subject else prefix

    @staticmethod
    def _state_value(channel: str, subject: str, state: EngineState) -> float:
        if channel == Channel.LOCAL_FATIGUE:
            return state.local_fatigue[Muscle(subject)]
        if channel == Channel.ADAPTATION:
            return state.adaptation[Muscle(subject)]
        if channel == Channel.NEUROMUSCULAR:
            return state.neuromuscular
        return state.systemic

    @staticmethod
    def _modifiers(channel: str, context: RecoveryContext | None) -> tuple[Modifier, ...]:
        # Adaptation is not modulated by recovery context, so reporting rho
        # against it would be reporting something that had no effect.
        if context is None or channel not in Channel.RHO_MODULATED:
            return ()
        modifiers = [
            Modifier(
                "recovery context", context.rho, context.rho - 1.0,
                f"recovery context {'above' if context.rho > 1 else 'below'} baseline"
                if abs(context.rho - 1.0) > 1e-9 else "recovery context at baseline",
            )
        ]
        for name, z in sorted(context.raw_z.items(), key=lambda kv: -abs(kv[1])):
            modifiers.append(
                Modifier(
                    name, z, z,
                    f"{_READABLE.get(name, name)} "
                    f"{'above' if z > 0 else 'below'} your baseline",
                )
            )
        return tuple(modifiers)

    def driver(
        self,
        channel: str,
        subject: str,
        contributors: tuple[Contribution, ...],
        modifiers: tuple[Modifier, ...],
    ) -> str:
        """The short Today-screen string, from fixed templates only.

        ``MODEL.tex`` fixes the rule: the two highest-share contributors and the
        single modifier with the largest absolute deviation. Nothing here is
        free generation, and the result is checked before it is returned.
        """
        named = [c for c in contributors if not c.is_residual][:2]
        if not named:
            return ""

        subject_name = _MUSCLE_NAMES.get(subject, subject) if subject else ""
        head = _CHANNEL_NAMES[channel]
        if subject_name:
            head = f"{head} in the {subject_name}"

        # When no single set dominates, naming two of them would imply an
        # attribution the decomposition does not support. Two sets at eight per
        # cent each are not what a state "follows".
        if sum(c.share for c in named) < _DIFFUSE_SHARE:
            sentence = (
                f"{head} follows the whole of {named[0].label.split(',')[0]} "
                f"{_age_phrase(named[0].age_h)} rather than any single set"
            )
        else:
            sources = " and ".join(f"{c.label} {_age_phrase(c.age_h)}" for c in named)
            sentence = f"{head} follows {sources}"

        modifier = max(modifiers, key=lambda m: abs(m.deviation), default=None)
        if modifier is not None and abs(modifier.deviation) > 0.5:
            sentence += f"; {modifier.detail}"
        elif modifier is not None:
            sentence += "; recovery context near baseline"
        return check_claim_boundaries(sentence + ".")


#: Keys as ``RecoveryContext`` reports them, rendered for a person to read.
_READABLE = {
    "hrv": "heart-rate variability",
    "resting_hr": "resting heart rate",
    "sleep": "sleep duration",
    "total_sleep": "sleep duration",
    "sleep_efficiency": "sleep efficiency",
    "temperature": "body temperature",
}


#: Combined share below which the two leading contributors are not named
#: individually.
_DIFFUSE_SHARE = 0.25


def _age_phrase(age_h: float) -> str:
    if age_h < 20.0:
        return "today"
    if age_h < 44.0:
        return "yesterday"
    days = round(age_h / 24.0)
    return f"{days} days ago"
