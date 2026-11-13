"""Guardrail 3 — registered parameters must agree with the documents.

The failure mode is quiet: a coefficient is adjusted in code, the documents
keep claiming the old value, and later nobody can tell which is authoritative.
These tests read the referenced documents and require the registered value to
appear in them.
"""

from __future__ import annotations

import re

import pytest

from rhome_core.muscles import MASS_WEIGHT, Muscle
from rhome_engine.parameters import ENGINE_PARAMETERS
from rhome_core.parameters import (
    CORE_PARAMETERS,
    ParameterRegistry,
    docs_root,
    extract_section,
)


def _document_text(name: str) -> str:
    path = docs_root() / name
    assert path.exists(), f"referenced document missing: {path}"
    return path.read_text(encoding="utf-8")


def _appears_in(text: str, value: float | int) -> bool:
    """Whether a number appears in a document in any plausible rendering."""
    candidates = {str(value)}
    if isinstance(value, float):
        candidates.add(f"{value:g}")
        # A document may write a coefficient to a fixed number of places to
        # line it up with its neighbours: 0.03 appears as 0.030 beside 0.065
        # and 0.045. Trailing zeros are typography, not a different value.
        candidates.update(f"{value:.{places}f}" for places in (1, 2, 3, 4))
        if value == int(value):
            candidates.add(str(int(value)))
    for candidate in candidates:
        if re.search(rf"(?<![\d.]){re.escape(candidate)}(?![\d])", text):
            return True
    return False


def _section_text(parameter) -> str:
    """The text of the exact section a parameter cites."""
    document = _document_text(parameter.document)
    scope = extract_section(
        document, parameter.section, is_tex=parameter.document.endswith(".tex")
    )
    assert scope is not None, (
        f"{parameter.name} cites {parameter.document} section "
        f"{parameter.section!r}, which could not be located in that document"
    )
    return scope


@pytest.mark.guardrail(3)
@pytest.mark.spec("ARCH:parameters-match-docs")
@pytest.mark.parametrize(
    "parameter",
    [p for p in (*CORE_PARAMETERS, *ENGINE_PARAMETERS) if p.unverifiable_reason is None],
    ids=lambda p: f"{p.name}",
)
def test_registered_value_appears_in_the_section_it_cites(parameter):
    """Scoped to the cited section, not the whole document.

    A document-wide search finds a coincidental match for any common value, so
    it would pass while code and specification disagreed.
    """
    assert _appears_in(_section_text(parameter), parameter.value), (
        f"{parameter.name} = {parameter.value} is not present in "
        f"{parameter.document} §{parameter.section}. Either the code drifted "
        f"from the specification, or the specification changed without the "
        f"registry being updated."
    )


@pytest.mark.guardrail(3)
def test_section_scoping_rejects_a_coincidental_match_elsewhere():
    """The failure this guardrail was rewritten to catch.

    A value planted in one section must not be validated by an unrelated
    occurrence in another.
    """
    document = (
        "\\section{Alpha}\nThe coefficient is 0.50.\n"
        "\\section{Beta}\nAn unrelated value 0.55 appears here.\n"
    )
    alpha = extract_section(document, "Alpha", is_tex=True)
    assert _appears_in(alpha, 0.50)
    assert not _appears_in(alpha, 0.55), (
        "a value from another section must not satisfy the check"
    )


@pytest.mark.guardrail(3)
def test_unlocatable_section_is_an_error_not_an_empty_scope():
    assert extract_section("\\section{Alpha}\nbody\n", "Gamma", is_tex=True) is None


@pytest.mark.guardrail(3)
def test_section_scope_includes_nested_subsections():
    document = (
        "\\section{Outer}\nintro\n\\subsection{Inner}\nvalue 0.42 lives here\n"
        "\\section{Next}\nvalue 0.99\n"
    )
    outer = extract_section(document, "Outer", is_tex=True)
    assert _appears_in(outer, 0.42), "a subsection belongs to its parent section"
    assert not _appears_in(outer, 0.99)


@pytest.mark.guardrail(3)
def test_every_parameter_cites_a_real_document_section():
    for p in (*CORE_PARAMETERS, *ENGINE_PARAMETERS):
        text = _document_text(p.document)
        assert p.section, f"{p.name} has no section reference"
        assert p.description, f"{p.name} has no description"
        if p.document.endswith(".md") or p.document.endswith(".tex"):
            # A section reference must be findable, so the trace can point at it.
            needle = p.section.lstrip("§")
            assert needle in text, (
                f"{p.name} cites {p.document} {p.section}, which is not in that document"
            )


