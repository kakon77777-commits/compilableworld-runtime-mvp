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
import re
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .kernel import WorldRuntime
    from .models import EventIR


STATE_MACHINE_FORMAT_V1 = "compilableworld.state-machines/v0.1"
STATE_MACHINE_FORMAT_V2 = "compilableworld.state-machines/v0.2"
STATE_MACHINE_FORMAT_V3 = "compilableworld.state-machines/v0.3"
STATE_MACHINE_FORMAT_V4 = "compilableworld.state-machines/v0.4"
STATE_MACHINE_FORMAT_V5 = "compilableworld.state-machines/v0.5"
STATE_MACHINE_FORMAT = "compilableworld.state-machines/v0.6"
STATE_MACHINE_SCHEMA_ID_V1 = "compilableworld.schema/state-machines/v0.1"
STATE_MACHINE_SCHEMA_ID_V2 = "compilableworld.schema/state-machines/v0.2"
STATE_MACHINE_SCHEMA_ID_V3 = "compilableworld.schema/state-machines/v0.3"
STATE_MACHINE_SCHEMA_ID_V4 = "compilableworld.schema/state-machines/v0.4"
STATE_MACHINE_SCHEMA_ID_V5 = "compilableworld.schema/state-machines/v0.5"
STATE_MACHINE_SCHEMA_ID = "compilableworld.schema/state-machines/v0.6"
STATE_MACHINE_EVENT_MATCH_LIMIT = 16
STATE_MACHINE_DEFINITION_LIMIT = 1024
STATE_MACHINE_STATE_LIMIT = 256
STATE_MACHINE_TRANSITION_LIMIT = 4096
STATE_MACHINE_CONDITION_LIMIT = 16
STATE_MACHINE_CONDITION_GROUP_DEPTH_LIMIT = 4
STATE_MACHINE_CONDITION_NODE_LIMIT = 64
STATE_MACHINE_CONDITION_LEAF_LIMIT = 32
STATE_MACHINE_TIMER_TICK_LIMIT = 1_000_000
STATE_MACHINE_REACTION_DEPTH_LIMIT = 64
STATE_MACHINE_HIERARCHY_DEPTH_LIMIT = 16
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
        "state_machine_id", "title", "owner_scope", "owner_id", "transition_id",
        "from", "to", "from_leaf", "to_leaf", "trigger",
    },
    "fsm.failed": {
        "state_machine_id", "title", "owner_scope", "owner_id", "transition_id",
        "from", "to", "from_leaf", "to_leaf", "trigger",
    },
    "fsm.transitioned": {
        "state_machine_id", "title", "owner_scope", "owner_id", "transition_id",
        "from", "to", "from_leaf", "to_leaf", "trigger",
    },
}

STATE_MACHINE_OWNER_SCOPES = {"world", "region", "scene", "entity", "system"}
STATE_MACHINE_VISIBILITIES = {"public", "observable", "inferred", "private", "system_only"}
_STATE_MACHINE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")


def _state_machine_hierarchy_maps(
    machine: Any,
) -> tuple[dict[str, str], dict[str, str]] | None:
    """Parse a flat legacy machine or a structurally complete hierarchy."""
    if not isinstance(machine, dict):
        return None
    states = machine.get("states")
    if (
        not isinstance(states, list)
        or any(not isinstance(state, str) or not state for state in states)
        or len(states) != len(set(states))
    ):
        return None
    hierarchy = machine.get("hierarchy")
    if hierarchy is None:
        return {}, {}
    if not isinstance(hierarchy, dict) or set(hierarchy) != {
        "parent_by_state", "initial_child_by_state",
    }:
        return None
    parents = hierarchy.get("parent_by_state")
    initial_children = hierarchy.get("initial_child_by_state")
    if not isinstance(parents, dict) or not isinstance(initial_children, dict):
        return None
    state_set = set(states)
    if any(
        not isinstance(child, str)
        or not isinstance(parent, str)
        or child not in state_set
        or parent not in state_set
        or child == parent
        for child, parent in parents.items()
    ):
        return None
    compounds = set(parents.values())
    if set(initial_children) != compounds or any(
        not isinstance(parent, str)
        or not isinstance(child, str)
        or child not in state_set
        or parents.get(child) != parent
        for parent, child in initial_children.items()
    ):
        return None
    return dict(parents), dict(initial_children)


