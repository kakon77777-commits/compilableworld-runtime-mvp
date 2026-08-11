"""Shared, bounded contract for event-driven world state machines.

The Authoring/Studio adapters, Compiler, and Runtime must agree on exactly
which EventIR payload fields may participate in deterministic equality
matching.  Keeping the contract here prevents an editor mapping from becoming
"valid" for an event that the Runtime Compiler later rejects (or vice versa).

This module deliberately contains no free-form expression evaluator.  Rich
guards remain review metadata until they are represented by a separately
versioned, bounded Runtime contract.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .kernel import WorldRuntime
    from .models import EventIR


STATE_MACHINE_FORMAT_V1 = "compilableworld.state-machines/v0.1"
STATE_MACHINE_FORMAT_V2 = "compilableworld.state-machines/v0.2"
STATE_MACHINE_FORMAT = "compilableworld.state-machines/v0.3"
STATE_MACHINE_SCHEMA_ID_V1 = "compilableworld.schema/state-machines/v0.1"
STATE_MACHINE_SCHEMA_ID_V2 = "compilableworld.schema/state-machines/v0.2"
STATE_MACHINE_SCHEMA_ID = "compilableworld.schema/state-machines/v0.3"
STATE_MACHINE_EVENT_MATCH_LIMIT = 16
STATE_MACHINE_DEFINITION_LIMIT = 1024
STATE_MACHINE_STATE_LIMIT = 256
STATE_MACHINE_TRANSITION_LIMIT = 4096
STATE_MACHINE_CONDITION_LIMIT = 16
STATE_MACHINE_TIMER_TICK_LIMIT = 1_000_000
STATE_MACHINE_REQUIREMENT_LIMIT = 32
STATE_MACHINE_PRIORITY_LIMIT = 1_000_000
STATE_MACHINE_REWARD_CURRENCY_LIMIT = 1_000_000_000
STATE_MACHINE_CONDITION_SUBJECTS = {"owner", "actor"}
STATE_MACHINE_CONDITION_OPERATORS = {
    "equals", "not_equals", "less_than", "less_or_equal", "greater_than", "greater_or_equal",
}
STATE_MACHINE_CONDITION_NAMESPACES = {
    "combat", "door", "exploration", "fsm", "health", "inventory", "magic",
    "position", "quest", "status", "wallet",
}

# Every value is a field emitted by the corresponding built-in module.  Actor
# ownership is resolved separately from ActionIR causation and is therefore not
# exposed as an ad-hoc payload match for events that do not carry it.
STATE_MACHINE_TRIGGER_EVENT_FIELDS: dict[str, set[str]] = {
    "action.failed": {
        "action_id", "behavior_id", "actor", "verb", "phase_id", "condition_id",
        "failure_code", "attempt", "max_attempts", "timeout_at_tick", "reason",
        "step_id", "child_action_id", "child_verb",
    },
    "action.child_started": {
        "parent_action_id", "behavior_id", "actor", "phase_id", "step_id",
        "child_action_id", "child_verb", "child_target",
    },
    "action.child_completed": {
        "parent_action_id", "behavior_id", "actor", "phase_id", "step_id",
        "child_action_id", "child_verb", "child_target",
    },
    "action.child_failed": {
        "parent_action_id", "behavior_id", "actor", "phase_id", "step_id",
        "child_action_id", "child_verb", "child_target", "reason",
    },
    "action.branch_selected": {
        "action_id", "behavior_id", "actor", "verb", "phase_id", "branch_id",
        "priority", "next_phase_id", "child_step_id",
    },
    "action.retry_scheduled": {
        "action_id", "behavior_id", "actor", "verb", "duration_ticks", "phase_id",
        "condition_id", "attempt", "max_attempts", "interval_ticks",
        "first_failure_tick", "retry_at_tick", "timeout_at_tick", "due_tick", "reason",
    },
    "action.scheduled": {
        "action_id", "behavior_id", "actor", "verb", "duration_ticks", "due_tick",
    },
    "action.started": {"action_id", "behavior_id", "actor", "verb", "duration_ticks"},
    "action.progressed": {
        "action_id", "behavior_id", "actor", "verb", "phase_id", "phase_title",
        "phase_index", "completed_phases", "total_phases", "next_phase_id",
        "progress_ticks", "duration_ticks",
    },
    "action.completed": {"action_id", "behavior_id", "actor", "verb", "duration_ticks"},
    "action.cancelled": {
        "action_id", "behavior_id", "actor", "verb", "duration_ticks", "due_tick", "reason",
    },
    "action.interrupted": {
        "action_id", "behavior_id", "actor", "verb", "duration_ticks", "due_tick", "reason",
    },
    "combat.actor_defeated": {"target"},
    "combat.attack_missed": {"target"},
    "combat.damage_applied": {"target", "damage", "remaining"},
    "dialogue.responded": {
        "speaker_id", "speaker_name", "topic", "resolved_topic", "dialogue_id", "text",
    },
    "dialogue.spoken": {"text"},
    "door.opened": {"door"},
    "door.unlocked": {"door"},
    "exploration.searched": {"room_id", "search_count"},
    "inventory.item_added": {"item"},
    "inventory.item_given": {"item", "actor", "recipient"},
    "inventory.item_removed": {"item"},
    "magic.cast": {"spell", "effect", "temp_hp"},
    "movement.actor_moved": {"from", "to", "direction"},
    # Terminal quest events are safe state-machine chaining points: the source
    # quest cannot leave its terminal state, while another quest may react.
    "quest.completed": {"quest_id", "title", "transition_id", "from", "to", "trigger"},
    "quest.failed": {"quest_id", "title", "transition_id", "from", "to", "trigger"},
    "fsm.completed": {
        "state_machine_id", "title", "owner_scope", "owner_id", "transition_id", "from", "to", "trigger",
    },
    "fsm.failed": {
        "state_machine_id", "title", "owner_scope", "owner_id", "transition_id", "from", "to", "trigger",
    },
}

STATE_MACHINE_OWNER_SCOPES = {"world", "region", "scene", "entity", "system"}
STATE_MACHINE_VISIBILITIES = {"public", "observable", "inferred", "private", "system_only"}


def resolve_state_machine_actor(runtime: "WorldRuntime", event: "EventIR") -> str | None:
    """Resolve the actor whose state machine may consume ``event``.

    Built-in module events inherit the originating ActionIR id as
    ``causation_id``.  Reactive modules instead point at the immediately
    preceding EventIR, so a bounded EventLog walk preserves both direct
    causation and the originating actor across multi-stage FSM/quest chains.
    Events without ActionIR provenance may still identify an explicit payload
    actor.  A target fallback is accepted only for entities that declare the
    quest component; this keeps a door or item target from accidentally
    receiving quest state.
    """
    causation_id = event.causation_id
    seen: set[str] = set()
    event_by_id = {item.event_id: item for item in runtime.event_log.events}
    for _ in range(64):
        if not causation_id or causation_id in seen:
            break
        seen.add(causation_id)
        action = runtime.actions.get(causation_id)
        if action is not None and runtime.registry.contains(action.actor_id):
            return action.actor_id
        cause = event_by_id.get(causation_id)
        if cause is None:
            break
        causation_id = cause.causation_id

    payload_actor = event.payload.get("actor")
    if isinstance(payload_actor, str) and runtime.registry.contains(payload_actor):
        return payload_actor

    target = event.target
    if isinstance(target, str) and runtime.registry.contains(target):
        entity = runtime.registry.get(target)
        if "quest" in entity.components:
            return target
    return None


def state_machine_condition_matches(
    runtime: "WorldRuntime",
    machine: dict[str, Any],
    condition: Any,
    *,
    actor_id: str | None,
) -> bool:
    """Evaluate one compiled StateIR condition without coercion or side effects.

    ``owner`` reads the machine's own authoritative owner. ``actor`` reads the
    bounded actor resolved from the triggering EventIR causation chain. Missing
    state, unknown fields, type mismatches, and non-finite numbers all fail
    closed. The Compiler normally prevents malformed conditions, but the
    Runtime repeats these checks because a package is still untrusted input.
    """
    if not isinstance(condition, dict):
        return False
    condition_id = condition.get("condition_id")
    subject = condition.get("subject")
    namespace = condition.get("namespace")
    key = condition.get("key")
    operator = condition.get("operator")
    if (
        not isinstance(condition_id, str)
        or not condition_id
        or subject not in STATE_MACHINE_CONDITION_SUBJECTS
        or namespace not in STATE_MACHINE_CONDITION_NAMESPACES
        or not isinstance(key, str)
        or not key
        or operator not in STATE_MACHINE_CONDITION_OPERATORS
    ):
        return False

    owner_id = machine.get("owner_id") if subject == "owner" else actor_id
    if not isinstance(owner_id, str) or not owner_id:
        return False
    missing = object()
    actual = runtime.state.get(owner_id, namespace, key, missing)
    expected = condition.get("value")
    if (
        actual is missing
        or not _finite_condition_scalar(actual)
        or not _finite_condition_scalar(expected)
    ):
        return False
    if operator in {"equals", "not_equals"}:
        equal = _strict_scalar_equal(actual, expected)
        return equal if operator == "equals" else not equal
    if (
        isinstance(actual, bool)
        or isinstance(expected, bool)
        or not isinstance(actual, (int, float))
        or not isinstance(expected, (int, float))
    ):
        return False
    return {
        "less_than": actual < expected,
        "less_or_equal": actual <= expected,
        "greater_than": actual > expected,
        "greater_or_equal": actual >= expected,
    }[operator]


def _strict_scalar_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual == expected
    return type(actual) is type(expected) and actual == expected


def _finite_condition_scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, (str, bool, int))
        or (isinstance(value, float) and math.isfinite(value))
    )


__all__ = [
    "STATE_MACHINE_CONDITION_LIMIT",
    "STATE_MACHINE_CONDITION_NAMESPACES",
    "STATE_MACHINE_CONDITION_OPERATORS",
    "STATE_MACHINE_CONDITION_SUBJECTS",
    "STATE_MACHINE_DEFINITION_LIMIT",
    "STATE_MACHINE_EVENT_MATCH_LIMIT",
    "STATE_MACHINE_FORMAT",
    "STATE_MACHINE_FORMAT_V1",
    "STATE_MACHINE_FORMAT_V2",
    "STATE_MACHINE_OWNER_SCOPES",
    "STATE_MACHINE_PRIORITY_LIMIT",
    "STATE_MACHINE_REQUIREMENT_LIMIT",
    "STATE_MACHINE_REWARD_CURRENCY_LIMIT",
    "STATE_MACHINE_SCHEMA_ID",
    "STATE_MACHINE_SCHEMA_ID_V1",
    "STATE_MACHINE_SCHEMA_ID_V2",
    "STATE_MACHINE_STATE_LIMIT",
    "STATE_MACHINE_TRANSITION_LIMIT",
    "STATE_MACHINE_TIMER_TICK_LIMIT",
    "STATE_MACHINE_TRIGGER_EVENT_FIELDS",
    "STATE_MACHINE_VISIBILITIES",
    "resolve_state_machine_actor",
    "state_machine_condition_matches",
]
