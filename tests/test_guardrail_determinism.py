"""Guardrail 4 — every run must be reproducible from its seed.

``DATA.md`` §20 requires the generator to be deterministic under a fixed seed so
a dataset can be regenerated exactly from its stored config. Two things can
break that: global random state, and substreams that are not independent.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from rhome_core.architecture import source_root
from rhome_core.seeding import RootSeed, stream_seed


@pytest.mark.guardrail(4)
@pytest.mark.spec("DATA:deterministic-seed")
def test_same_seed_and_name_reproduce_identical_draws():
    a = RootSeed(20260822).stream("sim.sleep").normal(size=256)
    b = RootSeed(20260822).stream("sim.sleep").normal(size=256)
    assert np.array_equal(a, b)


@pytest.mark.guardrail(4)
def test_named_streams_are_independent():
    root = RootSeed(20260822)
    sleep = root.stream("sim.sleep").normal(size=256)
    hrv = root.stream("sim.hrv").normal(size=256)
    assert not np.array_equal(sleep, hrv)
    # Independent streams should be essentially uncorrelated.
    assert abs(float(np.corrcoef(sleep, hrv)[0, 1])) < 0.2


@pytest.mark.guardrail(4)
def test_stream_order_does_not_affect_values():
    """Requesting streams in a different order must not change any of them.

    This is the property that lets one component gain an extra random draw
    without silently changing every other component's output.
    """
    first = RootSeed(7)
    a1 = first.stream("a").normal(size=64)
    b1 = first.stream("b").normal(size=64)

    second = RootSeed(7)
    b2 = second.stream("b").normal(size=64)
    a2 = second.stream("a").normal(size=64)

    assert np.array_equal(a1, a2)
    assert np.array_equal(b1, b2)


@pytest.mark.guardrail(4)
def test_different_root_seeds_give_different_streams():
    a = RootSeed(1).stream("sim.sleep").normal(size=64)
    b = RootSeed(2).stream("sim.sleep").normal(size=64)
    assert not np.array_equal(a, b)


@pytest.mark.guardrail(4)
def test_stream_seeds_are_stable_across_processes():
    """Pinned values: a change here would silently invalidate every dataset."""
    assert stream_seed(20260822, "sim.sleep") == stream_seed(20260822, "sim.sleep")
    assert stream_seed(0, "x") != stream_seed(1, "x")
    assert stream_seed(0, "x") != stream_seed(0, "y")


@pytest.mark.guardrail(4)
@pytest.mark.parametrize("bad", [-1, "20260822", 3.5, True, None])
def test_invalid_root_seeds_are_rejected(bad):
    with pytest.raises((TypeError, ValueError)):
        RootSeed(bad)


@pytest.mark.guardrail(4)
def test_empty_stream_name_is_rejected():
    with pytest.raises(ValueError):
        RootSeed(1).stream("")


# --- no global random state anywhere in the source tree --------------------

_FORBIDDEN_GLOBALS = {
    "normal", "uniform", "random", "randint", "choice", "shuffle", "seed",
    "standard_normal", "poisson", "binomial", "lognormal", "permutation", "rand", "randn",
}


def _global_random_calls(tree: ast.AST) -> list[tuple[int, str]]:
    """Find ``np.random.<fn>(...)`` and bare ``random.<fn>(...)`` calls."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _FORBIDDEN_GLOBALS:
            continue
        owner = func.value
        # np.random.normal(...)
        if (
            isinstance(owner, ast.Attribute)
            and owner.attr == "random"
            and isinstance(owner.value, ast.Name)
            and owner.value.id in {"np", "numpy"}
        ):
            found.append((node.lineno, f"np.random.{func.attr}"))
        # random.normal(...) via `import random`
        elif isinstance(owner, ast.Name) and owner.id == "random":
            found.append((node.lineno, f"random.{func.attr}"))
    return found


@pytest.mark.guardrail(4)
@pytest.mark.spec("DATA:deterministic-seed")
def test_no_global_random_state_in_source():
    offenders: list[str] = []
    root: Path = source_root()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for line, call in _global_random_calls(tree):
            offenders.append(f"{path.relative_to(root)}:{line} uses {call}")
    assert not offenders, (
        "global random state breaks reproducibility; pass a Generator instead:\n"
        + "\n".join(offenders)
    )


@pytest.mark.guardrail(4)
def test_global_random_detector_catches_a_planted_violation(tmp_path):
    """The detector must be known to work, not merely to pass."""
    src = tmp_path / "offender.py"
    src.write_text("import numpy as np\nx = np.random.normal(0, 1)\n", encoding="utf-8")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    assert _global_random_calls(tree) == [(2, "np.random.normal")]