def state_machine_parent_by_state(machine: Any) -> dict[str, str]:
    """Return a defensive copy of the compiled direct-parent mapping."""
    maps = _state_machine_hierarchy_maps(machine)
    return dict(maps[0]) if maps is not None else {}


def state_machine_initial_child_by_state(machine: Any) -> dict[str, str]:
    """Return a defensive copy of deterministic compound entry targets."""
    maps = _state_machine_hierarchy_maps(machine)
    return dict(maps[1]) if maps is not None else {}


def state_machine_lineage(machine: Any, state: Any) -> tuple[str, ...]:
    """Return ``state -> ... -> root`` or an empty tuple for malformed input."""
    states = machine.get("states") if isinstance(machine, dict) else None
    if (
        not isinstance(state, str)
        or not isinstance(states, list)
        or state not in states
    ):
        return ()
    maps = _state_machine_hierarchy_maps(machine)
    if maps is None:
        return ()
    parents = maps[0]
    lineage: list[str] = []
    seen: set[str] = set()
    current = state
    for _ in range(STATE_MACHINE_HIERARCHY_DEPTH_LIMIT + 1):
        if current in seen or current not in states:
            return ()
        lineage.append(current)
        seen.add(current)
        parent = parents.get(current)
        if parent is None:
            return tuple(lineage)
        current = parent
    return ()


def state_machine_state_path(machine: Any, state: Any) -> tuple[str, ...]:
    """Return the root-to-state path used by read-only Studio projections."""
    lineage = state_machine_lineage(machine, state)
    return tuple(reversed(lineage)) if lineage else ()


def state_machine_state_matches(machine: Any, source: Any, active_leaf: Any) -> bool:
    """Whether an authored source state contains the current active leaf."""
    return isinstance(source, str) and source in state_machine_lineage(machine, active_leaf)


def state_machine_is_active_leaf(machine: Any, state: Any) -> bool:
    """Fail closed unless ``state`` is a declared leaf in the compiled tree."""
    maps = _state_machine_hierarchy_maps(machine)
    if maps is None:
        return False
    parents, initial_children = maps
    return bool(
        state_machine_lineage(machine, state)
        and state not in initial_children
        and state not in set(parents.values())
    )


def state_machine_resolve_leaf(machine: Any, target: Any) -> str | None:
    """Resolve a leaf or compound target through bounded initial-child entry."""
    states = machine.get("states") if isinstance(machine, dict) else None
    if not isinstance(target, str) or not isinstance(states, list) or target not in states:
        return None
    maps = _state_machine_hierarchy_maps(machine)
    if maps is None:
        return None
    parents, initial_children = maps
    seen: set[str] = set()
    current = target
    for _ in range(STATE_MACHINE_HIERARCHY_DEPTH_LIMIT + 1):
        if current in seen or current not in states:
            return None
        seen.add(current)
        child = initial_children.get(current)
        if child is None:
            return current if state_machine_lineage(machine, current) else None
        if parents.get(child) != current:
            return None
        current = child
    return None