@pytest.mark.guardrail(3)
def test_mass_weights_match_the_document():
    """The one registry entry exempt from the generic check, checked properly."""
    text = _document_text("MODEL.tex")
    assert len(MASS_WEIGHT) == len(list(Muscle)), "every model group needs a mass weight"
    for muscle, weight in MASS_WEIGHT.items():
        rendered = f"{weight:.2f}"
        assert rendered in text, (
            f"mass weight for {muscle.value} ({rendered}) is not in MODEL.tex"
        )
    assert all(0.0 < w <= 1.0 for w in MASS_WEIGHT.values())


@pytest.mark.guardrail(3)
def test_exempt_parameters_state_a_reason():
    for p in (*CORE_PARAMETERS, *ENGINE_PARAMETERS):
        if p.value is None:
            assert p.unverifiable_reason, (
                f"{p.name} cannot be verified but gives no reason; an exemption "
                f"must be a visible decision, not an oversight"
            )


@pytest.mark.guardrail(3)
def test_doc_verifier_rejects_a_value_that_is_not_present():
    """The checker must be known to catch drift, not merely to pass."""
    text = "the coefficient is 0.065 and the half-life is 30 h"
    assert _appears_in(text, 0.065)
    assert _appears_in(text, 30)
    assert not _appears_in(text, 0.075), "a drifted value must not be accepted"
    assert not _appears_in(text, 0.06), "a prefix must not count as a match"


@pytest.mark.guardrail(3)
def test_registry_rejects_duplicate_and_malformed_entries():
    registry = ParameterRegistry("test")
    registry.register("x", 1.0, "C", "MODEL.tex", "§1", "a value")
    with pytest.raises(ValueError, match="already registered"):
        registry.register("x", 2.0, "C", "MODEL.tex", "§1", "a duplicate")
    with pytest.raises(ValueError, match="evidence grade"):
        registry.register("y", 1.0, "D", "MODEL.tex", "§1", "a bad grade")
    with pytest.raises(KeyError):
        registry["nope"]


@pytest.mark.guardrail(3)
def test_every_parameter_has_a_stable_version_id():
    ids = [p.version_id for p in (*CORE_PARAMETERS, *ENGINE_PARAMETERS)]
    assert len(set(ids)) == len(ids), "version ids must be unique for the trace"


# --- the other direction (L2.7) ---------------------------------------------

@pytest.mark.guardrail(3)
@pytest.mark.spec("ARCH:parameters-match-docs")
def test_every_registered_parameter_is_actually_read_by_the_code():
    """The failure a document check cannot see.

    Verifying a value against MODEL.tex proves nothing if the computation uses
    a literal instead. Five parameters were in exactly that state at L2.7 —
    the contribution coefficients, the waking window, the Nuzzo domain bounds
    — each with the registry, the document and this test all agreeing with one
    another and none of them connected to the arithmetic.

    An unread parameter is either dead or shadowed. Both are defects.
    """
    from rhome_core.parameters import parameter_reads

    known = {p.name for p in CORE_PARAMETERS} | {p.name for p in ENGINE_PARAMETERS}
    from rhome_core.architecture import source_root as src_root

    read = parameter_reads(src_root(), known)

    exempt = {"muscle_mass_weights"}  # checked by its own test; has no scalar value
    unread = sorted(known - read - exempt)
    assert not unread, (
        f"{len(unread)} registered parameters are never read: {unread}. "
        f"Each is either dead or shadowed by a literal."
    )


@pytest.mark.guardrail(3)
def test_the_read_scanner_finds_a_planted_parameter_and_misses_a_removed_one(tmp_path):
    """The checker must be known to catch drift, not merely to pass."""
    from rhome_core.parameters import parameter_reads

    (tmp_path / "uses.py").write_text(
        'p = None\nX = p("local_half_life_h")\n', encoding="utf-8"
    )
    (tmp_path / "ignores.py").write_text("Y = 30.0\n", encoding="utf-8")

    found = parameter_reads(tmp_path, {"local_half_life_h", "novelty_cap"})
    assert found == {"local_half_life_h"}
