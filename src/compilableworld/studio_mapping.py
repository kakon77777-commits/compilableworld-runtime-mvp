"""Validation for human-reviewed Studio World IR mapping decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .studio_world_ir import (
    validate_studio_event_match,
    validate_studio_priority,
    validate_studio_requirements,
    validate_studio_reward,
)
from .state_machine import STATE_MACHINE_TRIGGER_EVENT_FIELDS


STUDIO_MAPPING_FORMAT = "compilableworld.studio-mapping/v0.1"
_ALLOWED_RUNTIME_EVENTS = set(STATE_MACHINE_TRIGGER_EVENT_FIELDS)
_RUNTIME_EVENT_FIELDS = STATE_MACHINE_TRIGGER_EVENT_FIELDS
_GUARD_POLICIES = {"none", "state_conditions", "runtime_module", "external_review", "drop_with_approval"}


class StudioMappingError(ValueError):
    pass


def _issue(severity: str, code: str, message: str, path: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "path": path}


def load_studio_mapping(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioMappingError(f"invalid Studio mapping JSON: {path}") from exc
    if not isinstance(value, dict):
        raise StudioMappingError("Studio mapping root must be an object")
    return value


def suggest_studio_mapping(world_ir: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic, review-required mapping draft from World IR.

    Only explicit source locations and already-known Runtime EventIR types are
    carried forward.  Unknown values remain ``null`` so the draft cannot be
    mistaken for an executable mapping.
    """
    if not isinstance(world_ir, dict) or world_ir.get("format") != "compilableworld.studio-world-ir/v0.1":
        raise StudioMappingError("expected compilableworld.studio-world-ir/v0.1")
    plan = world_ir.get("migration_plan")
    if not isinstance(plan, dict):
        raise StudioMappingError("World IR does not contain migration_plan")
    entity_bindings = plan.get("entity_bindings")
    machine_bindings = plan.get("state_machine_bindings")
    if not isinstance(entity_bindings, list) or not isinstance(machine_bindings, list):
        raise StudioMappingError("World IR migration_plan bindings are invalid")

    entities: dict[str, dict[str, Any]] = {}
    for binding in entity_bindings:
        key = binding.get("binding_key")
        if not isinstance(key, str):
            continue
        entities[key] = {
            "room": binding.get("proposed_room"),
            "target_table": binding.get("target_table"),
        }

    state_machines: dict[str, dict[str, Any]] = {}
    for machine in machine_bindings:
        machine_id = machine.get("state_machine_id")
        if not isinstance(machine_id, str):
            continue
        transitions = machine.get("transitions") if isinstance(machine.get("transitions"), list) else []
        has_guards = any(isinstance(item, dict) and item.get("guards") for item in transitions)
        event_mappings: dict[str, dict[str, Any]] = {}
        for transition in transitions:
            if not isinstance(transition, dict) or not isinstance(transition.get("transition_id"), str):
                continue
            proposed_event = transition.get("proposed_runtime_event")
            event_mappings[transition["transition_id"]] = {
                "event_type": proposed_event,
                "event_match": dict(transition.get("event_match", {})),
                "requirements": list(transition.get("requirements", [])),
                "priority": transition.get("priority", 0),
                **({"reward": transition["reward"]} if transition.get("reward") is not None else {}),
            }
        state_machines[machine_id] = {
            "target": "quest" if str(machine_id).startswith("quest.") else None,
            "guard_policy": "external_review" if has_guards else "none",
            "event_mappings": event_mappings,
        }

    return {
        "format": STUDIO_MAPPING_FORMAT,
        "world_ir_format": world_ir["format"],
        "entities": entities,
        "state_machines": state_machines,
        "notes": "Deterministic suggestions only; review room, EventIR, and guard semantics before validation.",
    }