def validate_compiled_state_machines(
    machines: Any,
    *,
    world_id: str,
    region_ids: set[str],
    room_ids: set[str],
    entity_ids: set[str],
    enabled_modules: set[str],
) -> None:
    """Validate the bounded StateIR subset stored in a Runtime Package.

    Compiler validation is not a trust boundary for a package loaded later
    from disk.  This dependency-free validator repeats the compiled shape,
    identifier, trigger, hierarchy, condition, and budget checks needed by the
    Runtime before modules subscribe to any events.
    """

    if not isinstance(machines, list) or len(machines) > STATE_MACHINE_DEFINITION_LIMIT:
        raise ValueError("state_machines must be a bounded array")
    if machines and "state_machine.core" not in enabled_modules:
        raise ValueError("state_machine.core is not enabled")

    machine_fields = {
        "state_machine_id", "title", "owner_scope", "owner_id", "states",
        "initial_state", "initial_leaf", "hierarchy", "persistence", "visibility",
        "authority", "transitions",
    }
    machine_ids: set[str] = set()
    state_paths: set[tuple[str, str]] = set()
    for machine_index, machine in enumerate(machines):
        label = f"state_machines[{machine_index}]"
        if not isinstance(machine, dict) or set(machine) != machine_fields:
            raise ValueError(f"{label} has an invalid compiled shape")
        machine_id = machine.get("state_machine_id")
        owner_id = machine.get("owner_id")
        states = machine.get("states")
        if (
            not _valid_state_machine_id(machine_id)
            or machine_id == "state"
            or machine_id in machine_ids
            or not isinstance(machine.get("title"), str)
            or not machine["title"].strip()
            or machine.get("owner_scope") not in STATE_MACHINE_OWNER_SCOPES
            or not _valid_state_machine_id(owner_id)
            or not isinstance(states, list)
            or not 2 <= len(states) <= STATE_MACHINE_STATE_LIMIT
            or any(not _valid_state_machine_id(state) for state in states)
            or len(states) != len(set(states))
            or machine.get("initial_state") not in states
            or machine.get("initial_leaf") not in states
            or machine.get("persistence") != "runtime"
            or machine.get("visibility") not in STATE_MACHINE_VISIBILITIES
            or machine.get("authority") != "state_machine.core"
        ):
            raise ValueError(f"{label} violates the compiled StateIR contract")
        owner_scope = machine["owner_scope"]
        owner_valid = {
            "world": owner_id == world_id,
            "region": owner_id in region_ids,
            "scene": owner_id in room_ids,
            "entity": owner_id in entity_ids,
            "system": owner_id.startswith("system."),
        }[owner_scope]
        if not owner_valid:
            raise ValueError(f"{label}.owner_id does not exist in its declared scope")
        machine_ids.add(machine_id)
        state_path = (owner_id, machine_id)
        if state_path in state_paths:
            raise ValueError(f"{label} duplicates a StateStore path")
        state_paths.add(state_path)

        maps = _state_machine_hierarchy_maps(machine)
        if maps is None or any(not state_machine_lineage(machine, state) for state in states):
            raise ValueError(f"{label}.hierarchy is invalid")
        parents, initial_children = maps
        if any(terminal in parents or terminal in initial_children for terminal in {"completed", "failed"}):
            raise ValueError(f"{label} has a non-root terminal state")
        if state_machine_resolve_leaf(machine, machine["initial_state"]) != machine["initial_leaf"]:
            raise ValueError(f"{label}.initial_leaf does not match initial_state")

        transitions = machine.get("transitions")
        if (
            not isinstance(transitions, list)
            or not 1 <= len(transitions) <= STATE_MACHINE_TRANSITION_LIMIT
        ):
            raise ValueError(f"{label}.transitions is invalid")
        transition_ids: set[str] = set()
        condition_ids: set[str] = set()
        dispatches: set[tuple[str, str, int]] = set()
        for transition_index, transition in enumerate(transitions):
            transition_label = f"{label}.transitions[{transition_index}]"
            _validate_compiled_state_machine_transition(
                machine,
                transition,
                transition_label,
                transition_ids=transition_ids,
                condition_ids=condition_ids,
                dispatches=dispatches,
            )
        _validate_compiled_state_machine_reachability(machine, label)
    _validate_compiled_state_machine_reactions(machines)


