"""Architectural boundary rules and the checker that enforces them (Guardrail 1).

The central methodological commitment of this project is that the inference
engine never sees the simulator's internals or its answers (``DATA.md`` §2).
If that boundary is crossed, every evaluation result afterwards is worthless,
and the failure is silent: the engine simply appears to perform well.

Convention is not enough to hold a rule whose violation is invisible, so the
boundary is checked mechanically. This module parses the source tree and fails
if any package imports something it is not permitted to import, or if the
engine references the hidden data directory.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "PACKAGES",
    "ALLOWED_IMPORTS",
    "Violation",
    "SEALED_DATA_ALLOWED",
    "check_import_boundaries",
    "source_root",
]

PACKAGES = ("rhome_core", "rhome_sim", "rhome_engine", "rhome_eval")

#: Which rhome packages each package may import.
ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    # Sits beneath everything; depending upward would let sim and engine reach
    # each other through it.
    "rhome_core": frozenset(),
    "rhome_sim": frozenset({"rhome_core"}),
    "rhome_engine": frozenset({"rhome_core"}),
    # The single exception: evaluation compares truth against estimates and so
    # must see both sides.
    "rhome_eval": frozenset({"rhome_core", "rhome_sim", "rhome_engine"}),
}

#: Packages forbidden from referencing the simulator's hidden ground-truth data.
HIDDEN_DATA_FORBIDDEN = ("rhome_engine",)

#: Substrings that indicate a reference to the hidden data directory.
_HIDDEN_MARKERS = ("hidden/", "latent_daily", "latent_sets", "scenario_manifest")

#: The athlete's own recorded history, sealed until L3.9. There is one such
#: dataset and one chance to run against it, so no package may reach for it
#: during development — including by accident, in a debugging script left
#: behind. ``rhome_eval`` is exempted because L3.9 lives there; the seal that
#: matters until then is the manifest, which records the export's checksums so
#: a later run can prove the files were not touched in between.
SEALED_DATA_ALLOWED = ("rhome_eval",)

#: Substrings that indicate a reference to the sealed real-data directory.
_SEALED_MARKERS = ("data/real", "real_holdout", "oura_export")


@dataclass(frozen=True)
class Violation:
    """One breach of an architectural rule."""

    file: Path
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} [{self.rule}] {self.detail}"


def source_root() -> Path:
    """Locate the ``src`` directory regardless of where tests are invoked."""
    return Path(__file__).resolve().parents[1]


def _owning_package(path: Path, root: Path) -> str | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    return relative.parts[0] if relative.parts else None


def _imported_rhome_packages(tree: ast.AST) -> list[tuple[int, str]]:
    """Every rhome package imported, with the line it was imported on."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in PACKAGES:
                    found.append((node.lineno, top))
        elif isinstance(node, ast.ImportFrom):
            # A relative import cannot leave its own package, so it is always safe.
            if node.level and not node.module:
                continue
            if node.module:
                top = node.module.split(".")[0]
                if top in PACKAGES:
                    found.append((node.lineno, top))
    return found


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Identify docstring literals, which are prose rather than code.

    A module explaining that it must not read ``hidden/`` should not be
    reported for containing the word. Only executable string literals count.
    """
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docstrings.add(id(first.value))
    return docstrings


def _string_references(tree: ast.AST, markers: tuple[str, ...]) -> list[tuple[int, str]]:
    """Executable string literals containing any of ``markers``.

    Docstrings are exempt: a module may describe a boundary it must not cross.
    """
    docstrings = _docstring_nodes(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings:
            continue
        for marker in markers:
            if marker in node.value:
                found.append((node.lineno, node.value))
                break
    return found


def check_import_boundaries(root: Path | None = None) -> list[Violation]:
    """Return every architectural violation in the source tree.

    An empty list means the boundary holds.
    """
    root = root or source_root()
    violations: list[Violation] = []

    for path in sorted(root.rglob("*.py")):
        package = _owning_package(path, root)
        if package not in ALLOWED_IMPORTS:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        allowed = ALLOWED_IMPORTS[package]
        relative = path.relative_to(root)

        for line, imported in _imported_rhome_packages(tree):
            if imported == package or imported in allowed:
                continue
            violations.append(
                Violation(
                    file=relative,
                    line=line,
                    rule="import-boundary",
                    detail=f"{package} may not import {imported}",
                )
            )

        # The checker names what it forbids, so it cannot obey its own string
        # rules. Exempted by path rather than by marker, so the exemption is
        # this one file and not any file that happens to look like it.
        is_the_checker = relative == Path("rhome_core/architecture.py")

        if package not in SEALED_DATA_ALLOWED and not is_the_checker:
            for line, literal in _string_references(tree, _SEALED_MARKERS):
                violations.append(
                    Violation(
                        file=relative,
                        line=line,
                        rule="sealed-real-data",
                        detail=(
                            f"{package} may not reference the athlete's sealed "
                            f"history before L3.9: {literal!r}"
                        ),
                    )
                )

        if package in HIDDEN_DATA_FORBIDDEN:
            for line, literal in _string_references(tree, _HIDDEN_MARKERS):
                violations.append(
                    Violation(
                        file=relative,
                        line=line,
                        rule="hidden-data",
                        detail=(
                            f"{package} may not reference simulator ground truth: "
                            f"{literal!r}"
                        ),
                    )
                )

    return violations
