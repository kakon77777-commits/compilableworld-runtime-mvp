"""Shared bounded contract for authored Action-scope behavior lifecycles.

The Compiler, Kernel, and Studio use this module instead of inventing their
own duration, phase-gate, retry, child-step, branch, or interruption rules.
Older source versions remain compiler inputs; the current contract adds sticky
conditional child branches with compile-time validated static DAG routing.
"""

from __future__ import annotations


ACTION_BEHAVIOR_FORMAT_V1 = "compilableworld.action-behaviors/v0.1"
ACTION_BEHAVIOR_FORMAT_V2 = "compilableworld.action-behaviors/v0.2"
ACTION_BEHAVIOR_FORMAT_V3 = "compilableworld.action-behaviors/v0.3"
ACTION_BEHAVIOR_FORMAT_V4 = "compilableworld.action-behaviors/v0.4"
ACTION_BEHAVIOR_FORMAT_V5 = "compilableworld.action-behaviors/v0.5"
ACTION_BEHAVIOR_FORMAT_V6 = "compilableworld.action-behaviors/v0.6"
ACTION_BEHAVIOR_FORMAT = "compilableworld.action-behaviors/v0.7"
ACTION_BEHAVIOR_SCHEMA_ID_V1 = "compilableworld.schema/action-behaviors/v0.1"
ACTION_BEHAVIOR_SCHEMA_ID_V2 = "compilableworld.schema/action-behaviors/v0.2"
ACTION_BEHAVIOR_SCHEMA_ID_V3 = "compilableworld.schema/action-behaviors/v0.3"
ACTION_BEHAVIOR_SCHEMA_ID_V4 = "compilableworld.schema/action-behaviors/v0.4"
ACTION_BEHAVIOR_SCHEMA_ID_V5 = "compilableworld.schema/action-behaviors/v0.5"
ACTION_BEHAVIOR_SCHEMA_ID_V6 = "compilableworld.schema/action-behaviors/v0.6"
ACTION_BEHAVIOR_SCHEMA_ID = "compilableworld.schema/action-behaviors/v0.7"
ACTION_BEHAVIOR_EXECUTION_MODEL_STATIC_DAG = "static_dag"
ACTION_BEHAVIOR_DEFINITION_LIMIT = 1024
ACTION_BEHAVIOR_DURATION_LIMIT = 1_000_000
ACTION_BEHAVIOR_PHASE_LIMIT = 64
ACTION_BEHAVIOR_CONDITION_LIMIT = 16
ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT = 16
ACTION_BEHAVIOR_CHILD_ARG_LIMIT = 16
ACTION_BEHAVIOR_BRANCH_LIMIT = 16
ACTION_BEHAVIOR_BRANCH_PRIORITY_LIMIT = 1_000_000
ACTION_BEHAVIOR_INTERRUPT_LIMIT = 16
ACTION_BEHAVIOR_INTERRUPT_EVENTS = {
    "combat.actor_defeated",
    "combat.damage_applied",
    "movement.actor_moved",
}
ACTION_BEHAVIOR_CONCURRENCY = "one_per_actor"
ACTION_BEHAVIOR_CONDITION_SUBJECTS = {"actor", "target"}
ACTION_BEHAVIOR_CONDITION_OPERATORS = {
    "equals", "not_equals", "less_than", "less_or_equal", "greater_than", "greater_or_equal",
}
ACTION_BEHAVIOR_CONDITION_NAMESPACES = {
    "combat", "door", "exploration", "fsm", "health", "inventory", "magic",
    "position", "quest", "status", "wallet",
}
ACTION_BEHAVIOR_CHILD_MODULES = {
    "attack": "combat.basic",
    "cast": "magic.core",
    "drop": "inventory.core",
    "give": "inventory.core",
    "inventory": "inventory.core",
    "look": "room.core",
    "move": "movement.core",
    "open": "door.core",
    "quests": "quest.core",
    "say": "dialogue.core",
    "status": "health.core",
    "take": "inventory.core",
    "talk": "dialogue.core",
    "unlock": "door.core",
}
ACTION_BEHAVIOR_CHILD_ARG_FIELDS = {
    "attack": set(),
    "cast": {"spell"},
    "drop": set(),
    "give": {"recipient"},
    "inventory": set(),
    "look": set(),
    "move": {"direction"},
    "open": set(),
    "quests": set(),
    "say": {"text"},
    "status": set(),
    "take": set(),
    "talk": {"topic"},
    "unlock": set(),
}
ACTION_BEHAVIOR_CHILD_REQUIRED_ARGS = {
    "cast": {"spell"},
    "give": {"recipient"},
    "move": {"direction"},
    "say": {"text"},
}
ACTION_BEHAVIOR_CHILD_TARGET_VERBS = {
    "attack", "drop", "give", "open", "take", "talk", "unlock",
}


__all__ = [
    "ACTION_BEHAVIOR_CONCURRENCY",
    "ACTION_BEHAVIOR_CONDITION_LIMIT",
    "ACTION_BEHAVIOR_CONDITION_NAMESPACES",
    "ACTION_BEHAVIOR_CONDITION_OPERATORS",
    "ACTION_BEHAVIOR_CONDITION_SUBJECTS",
    "ACTION_BEHAVIOR_CHILD_ARG_FIELDS",
    "ACTION_BEHAVIOR_CHILD_ARG_LIMIT",
    "ACTION_BEHAVIOR_CHILD_MODULES",
    "ACTION_BEHAVIOR_CHILD_REQUIRED_ARGS",
    "ACTION_BEHAVIOR_CHILD_TARGET_VERBS",
    "ACTION_BEHAVIOR_BRANCH_LIMIT",
    "ACTION_BEHAVIOR_BRANCH_PRIORITY_LIMIT",
    "ACTION_BEHAVIOR_DEFINITION_LIMIT",
    "ACTION_BEHAVIOR_DURATION_LIMIT",
    "ACTION_BEHAVIOR_EXECUTION_MODEL_STATIC_DAG",
    "ACTION_BEHAVIOR_FORMAT",
    "ACTION_BEHAVIOR_FORMAT_V1",
    "ACTION_BEHAVIOR_FORMAT_V2",
    "ACTION_BEHAVIOR_FORMAT_V3",
    "ACTION_BEHAVIOR_FORMAT_V4",
    "ACTION_BEHAVIOR_FORMAT_V5",
    "ACTION_BEHAVIOR_FORMAT_V6",
    "ACTION_BEHAVIOR_INTERRUPT_EVENTS",
    "ACTION_BEHAVIOR_INTERRUPT_LIMIT",
    "ACTION_BEHAVIOR_PHASE_LIMIT",
    "ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT",
    "ACTION_BEHAVIOR_SCHEMA_ID",
    "ACTION_BEHAVIOR_SCHEMA_ID_V1",
    "ACTION_BEHAVIOR_SCHEMA_ID_V2",
    "ACTION_BEHAVIOR_SCHEMA_ID_V3",
    "ACTION_BEHAVIOR_SCHEMA_ID_V4",
    "ACTION_BEHAVIOR_SCHEMA_ID_V5",
    "ACTION_BEHAVIOR_SCHEMA_ID_V6",
]