def _validate_compiled_state_machine_reachability(
    machine: dict[str, Any],
    label: str,
) -> None:
    reachable_leaves = {machine["initial_leaf"]}
    changed = True
    while changed:
        changed = False
        for transition in machine["transitions"]:
            if not any(
                state_machine_state_matches(machine, transition["from"], leaf)
                for leaf in reachable_leaves
            ):
                continue
            target_leaf = state_machine_resolve_leaf(machine, transition["to"])
            if target_leaf is not None and target_leaf not in reachable_leaves:
                reachable_leaves.add(target_leaf)
                changed = True
    reachable_states = {
        state
        for leaf in reachable_leaves
        for state in state_machine_lineage(machine, leaf)
    }
    if set(machine["states"]) != reachable_states or any(
        not any(
            state_machine_state_matches(machine, transition["from"], leaf)
            for leaf in reachable_leaves
        )
        for transition in machine["transitions"]
    ):
        raise ValueError(f"{label} contains unreachable states or transitions")


def _validate_compiled_state_machine_reactions(machines: list[dict[str, Any]]) -> None:
    by_id = {machine["state_machine_id"]: machine for machine in machines}
    edges: dict[str, set[str]] = {machine_id: set() for machine_id in by_id}
    for target in machines:
        target_id = target["state_machine_id"]
        for transition in target["transitions"]:
            if transition.get("on") != "fsm.transitioned":
                continue
            event_match = transition["event_match"]
            source_id = event_match.get("state_machine_id")
            source_transition_id = event_match.get("transition_id")
            source = by_id.get(source_id) if isinstance(source_id, str) else None
            source_transition = next((
                item for item in source.get("transitions", [])
                if item.get("transition_id") == source_transition_id
            ), None) if isinstance(source, dict) else None
            if source is None or source_transition is None:
                raise ValueError(
                    f"state machine {target_id} references an unknown fsm transition"
                )
            expected = {
                "state_machine_id": source_id,
                "title": source["title"],
                "owner_scope": source["owner_scope"],
                "owner_id": source["owner_id"],
                "transition_id": source_transition_id,
                "from": source_transition["from"],
                "to": source_transition["to"],
                "to_leaf": state_machine_resolve_leaf(source, source_transition["to"]),
                "trigger": source_transition.get("on", "fsm.timer_elapsed"),
            }
            if any(
                key in expected and value != expected[key]
                for key, value in event_match.items()
            ):
                raise ValueError(
                    f"state machine {target_id} event_match disagrees with its source"
                )
            matched_from_leaf = event_match.get("from_leaf")
            if matched_from_leaf is not None and not (
                state_machine_is_active_leaf(source, matched_from_leaf)
                and state_machine_state_matches(
                    source, source_transition["from"], matched_from_leaf,
                )
            ):
                raise ValueError(
                    f"state machine {target_id} matches a leaf outside its source"
                )
            edges[source_id].add(target_id)

    visiting: list[str] = []
    visited: set[str] = set()

    def visit(machine_id: str) -> None:
        if machine_id in visiting:
            raise ValueError("fsm.transitioned dependencies contain a cycle")
        if machine_id in visited:
            return
        visiting.append(machine_id)
        for target_id in sorted(edges[machine_id]):
            visit(target_id)
        visiting.pop()
        visited.add(machine_id)

    for machine_id in sorted(edges):
        visit(machine_id)

    indegree = {machine_id: 0 for machine_id in edges}
    for targets in edges.values():
        for target_id in targets:
            indegree[target_id] += 1
    queue = deque(sorted(machine_id for machine_id, degree in indegree.items() if degree == 0))
    depth = {machine_id: 0 for machine_id in edges}
    while queue:
        source_id = queue.popleft()
        for target_id in sorted(edges[source_id]):
            depth[target_id] = max(depth[target_id], depth[source_id] + 1)
            if depth[target_id] > STATE_MACHINE_REACTION_DEPTH_LIMIT:
                raise ValueError("fsm.transitioned dependencies exceed the depth budget")
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)


