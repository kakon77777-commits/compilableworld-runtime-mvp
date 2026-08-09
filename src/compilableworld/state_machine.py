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
STATE_MACHINE_REQUIREMENT_LIMIT = 32
STATE_MACHINE_PRIORITY_LIMIT = 1_000_000
STATE_MACHINE_REWARD_CURRENCY_LIMIT = 1_000_000_000

# Every value is a field emitted by the corresponding built-in module.  Actor
# ownership is resolved separately from ActionIR causation and is therefore not
# exposed as an ad-hoc payload match for events that do not carry it.
STATE_MACHINE_TRIGGER_EVENT_FIELDS: dict[str, set[str]] = {
    "action.failed": {"verb", "reason"},
    "combat.actor_defeated": {"target"},
    "combat.attack_missed": {"target"},
    "combat.damage_applied": {"target", "damage", "remaining"},
    "dialogue.responded": {
        "speaker_id", "speaker_name", "topic", "resolved_topic", "dialogue_id", "text",
    },
    "dialogue.spoken": {"text"},
    "door.opened": {"door"},
    "door.unlocked": {"door"},
    "inventory.item_added": {"item"},
    "inventory.item_given": {"item", "actor", "recipient"},
    "inventory.item_removed": {"item"},
    "magic.cast": {"spell", "effect", "temp_hp"},
    "movement.actor_moved": {"from", "to", "direction"},
    # Terminal quest events are safe state-machine chaining points: the source
    # quest cannot leave its terminal state, while another quest may react.
    "quest.completed": {"quest_id", "title", "transition_id", "from", "to", "trigger"},
    "quest.failed": {"quest_id", "title", "transition_id", "from", "to", "trigger"},
}


def resolve_state_machine_actor(runtime: "WorldRuntime", event: "EventIR") -> str | None:
    """Resolve the actor whose state machine may consume ``event``.

    Built-in module events inherit the originating ActionIR id as
    ``causation_id``.  That immutable provenance is preferred over payload or
    target fields because door/combat events intentionally target the affected
    entity, not necessarily the acting player.  Events without ActionIR
    causation may still identify an explicit payload actor.  A target fallback
    is accepted only for entities that declare the quest component; this keeps
    a door or item target from accidentally receiving quest state.
    """
    if event.causation_id:
        action = runtime.actions.get(event.causation_id)
        if action is not None and runtime.registry.contains(action.actor_id):
            return action.actor_id

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
    "STATE_MACHINE_EVENT_MATCH_LIMIT",
    "STATE_MACHINE_PRIORITY_LIMIT",
    "STATE_MACHINE_REQUIREMENT_LIMIT",
    "STATE_MACHINE_REWARD_CURRENCY_LIMIT",
    "STATE_MACHINE_TRIGGER_EVENT_FIELDS",
    "resolve_state_machine_actor",
]
