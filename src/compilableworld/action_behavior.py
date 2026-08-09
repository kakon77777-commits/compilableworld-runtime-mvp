"""Shared bounded contract for authored Action-scope behavior lifecycles.

The Compiler, Kernel, and Studio use this module instead of inventing their
own duration or interruption rules.  v0.1 intentionally supports only a
single queued behavior per actor and EventIR target-based interruption.
"""

from __future__ import annotations


ACTION_BEHAVIOR_FORMAT_V1 = "compilableworld.action-behaviors/v0.1"
ACTION_BEHAVIOR_FORMAT = "compilableworld.action-behaviors/v0.2"
ACTION_BEHAVIOR_SCHEMA_ID_V1 = "compilableworld.schema/action-behaviors/v0.1"
ACTION_BEHAVIOR_SCHEMA_ID = "compilableworld.schema/action-behaviors/v0.2"
ACTION_BEHAVIOR_DEFINITION_LIMIT = 1024
ACTION_BEHAVIOR_DURATION_LIMIT = 1_000_000
ACTION_BEHAVIOR_PHASE_LIMIT = 64
ACTION_BEHAVIOR_INTERRUPT_LIMIT = 16
ACTION_BEHAVIOR_INTERRUPT_EVENTS = {
    "combat.actor_defeated",
    "combat.damage_applied",
    "movement.actor_moved",
}
ACTION_BEHAVIOR_CONCURRENCY = "one_per_actor"


__all__ = [
    "ACTION_BEHAVIOR_CONCURRENCY",
    "ACTION_BEHAVIOR_DEFINITION_LIMIT",
    "ACTION_BEHAVIOR_DURATION_LIMIT",
    "ACTION_BEHAVIOR_FORMAT",
    "ACTION_BEHAVIOR_FORMAT_V1",
    "ACTION_BEHAVIOR_INTERRUPT_EVENTS",
    "ACTION_BEHAVIOR_INTERRUPT_LIMIT",
    "ACTION_BEHAVIOR_PHASE_LIMIT",
    "ACTION_BEHAVIOR_SCHEMA_ID",
    "ACTION_BEHAVIOR_SCHEMA_ID_V1",
]