def _validate_compiled_state_machine_transition(
    machine: dict[str, Any],
    transition: Any,
    label: str,
    *,
    transition_ids: set[str],
    condition_ids: set[str],
    dispatches: set[tuple[str, str, int]],
) -> None:
    base_fields = {"transition_id", "from", "to", "when", "priority"}
    if not isinstance(transition, dict):
        raise ValueError(f"{label} must be an object")
    has_event = "on" in transition
    has_timer = "after_ticks" in transition
    expected_fields = (
        base_fields | {"on", "event_match"}
        if has_event and not has_timer
        else base_fields | {"after_ticks"}
        if has_timer and not has_event
        else set()
    )
    if not expected_fields or set(transition) != expected_fields:
        raise ValueError(f"{label} has an invalid compiled transition shape")

    transition_id = transition.get("transition_id")
    from_state = transition.get("from")
    to_state = transition.get("to")
    priority = transition.get("priority")
    states = machine["states"]
    if (
        not _valid_state_machine_id(transition_id)
        or transition_id in transition_ids
        or from_state not in states
        or to_state not in states
        or from_state == to_state
        or from_state in {"completed", "failed"}
        or isinstance(priority, bool)
        or not isinstance(priority, int)
        or not 0 <= priority <= STATE_MACHINE_PRIORITY_LIMIT
    ):
        raise ValueError(f"{label} violates the compiled transition contract")
    transition_ids.add(transition_id)
    target_leaf = state_machine_resolve_leaf(machine, to_state)
    if target_leaf is None or state_machine_state_matches(machine, from_state, target_leaf):
        raise ValueError(f"{label}.to does not resolve outside its source subtree")

    trigger_key = "@timer"
    if has_event:
        event_type = transition.get("on")
        event_match = transition.get("event_match")
        if (
            event_type not in STATE_MACHINE_TRIGGER_EVENT_FIELDS
            or not isinstance(event_match, dict)
            or len(event_match) > STATE_MACHINE_EVENT_MATCH_LIMIT
            or set(event_match) - STATE_MACHINE_TRIGGER_EVENT_FIELDS[event_type]
            or any(not _finite_condition_scalar(value) for value in event_match.values())
            or (
                event_type == "fsm.transitioned"
                and not {"state_machine_id", "transition_id"}.issubset(event_match)
            )
        ):
            raise ValueError(f"{label} has an invalid event trigger")
        trigger_key = event_type
    else:
        after_ticks = transition.get("after_ticks")
        if (
            isinstance(after_ticks, bool)
            or not isinstance(after_ticks, int)
            or not 1 <= after_ticks <= STATE_MACHINE_TIMER_TICK_LIMIT
            or not state_machine_is_active_leaf(machine, from_state)
        ):
            raise ValueError(f"{label} has an invalid timer trigger")

    dispatch = (from_state, trigger_key, priority)
    if dispatch in dispatches:
        raise ValueError(f"{label} duplicates a transition dispatch")
    dispatches.add(dispatch)
    _validate_compiled_condition_expression(
        transition["when"],
        condition_ids=condition_ids,
        timer_transition=has_timer,
    )


