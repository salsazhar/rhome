"""The Athlete A simulator.

Generates observable training and wearable data from a hidden physiological
state, plus the latent ground truth used to mark the engine's work.

The simulator must be structurally richer than the inference engine
(``DATA.md`` §16.2). It must never import ``rhome_engine``, and the engine must
never import it: if the two were coupled, the engine would be inverting its own
generator and no result afterwards would mean anything.
"""

__all__ = ["ARCHITECTURE_ROLE"]

ARCHITECTURE_ROLE = "simulator; may import rhome_core only"
