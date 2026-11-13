"""Shared substrate for Rhome.

Muscle taxonomy, exercise metadata, time handling, the parameter registry and
the relative-intensity mapping live here.

This package must not import from ``rhome_sim``, ``rhome_engine`` or
``rhome_eval``. It sits beneath all three, and depending upward would let the
simulator and the engine reach each other through it. Enforced by
``tests/test_guardrail_import_boundary.py``.
"""

__all__ = ["ARCHITECTURE_ROLE"]

ARCHITECTURE_ROLE = "shared substrate; depends on nothing else in rhome"