def _validate_compiled_condition_expression(
    expression: Any,
    *,
    condition_ids: set[str],
    timer_transition: bool,
) -> None:
    budget = {"nodes": 0, "leaves": 0}

    def visit(node: Any, group_depth: int) -> None:
        budget["nodes"] += 1
        if budget["nodes"] > STATE_MACHINE_CONDITION_NODE_LIMIT:
            raise ValueError("condition expression exceeds its node budget")
        condition_fields = {
            "condition_id", "subject", "namespace", "key", "operator", "value",
        }
        if isinstance(node, dict) and set(node) == condition_fields:
            budget["leaves"] += 1
            condition_id = node.get("condition_id")
            operator = node.get("operator")
            expected = node.get("value")
            if (
                budget["leaves"] > STATE_MACHINE_CONDITION_LEAF_LIMIT
                or not _valid_state_machine_id(condition_id)
                or condition_id in condition_ids
                or node.get("subject") not in STATE_MACHINE_CONDITION_SUBJECTS
                or (timer_transition and node.get("subject") == "actor")
                or node.get("namespace") not in STATE_MACHINE_CONDITION_NAMESPACES
                or not _valid_state_machine_id(node.get("key"))
                or operator not in STATE_MACHINE_CONDITION_OPERATORS
                or not _finite_condition_scalar(expected)
                or (
                    operator not in {"equals", "not_equals"}
                    and (isinstance(expected, bool) or not isinstance(expected, (int, float)))
                )
            ):
                raise ValueError("condition leaf violates the compiled contract")
            condition_ids.add(condition_id)
            return
        if not isinstance(node, dict) or set(node) not in ({"all"}, {"any"}, {"not"}):
            raise ValueError("condition expression has an invalid shape")
        next_depth = group_depth + 1
        if next_depth > STATE_MACHINE_CONDITION_GROUP_DEPTH_LIMIT:
            raise ValueError("condition expression exceeds its group depth")
        if "not" in node:
            visit(node["not"], next_depth)
            return
        operator = "all" if "all" in node else "any"
        children = node[operator]
        if (
            not isinstance(children, list)
            or len(children) > STATE_MACHINE_CONDITION_LIMIT
            or (operator == "any" and not children)
        ):
            raise ValueError("condition group has an invalid child count")
        for child in children:
            visit(child, next_depth)

    if isinstance(expression, list):
        if len(expression) > STATE_MACHINE_CONDITION_LIMIT:
            raise ValueError("legacy condition list exceeds its budget")
        for condition in expression:
            visit(condition, 0)
        return
    visit(expression, 0)


def _valid_state_machine_id(value: Any) -> bool:
    return isinstance(value, str) and _STATE_MACHINE_ID_RE.fullmatch(value) is not None


def resolve_state_machine_actor(
    runtime: "WorldRuntime",
    event: "EventIR",
    *,
    require_action_causation: bool = False,
) -> str | None:
    """Resolve the actor whose state machine may consume ``event``.

    Built-in module events inherit the originating ActionIR id as
    ``causation_id``.  Reactive modules instead point at the immediately
    preceding EventIR, so a bounded EventLog walk preserves both direct
    causation and the originating actor across multi-stage FSM/quest chains.
    StateIR actor conditions set ``require_action_causation`` so payload
    metadata cannot become an authoritative actor. Quest compatibility may
    still identify an explicit payload actor, or a target entity that declares
    the quest component.
    """
    causation_id = event.causation_id
    seen: set[str] = set()
    event_by_id = {item.event_id: item for item in runtime.event_log.events}
    for _ in range(STATE_MACHINE_REACTION_DEPTH_LIMIT + 4):
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

    if require_action_causation:
        return None

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
    budget = {"nodes": 0, "leaves": 0, "invalid": False, "condition_ids": set()}
    result = _state_machine_condition_result(
        runtime, machine, condition, actor_id=actor_id, budget=budget,
    )
    return not budget["invalid"] and result is True


def state_machine_when_matches(
    runtime: "WorldRuntime",
    machine: dict[str, Any],
    expression: Any,
    *,
    actor_id: str | None,
) -> bool:
    """Evaluate a legacy AND list or a bounded v0.6 condition expression.

    Leaf reads use three-valued results: missing or type-invalid state is
    unknown, and ``not(unknown)`` remains unknown. Structural or budget errors
    invalidate the whole expression even when another ``any`` branch is true.
    Only a fully valid expression whose final value is true may transition.
    """
    if isinstance(expression, list):
        if len(expression) > STATE_MACHINE_CONDITION_LIMIT:
            return False
        budget = {"nodes": 0, "leaves": 0, "invalid": False, "condition_ids": set()}
        results = [
            _state_machine_condition_result(
                runtime, machine, condition, actor_id=actor_id, budget=budget,
            )
            for condition in expression
        ]
        return not budget["invalid"] and _all_condition_results(results) is True

    budget = {"nodes": 0, "leaves": 0, "invalid": False, "condition_ids": set()}
    result = _state_machine_expression_result(
        runtime, machine, expression, actor_id=actor_id,
        group_depth=0, budget=budget, active=set(),
    )
    return not budget["invalid"] and result is True