def write_mapping_template(world_ir: dict[str, Any], output: str | Path) -> Path:
    """Write a deterministic Studio mapping suggestion for human review."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(suggest_studio_mapping(world_ir), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def validate_studio_mapping(world_ir: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """Validate a mapping without mutating World IR or creating Runtime State."""
    if not isinstance(world_ir, dict) or world_ir.get("format") != "compilableworld.studio-world-ir/v0.1":
        raise StudioMappingError("expected compilableworld.studio-world-ir/v0.1")
    if not isinstance(mapping, dict):
        raise StudioMappingError("Studio mapping root must be an object")
    issues: list[dict[str, str]] = []
    diagnostics = world_ir.get("diagnostics")
    diagnostic_errors = diagnostics.get("errors", 0) if isinstance(diagnostics, dict) else 0
    if isinstance(diagnostic_errors, int) and not isinstance(diagnostic_errors, bool) and diagnostic_errors > 0:
        issues.append(_issue(
            "error",
            "world_ir_diagnostics",
            "World IR contains validation errors; resolve the source draft before mapping can be runtime-ready",
            "diagnostics",
        ))
    if mapping.get("format") != STUDIO_MAPPING_FORMAT:
        issues.append(_issue("error", "invalid_mapping_format", f"expected {STUDIO_MAPPING_FORMAT}", "format"))
    if mapping.get("world_ir_format") != world_ir["format"]:
        issues.append(_issue("error", "world_ir_format_mismatch", "mapping targets a different World IR format", "world_ir_format"))

    plan = world_ir.get("migration_plan") if isinstance(world_ir.get("migration_plan"), dict) else {}
    planned_entities = plan.get("entity_bindings") if isinstance(plan.get("entity_bindings"), list) else []
    planned_machines = plan.get("state_machine_bindings") if isinstance(plan.get("state_machine_bindings"), list) else []
    entities = mapping.get("entities")
    machines = mapping.get("state_machines")
    if not isinstance(entities, dict):
        issues.append(_issue("error", "missing_entity_mappings", "entities must be an object", "entities"))
        entities = {}
    if not isinstance(machines, dict):
        issues.append(_issue("error", "missing_state_machine_mappings", "state_machines must be an object", "state_machines"))
        machines = {}

    expected_entity_keys = {item.get("binding_key") for item in planned_entities}
    for key in sorted(set(entities) - expected_entity_keys):
        issues.append(_issue("error", "unknown_entity_mapping", "mapping has no matching World IR entity", f"entities.{key}"))
    for item in planned_entities:
        key = item.get("binding_key")
        binding = entities.get(key)
        path = f"entities.{key}"
        if not isinstance(binding, dict):
            issues.append(_issue("error", "missing_entity_mapping", "entity room mapping is required", path))
            continue
        room = binding.get("room")
        if not isinstance(room, str) or not room.strip():
            issues.append(_issue("error", "missing_entity_room", "entity mapping must declare a Runtime room", f"{path}.room"))
        target_table = binding.get("target_table", item.get("target_table"))
        if target_table not in {"entities", "items"}:
            issues.append(_issue("error", "invalid_entity_target", "target_table must be entities or items", f"{path}.target_table"))

    expected_machine_ids = {item.get("state_machine_id") for item in planned_machines}
    for key in sorted(set(machines) - expected_machine_ids):
        issues.append(_issue("error", "unknown_state_machine_mapping", "mapping has no matching World IR state machine", f"state_machines.{key}"))
    for machine in planned_machines:
        machine_id = machine.get("state_machine_id")
        binding = machines.get(machine_id)
        path = f"state_machines.{machine_id}"
        if not isinstance(binding, dict):
            issues.append(_issue("error", "missing_state_machine_mapping", "state machine mapping is required", path))
            continue
        target = binding.get("target")
        if target not in {None, "quest"}:
            issues.append(_issue("error", "invalid_mapping_target", "target must be quest or null", f"{path}.target"))
        if target != "quest":
            issues.append(_issue("warning", "unsupported_mapping_target", "only target=quest has a Runtime compiler path in v0.1", f"{path}.target"))
        guard_policy = binding.get("guard_policy", "none")
        if guard_policy not in _GUARD_POLICIES:
            issues.append(_issue("error", "invalid_guard_policy", f"guard_policy must be one of {sorted(_GUARD_POLICIES)}", f"{path}.guard_policy"))
        if guard_policy != "none":
            issues.append(_issue("warning", "non_runtime_guard_policy", f"{guard_policy} does not produce executable Runtime guard semantics", f"{path}.guard_policy"))
        transition_mappings = binding.get("event_mappings")
        if not isinstance(transition_mappings, dict):
            issues.append(_issue("error", "missing_transition_mappings", "event_mappings must be an object", f"{path}.event_mappings"))
            transition_mappings = {}
        expected_transition_ids = {
            transition.get("transition_id")
            for transition in machine.get("transitions", [])
            if isinstance(transition, dict)
        }
        for transition_id in sorted(set(transition_mappings) - expected_transition_ids):
            issues.append(_issue("error", "unknown_transition_mapping", "mapping has no matching World IR transition", f"{path}.event_mappings.{transition_id}"))
        for transition in machine.get("transitions", []):
            transition_id = transition.get("transition_id")
            transition_path = f"{path}.event_mappings.{transition_id}"
            event_mapping = transition_mappings.get(transition_id)
            if not isinstance(event_mapping, dict):
                issues.append(_issue("error", "missing_transition_mapping", "transition event mapping is required", transition_path))
                continue
            event_type = event_mapping.get("event_type")
            if event_type not in _ALLOWED_RUNTIME_EVENTS:
                issues.append(_issue("error", "invalid_runtime_event", f"event_type must be one of {sorted(_ALLOWED_RUNTIME_EVENTS)}", f"{transition_path}.event_type"))
            source_event_match = transition.get("event_match", {})
            normalized_source_match = validate_studio_event_match(source_event_match, f"{transition_path}.source_event_match", issues)
            mapped_event_match = event_mapping.get("event_match", source_event_match)
            normalized_mapped_match = validate_studio_event_match(mapped_event_match, f"{transition_path}.event_match", issues)
            allowed_fields = _RUNTIME_EVENT_FIELDS.get(event_type)
            if allowed_fields is not None:
                unknown_match = set(normalized_mapped_match) - allowed_fields
                if unknown_match:
                    issues.append(_issue("error", "invalid_event_match_field", f"event_match fields are not allowed for {event_type}: {sorted(unknown_match)}", f"{transition_path}.event_match"))
            if normalized_mapped_match != normalized_source_match:
                issues.append(_issue(
                    "error",
                    "event_match_mismatch",
                    "mapping event_match must exactly preserve the World IR event_match",
                    f"{transition_path}.event_match",
                ))
            source_requirements = transition.get("requirements", [])
            normalized_source = validate_studio_requirements(source_requirements, f"{transition_path}.source_requirements", issues)
            mapped_requirements = event_mapping.get("requirements", source_requirements)
            normalized_mapped = validate_studio_requirements(mapped_requirements, f"{transition_path}.requirements", issues)
            if normalized_mapped != normalized_source:
                issues.append(_issue(
                    "error",
                    "requirements_mismatch",
                    "mapping requirements must exactly preserve the World IR requirements",
                    f"{transition_path}.requirements",
                ))
            source_priority = transition.get("priority", 0)
            normalized_source_priority = validate_studio_priority(source_priority, f"{transition_path}.source_priority", issues)
            mapped_priority = event_mapping.get("priority", source_priority)
            normalized_mapped_priority = validate_studio_priority(mapped_priority, f"{transition_path}.priority", issues)
            if normalized_mapped_priority != normalized_source_priority:
                issues.append(_issue("error", "priority_mismatch", "mapping priority must exactly preserve the World IR priority", f"{transition_path}.priority"))
            source_reward = transition.get("reward")
            normalized_source_reward = validate_studio_reward(source_reward, transition.get("to"), f"{transition_path}.source_reward", issues)
            mapped_reward = event_mapping.get("reward", source_reward)
            normalized_mapped_reward = validate_studio_reward(mapped_reward, transition.get("to"), f"{transition_path}.reward", issues)
            if normalized_mapped_reward != normalized_source_reward:
                issues.append(_issue("error", "reward_mismatch", "mapping reward must exactly preserve the World IR reward", f"{transition_path}.reward"))

    errors = sum(issue["severity"] == "error" for issue in issues)
    warnings = len(issues) - errors
    mapping_complete = errors == 0
    runtime_ready = mapping_complete and not any(issue["code"] in {"non_runtime_guard_policy", "unsupported_mapping_target"} for issue in issues)
    return {
        "format": "compilableworld.studio-mapping-report/v0.1",
        "mapping_format": mapping.get("format"),
        "world_ir_format": world_ir["format"],
        "mapping_complete": mapping_complete,
        "runtime_ready": runtime_ready,
        "diagnostics": {"errors": errors, "warnings": warnings, "issues": issues},
        "summary": {
            "entity_bindings": len(planned_entities),
            "state_machine_bindings": len(planned_machines),
        },
    }


__all__ = [
    "STUDIO_MAPPING_FORMAT", "StudioMappingError", "load_studio_mapping",
    "suggest_studio_mapping", "validate_studio_event_match", "validate_studio_mapping",
    "validate_studio_priority", "validate_studio_requirements", "validate_studio_reward",
    "write_mapping_template",
]
