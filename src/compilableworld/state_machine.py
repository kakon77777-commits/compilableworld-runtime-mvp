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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .kernel import WorldRuntime
    from .models import EventIR


STATE_MACHINE_EVENT_MATCH_LIMIT = 16
STATE_MACHINE_DEFINITION_LIMIT = 1024
STATE_MACHINE_STATE_LIMIT = 256
STATE_MACHINE_TRANSITION_LIMIT = 4096
STATE_MACHINE_REQUIREMENT_LIMIT = 32
STATE_MACHINE_PRIORITY_LIMIT = 1_000_000
STATE_MACHINE_REWARD_CURRENCY_LIMIT = 1_000_000_000

# Every value is a field emitted by the corresponding built-in module.  Actor
# ownership is resolved separately from ActionIR causation and is therefore not
# exposed as an ad-hoc payload match for events that do not carry it.
STATE_MACHINE_TRIGGER_EVENT_FIELDS: dict[str, set[str]] = {
    "action.failed": {
        "action_id", "behavior_id", "actor", "verb", "phase_id", "condition_id", "reason",
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


__all__ = [
    "STATE_MACHINE_DEFINITION_LIMIT",
    "STATE_MACHINE_EVENT_MATCH_LIMIT",
    "STATE_MACHINE_OWNER_SCOPES",
    "STATE_MACHINE_PRIORITY_LIMIT",
    "STATE_MACHINE_REQUIREMENT_LIMIT",
    "STATE_MACHINE_REWARD_CURRENCY_LIMIT",
    "STATE_MACHINE_STATE_LIMIT",
    "STATE_MACHINE_TRANSITION_LIMIT",
    "STATE_MACHINE_TRIGGER_EVENT_FIELDS",
    "STATE_MACHINE_VISIBILITIES",
    "resolve_state_machine_actor",
]