def _state_machine_expression_result(
    runtime: "WorldRuntime",
    machine: dict[str, Any],
    expression: Any,
    *,
    actor_id: str | None,
    group_depth: int,
    budget: dict[str, Any],
    active: set[int],
) -> bool | None:
    budget["nodes"] = int(budget["nodes"]) + 1
    if int(budget["nodes"]) > STATE_MACHINE_CONDITION_NODE_LIMIT:
        budget["invalid"] = True
        return None
    if not isinstance(expression, dict):
        budget["invalid"] = True
        return None
    expression_identity = id(expression)
    if expression_identity in active:
        budget["invalid"] = True
        return None

    condition_fields = {
        "condition_id", "subject", "namespace", "key", "operator", "value",
    }
    if set(expression) == condition_fields:
        return _state_machine_condition_result(
            runtime, machine, expression, actor_id=actor_id, budget=budget,
            count_node=False,
        )

    if set(expression) not in ({"all"}, {"any"}, {"not"}):
        budget["invalid"] = True
        return None
    next_depth = group_depth + 1
    if next_depth > STATE_MACHINE_CONDITION_GROUP_DEPTH_LIMIT:
        budget["invalid"] = True
        return None

    active.add(expression_identity)
    try:
        if "not" in expression:
            result = _state_machine_expression_result(
                runtime, machine, expression["not"], actor_id=actor_id,
                group_depth=next_depth, budget=budget, active=active,
            )
            return None if result is None else not result

        operator = "all" if "all" in expression else "any"
        children = expression[operator]
        if (
            not isinstance(children, list)
            or len(children) > STATE_MACHINE_CONDITION_LIMIT
            or (operator == "any" and not children)
        ):
            budget["invalid"] = True
            return None
        results = [
            _state_machine_expression_result(
                runtime, machine, child, actor_id=actor_id,
                group_depth=next_depth, budget=budget, active=active,
            )
            for child in children
        ]
        return (
            _all_condition_results(results)
            if operator == "all"
            else _any_condition_results(results)
        )
    finally:
        active.remove(expression_identity)


def _state_machine_condition_result(
    runtime: "WorldRuntime",
    machine: dict[str, Any],
    condition: Any,
    *,
    actor_id: str | None,
    budget: dict[str, Any],
    count_node: bool = True,
) -> bool | None:
    if count_node:
        budget["nodes"] = int(budget["nodes"]) + 1
    budget["leaves"] = int(budget["leaves"]) + 1
    if (
        int(budget["nodes"]) > STATE_MACHINE_CONDITION_NODE_LIMIT
        or int(budget["leaves"]) > STATE_MACHINE_CONDITION_LEAF_LIMIT
    ):
        budget["invalid"] = True
        return None
    condition_fields = {
        "condition_id", "subject", "namespace", "key", "operator", "value",
    }
    if not isinstance(condition, dict) or set(condition) != condition_fields:
        budget["invalid"] = True
        return None
    condition_id = condition.get("condition_id")
    subject = condition.get("subject")
    namespace = condition.get("namespace")
    key = condition.get("key")
    operator = condition.get("operator")
    if (
        not _valid_state_machine_id(condition_id)
        or subject not in STATE_MACHINE_CONDITION_SUBJECTS
        or namespace not in STATE_MACHINE_CONDITION_NAMESPACES
        or not _valid_state_machine_id(key)
        or operator not in STATE_MACHINE_CONDITION_OPERATORS
    ):
        budget["invalid"] = True
        return None
    if condition_id in budget["condition_ids"]:
        budget["invalid"] = True
        return None
    budget["condition_ids"].add(condition_id)

    owner_id = machine.get("owner_id") if subject == "owner" else actor_id
    if not isinstance(owner_id, str) or not owner_id:
        return None
    missing = object()
    actual = runtime.state.get(owner_id, namespace, key, missing)
    expected = condition.get("value")
    if not _finite_condition_scalar(expected):
        budget["invalid"] = True
        return None
    if (
        actual is missing
        or not _finite_condition_scalar(actual)
    ):
        return None
    if operator in {"equals", "not_equals"}:
        if not _condition_scalar_types_compatible(actual, expected):
            return None
        equal = _strict_scalar_equal(actual, expected)
        return equal if operator == "equals" else not equal
    if (
        isinstance(actual, bool)
        or isinstance(expected, bool)
        or not isinstance(actual, (int, float))
        or not isinstance(expected, (int, float))
    ):
        return None
    return {
        "less_than": actual < expected,
        "less_or_equal": actual <= expected,
        "greater_than": actual > expected,
        "greater_or_equal": actual >= expected,
    }[operator]


