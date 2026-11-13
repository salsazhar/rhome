"""Guardrail 1 — the simulator and the engine must not be able to see each other.

If this boundary is crossed the engine is inverting its own generator, and no
evaluation result afterwards means anything. The failure would be silent, which
is exactly why it is checked mechanically rather than left to convention.
"""

from __future__ import annotations

import textwrap

import pytest

from rhome_core.architecture import (
    ALLOWED_IMPORTS,
    PACKAGES,
    check_import_boundaries,
    source_root,
)


@pytest.mark.guardrail(1)
@pytest.mark.spec("ARCH:sim-engine-separation")
def test_source_tree_has_no_boundary_violations():
    violations = check_import_boundaries()
    assert violations == [], "architectural violations:\n" + "\n".join(
        str(v) for v in violations
    )


@pytest.mark.guardrail(1)
@pytest.mark.spec("ARCH:eval-sole-exception")
def test_boundary_rules_match_the_documented_architecture():
    assert ALLOWED_IMPORTS["rhome_core"] == frozenset()
    assert ALLOWED_IMPORTS["rhome_sim"] == frozenset({"rhome_core"})
    assert ALLOWED_IMPORTS["rhome_engine"] == frozenset({"rhome_core"})
    assert ALLOWED_IMPORTS["rhome_eval"] == frozenset(
        {"rhome_core", "rhome_sim", "rhome_engine"}
    ), "evaluation is the single package allowed to see both sides"
    assert set(ALLOWED_IMPORTS) == set(PACKAGES)


# --- the checker must actually catch violations ----------------------------
# A guardrail that has never rejected anything is not known to work. These
# tests plant deliberate violations in a temporary tree and require detection.


def _package_tree(tmp_path, package: str, body: str):
    root = tmp_path / "src"
    for name in PACKAGES:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "__init__.py").write_text("", encoding="utf-8")
    (root / package / "offender.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return root


@pytest.mark.guardrail(1)
@pytest.mark.parametrize(
    "package, body, expect",
    [
        ("rhome_engine", "import rhome_sim\n", "rhome_engine may not import rhome_sim"),
        ("rhome_sim", "import rhome_engine\n", "rhome_sim may not import rhome_engine"),
        (
            "rhome_engine",
            "from rhome_sim.physiology import truth\n",
            "rhome_engine may not import rhome_sim",
        ),
        ("rhome_core", "import rhome_engine\n", "rhome_core may not import rhome_engine"),
    ],
)
def test_checker_detects_forbidden_imports(tmp_path, package, body, expect):
    root = _package_tree(tmp_path, package, body)
    violations = check_import_boundaries(root)
    assert any(v.rule == "import-boundary" and v.detail == expect for v in violations), (
        f"expected to catch {expect!r}, got {[str(v) for v in violations]}"
    )


@pytest.mark.guardrail(1)
@pytest.mark.parametrize(
    "literal",
    [
        "data/synthetic/athlete_a/hidden/latent_daily.csv",
        "latent_sets.csv",
        "scenario_manifest.csv",
    ],
)
def test_checker_detects_engine_reading_hidden_truth(tmp_path, literal):
    root = _package_tree(tmp_path, "rhome_engine", f'PATH = "{literal}"\n')
    violations = check_import_boundaries(root)
    assert any(v.rule == "hidden-data" for v in violations), (
        f"engine reference to {literal!r} was not caught"
    )


@pytest.mark.guardrail(1)
def test_docstrings_describing_the_rule_are_not_violations(tmp_path):
    """Prose explaining a boundary must not be reported as breaching it."""
    root = _package_tree(
        tmp_path,
        "rhome_engine",
        '"""This module must never read hidden/latent_daily.csv."""\n',
    )
    assert check_import_boundaries(root) == []


@pytest.mark.guardrail(1)
def test_evaluation_may_import_both_sides(tmp_path):
    root = _package_tree(tmp_path, "rhome_eval", "import rhome_sim\nimport rhome_engine\n")
    assert check_import_boundaries(root) == []


@pytest.mark.guardrail(1)
def test_checker_actually_reads_the_real_source_tree():
    """Guard against the checker passing because it found no files."""
    files = list(source_root().rglob("*.py"))
    assert len(files) >= len(PACKAGES), "checker is not seeing the source tree"


# --- the athlete's sealed history (BUILD_PLAN.md L3.9) ----------------------

@pytest.mark.guardrail(1)
def test_no_package_reaches_for_the_sealed_real_data(tmp_path):
    """One athlete, one export, one run. Reaching for it early is untestable
    afterwards: the damage is that the engine was tuned against it, and no
    later measurement can undo that.
    """
    assert not check_import_boundaries()

    package = tmp_path / "rhome_engine"
    package.mkdir()
    (package / "peek.py").write_text(
        'from pathlib import Path\n'
        'RECENT = Path("data/real/oura_sleep.csv")\n',
        encoding="utf-8",
    )
    violations = check_import_boundaries(tmp_path)
    assert [v.rule for v in violations] == ["sealed-real-data"]


@pytest.mark.guardrail(1)
def test_evaluation_may_reach_for_it_because_L39_lives_there(tmp_path):
    package = tmp_path / "rhome_eval"
    package.mkdir()
    (package / "cold_run.py").write_text(
        'VAULT = "data/real"\n', encoding="utf-8"
    )
    assert not check_import_boundaries(tmp_path)
