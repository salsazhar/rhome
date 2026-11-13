"""The Rhome inference engine.

Consumes only observable data — logged sets, exercise metadata and wearable
measurements — and estimates the athlete's latent training state.

Two hard boundaries apply. The engine must never import ``rhome_sim``, and it
must never read anything under a ``hidden/`` data directory: those files hold
the simulator's ground truth and the scenario manifest, which are the answers
to the questions the engine is being asked.
"""

__all__ = ["ARCHITECTURE_ROLE"]

ARCHITECTURE_ROLE = "inference engine; may import rhome_core only; observable data only"