def _all_condition_results(results: list[bool | None]) -> bool | None:
    if any(result is False for result in results):
        return False
    if any(result is None for result in results):
        return None
    return True


def _any_condition_results(results: list[bool | None]) -> bool | None:
    if any(result is True for result in results):
        return True
    if any(result is None for result in results):
        return None
    return False


def _condition_scalar_types_compatible(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected)
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return True
    return type(actual) is type(expected)


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
    "STATE_MACHINE_CONDITION_GROUP_DEPTH_LIMIT",
    "STATE_MACHINE_CONDITION_LEAF_LIMIT",
    "STATE_MACHINE_CONDITION_LIMIT",
    "STATE_MACHINE_CONDITION_NAMESPACES",
    "STATE_MACHINE_CONDITION_OPERATORS",
    "STATE_MACHINE_CONDITION_SUBJECTS",
    "STATE_MACHINE_CONDITION_NODE_LIMIT",
    "STATE_MACHINE_DEFINITION_LIMIT",
    "STATE_MACHINE_EVENT_MATCH_LIMIT",
    "STATE_MACHINE_FORMAT",
    "STATE_MACHINE_FORMAT_V1",
    "STATE_MACHINE_FORMAT_V2",
    "STATE_MACHINE_FORMAT_V3",
    "STATE_MACHINE_FORMAT_V4",
    "STATE_MACHINE_FORMAT_V5",
    "STATE_MACHINE_HIERARCHY_DEPTH_LIMIT",
    "STATE_MACHINE_OWNER_SCOPES",
    "STATE_MACHINE_PRIORITY_LIMIT",
    "STATE_MACHINE_REQUIREMENT_LIMIT",
    "STATE_MACHINE_REWARD_CURRENCY_LIMIT",
    "STATE_MACHINE_SCHEMA_ID",
    "STATE_MACHINE_SCHEMA_ID_V1",
    "STATE_MACHINE_SCHEMA_ID_V2",
    "STATE_MACHINE_SCHEMA_ID_V3",
    "STATE_MACHINE_SCHEMA_ID_V4",
    "STATE_MACHINE_SCHEMA_ID_V5",
    "STATE_MACHINE_STATE_LIMIT",
    "STATE_MACHINE_TRANSITION_LIMIT",
    "STATE_MACHINE_TIMER_TICK_LIMIT",
    "STATE_MACHINE_REACTION_DEPTH_LIMIT",
    "STATE_MACHINE_TRIGGER_EVENT_FIELDS",
    "STATE_MACHINE_VISIBILITIES",
    "resolve_state_machine_actor",
    "validate_compiled_state_machines",
    "state_machine_condition_matches",
    "state_machine_when_matches",
    "state_machine_initial_child_by_state",
    "state_machine_is_active_leaf",
    "state_machine_lineage",
    "state_machine_parent_by_state",
    "state_machine_resolve_leaf",
    "state_machine_state_matches",
    "state_machine_state_path",
]
