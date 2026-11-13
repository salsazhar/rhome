"""Versioned parameter registry (Guardrail 3).

Every number taken from the specification lives here rather than being typed
inline where it is used. Each entry carries its value, its evidence grade and
the document section it came from.

The failure this prevents is specific and quiet: a coefficient gets adjusted in
code during debugging, the documents continue to claim the old value, and six
months later nobody can tell which is authoritative. ``RESEARCH.md`` exists to
stop numbers acquiring "a false aura of scientific certainty merely because
they have been encoded in software"; a registry that silently disagreed with it
would defeat that.

So the registry is checked against the documents. A test reads each referenced
document and requires the registered value to appear in it. Values that drift
in code are caught at the next test run.

Evidence grades follow ``RESEARCH.md`` §2:

* **A** — strong constraint from meta-analysis or convergent evidence
* **B** — moderate constraint from controlled or validation studies
* **C** — engineering prior: needed to make the model explicit, not directly
  identifiable from evidence, and required to remain calibratable

Grade C is the common case and is not a defect. It is a disclosure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "Grade",
    "Parameter",
    "ParameterRegistry",
    "CORE_PARAMETERS",
    "docs_root",
]

Grade = Literal["A", "B", "C"]


def docs_root() -> Path:
    """Locate ``rhome_docs/`` regardless of where tests are invoked."""
    return Path(__file__).resolve().parents[2] / "rhome_docs"


@dataclass(frozen=True)
class Parameter:
    """One specification-derived value."""

    name: str
    value: Any
    grade: Grade
    document: str
    section: str
    description: str
    #: Set when the value cannot be verified verbatim against the document —
    #: for instance a table rendered across several lines. The reason is
    #: recorded so the exemption is a visible decision, not an oversight.
    unverifiable_reason: str | None = None

    @property
    def version_id(self) -> str:
        """Stable identifier for the explanation trace (``MODEL.tex`` §Trace)."""
        return f"{self.name}@{self.document}:{self.section}"


class ParameterRegistry:
    """An immutable-after-registration collection of parameters."""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._parameters: dict[str, Parameter] = {}

    def register(
        self,
        name: str,
        value: Any,
        grade: Grade,
        document: str,
        section: str,
        description: str,
        unverifiable_reason: str | None = None,
    ) -> Parameter:
        if name in self._parameters:
            raise ValueError(f"parameter already registered: {self.namespace}.{name}")
        if grade not in ("A", "B", "C"):
            raise ValueError(f"evidence grade must be A, B or C, got {grade!r}")
        parameter = Parameter(
            name=name,
            value=value,
            grade=grade,
            document=document,
            section=section,
            description=description,
            unverifiable_reason=unverifiable_reason,
        )
        self._parameters[name] = parameter
        return parameter

    def __getitem__(self, name: str) -> Parameter:
        try:
            return self._parameters[name]
        except KeyError:
            raise KeyError(f"no such parameter: {self.namespace}.{name}") from None

    def value(self, name: str) -> Any:
        return self[name].value

    def __contains__(self, name: object) -> bool:
        return name in self._parameters

    def __len__(self) -> int:
        return len(self._parameters)

    def __iter__(self):
        return iter(self._parameters.values())

    def by_grade(self, grade: Grade) -> tuple[Parameter, ...]:
        return tuple(p for p in self if p.grade == grade)


CORE_PARAMETERS = ParameterRegistry("core")

CORE_PARAMETERS.register(
    "stimulus_primary_coeff", 1.00, "C", "MODEL.tex", "Exercise-to-muscle contribution matrix",
    "Direct-muscle stimulus contribution; the unit reference.",
)
CORE_PARAMETERS.register(
    "stimulus_secondary_coeff", 0.50, "A", "MODEL.tex", "Exercise-to-muscle contribution matrix",
    "Indirect set counted as half a direct set (Pelland et al., 2026).",
)
CORE_PARAMETERS.register(
    "stimulus_stabiliser_coeff", 0.00, "C", "MODEL.tex", "Exercise-to-muscle contribution matrix",
    "Stabilising work earns no hypertrophic credit.",
)
CORE_PARAMETERS.register(
    "fatigue_stabiliser_coeff", 0.20, "C", "MODEL.tex", "Exercise-to-muscle contribution matrix",
    "Small fatigue spillover to stabilisers; a pure engineering prior.",
)
CORE_PARAMETERS.register(
    "waking_window_h", 16.0, "C", "MODEL.tex", "Temporal conventions and continuity",
    "Hours over which daily activity load is distributed from waking.",
)
CORE_PARAMETERS.register(
    "model_muscle_group_count", 16, "A", "DATA.md", "§7.1",
    "Model groups. Coarser than display because evidence is reported per group.",
)
CORE_PARAMETERS.register(
    "derived_coefficient_confidence", 0.75, "C", "MODEL.tex", "Confidence",
    "Dose-quality weight for a derived rather than curated exercise coefficient.",
)
CORE_PARAMETERS.register(
    "nuzzo_domain_min_reps", 3.28, "A", "MODEL.tex", "Estimating relative intensity",
    "Fewest repetitions to failure in the tabulated Nuzzo relationship (95% 1RM).",
)
CORE_PARAMETERS.register(
    "nuzzo_domain_max_reps", 25.99, "A", "MODEL.tex", "Estimating relative intensity",
    "Most repetitions to failure in the tabulated Nuzzo relationship (50% 1RM).",
)
CORE_PARAMETERS.register(
    "nuzzo_near_maximal_anchor", 1.00, "A", "MODEL.tex", "Domain of validity and edge-case policy",
    "One repetition at maximum is 100% of 1RM by the definition of 1RM.",
)
CORE_PARAMETERS.register(
    "nuzzo_high_rep_clip", 0.50, "A", "MODEL.tex", "Domain of validity and edge-case policy",
    "Relative intensity is clipped, never extrapolated, below the tabulated domain.",
)
CORE_PARAMETERS.register(
    "muscle_mass_weights", None, "C", "MODEL.tex", "Systemic cost from recruited mass",
    "Relative segmental mass weights; see rhome_core.muscles.MASS_WEIGHT.",
    unverifiable_reason="Sixteen values in a two-column LaTeX table; checked "
                        "individually by test_mass_weights_match_the_document.",
)


# --- document section extraction -------------------------------------------
# A registered value must appear in the *section* it cites, not merely
# somewhere in the document. Searching a whole document for a common value
# such as 0.50 or 1.00 will almost always find a coincidental match, which
# makes the check pass while the code and the specification disagree.

import re as _re

_TEX_LEVELS = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}
_TEX_HEADING = _re.compile(r"\\(section|subsection|subsubsection|paragraph)\{([^}]*)\}")
_MD_HEADING = _re.compile(r"^(#{1,6})\s+(.*)$", _re.MULTILINE)


def _normalise(text: str) -> str:
    """Compare headings loosely: ignore case, accents of formatting and spacing."""
    text = text.replace("\\", " ").replace("$", " ").replace("§", " ")
    text = _re.sub(r"[^a-z0-9. ]+", " ", text.lower())
    return _re.sub(r"\s+", " ", text).strip()


def extract_section(document_text: str, section: str, *, is_tex: bool) -> str | None:
    """Return the text of one section, including any subsections beneath it.

    Returns ``None`` when the section cannot be located, which the caller must
    treat as a failure rather than as an empty scope.
    """
    wanted = _normalise(section)
    if not wanted:
        return None

    pattern = _TEX_HEADING if is_tex else _MD_HEADING
    headings = []
    for match in pattern.finditer(document_text):
        if is_tex:
            level = _TEX_LEVELS[match.group(1)]
            title = match.group(2)
        else:
            level = len(match.group(1))
            title = match.group(2)
        headings.append((match.start(), match.end(), level, _normalise(title)))

    for index, (start, _end, level, title) in enumerate(headings):
        if title != wanted and not title.startswith(wanted + " ") and wanted not in title:
            continue
        stop = len(document_text)
        for later_start, _, later_level, _ in headings[index + 1:]:
            if later_level <= level:
                stop = later_start
                break
        # The heading is part of its own section: "7.1 Model groups (16)"
        # carries information the body does not repeat.
        return document_text[start:stop]
    return None


# --- what the code actually reads (Guardrail 3, extended at L2.7) -----------
# Verifying a registered value against the documents proves nothing if the
# computation reads a literal instead. At L2.7 five parameters were found in
# exactly that state: the registry said 16.0, MODEL.tex said 16.0, the test
# passed, and the code used its own 16.0 that nothing checked.
#
# So the registry is now also checked from the other side: every registered
# parameter must be read somewhere in the source.


def parameter_reads(root: Path, known: set[str]) -> set[str]:
    """Every registered parameter name the source reads, found by AST.

    Reads take several shapes — ``ENGINE_PARAMETERS.value("x")``, a local
    alias ``p("x")``, and f-strings that build a family of names — so the
    match is on the argument rather than on the callable. A string literal
    passed as a call's first argument that exactly equals a registered
    parameter name is a read; nothing else in this codebase produces one by
    accident.
    """
    import ast

    found: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        registering = path.name == "parameters.py"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args:
                if registering and (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "register"
                ):
                    continue
                first = node.args[0]
                if (
                    isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                    and first.value in known
                ):
                    found.add(first.value)
            elif isinstance(node, ast.JoinedStr):
                prefix = "".join(
                    v.value for v in node.values if isinstance(v, ast.Constant)
                )
                if prefix:
                    found.update(name for name in known if name.startswith(prefix))
    return found
