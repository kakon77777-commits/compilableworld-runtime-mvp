"""Headless Studio projections for CompilableWorld packages.

This is the small semantic bridge between the Runtime Package and a future
EveGlyph / CompilableWorld Studio surface.  It is deliberately read-only:
the package and Runtime State remain the sources of truth, while this module
returns FMS/SMS/TMS/DMS-friendly projections for humans, agents, and tools.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from copy import deepcopy
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from .functions import FunctionRegistryError
from .schema_registry import SCHEMA_CATALOG_FORMAT, schema_catalog as authoring_schema_catalog

if TYPE_CHECKING:
    from .kernel import WorldRuntime


STUDIO_OVERVIEW_FORMAT = "compilableworld.studio-overview/v0.1"
STUDIO_FUNCTION_CATALOG_FORMAT = "compilableworld.function-catalog/v0.1"
STUDIO_FUNCTION_PREVIEW_FORMAT = "compilableworld.function-preview/v0.1"
STUDIO_SEMANTIC_RECORDS_FORMAT = "compilableworld.studio-semantic-records/v0.1"
STUDIO_SCHEMA_CATALOG_FORMAT = SCHEMA_CATALOG_FORMAT


def _issue(severity: str, code: str, message: str, path: str | None = None) -> dict[str, str]:
    result = {"severity": severity, "code": code, "message": message}
    if path:
        result["path"] = path
    return result


def _ordered_unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _quest_overview(quest: Any, index: int) -> dict[str, Any]:
    path = f"quests[{index}]"
    if not isinstance(quest, dict):
        return {
            "quest_id": f"(invalid-{index})",
            "title": "",
            "initial_state": None,
            "states": [],
            "reachable_states": [],
            "terminal_states": [],
            "transition_count": 0,
            "issues": [_issue("error", "invalid_quest", "任務必須是物件", path)],
        }

    transitions = quest.get("transitions") if isinstance(quest.get("transitions"), list) else []
    states = _ordered_unique([
        quest.get("initial_state"),
        *(item.get("from") for item in transitions if isinstance(item, dict)),
        *(item.get("to") for item in transitions if isinstance(item, dict)),
    ])
    initial = quest.get("initial_state") if isinstance(quest.get("initial_state"), str) else None
    issues: list[dict[str, str]] = []
    if initial is None:
        issues.append(_issue("error", "missing_initial_state", "任務缺少 initial_state", f"{path}.initial_state"))

    adjacency: dict[str, set[str]] = defaultdict(set)
    dispatches: dict[tuple[str, str, int], int] = {}
    transition_records: list[dict[str, Any]] = []
    for transition_index, transition in enumerate(transitions):
        transition_path = f"{path}.transitions[{transition_index}]"
        if not isinstance(transition, dict):
            issues.append(_issue("error", "invalid_transition", "transition 必須是物件", transition_path))
            continue
        from_state = transition.get("from")
        to_state = transition.get("to")
        event = transition.get("on")
        priority = transition.get("priority", 0)
        if not isinstance(from_state, str) or not isinstance(to_state, str):
            issues.append(_issue("error", "invalid_transition_state", "transition 缺少有效 from/to", transition_path))
            continue
        adjacency[from_state].add(to_state)
        try:
            priority_value = int(priority)
        except (TypeError, ValueError):
            priority_value = 0
            issues.append(_issue("error", "invalid_transition_priority", "priority 必須是整數", f"{transition_path}.priority"))
        if isinstance(event, str):
            dispatch = (from_state, event, priority_value)
            if dispatch in dispatches:
                issues.append(_issue(
                    "error", "conflicting_transition",
                    f"同一 from/on/priority 有多條 transition: {dispatch}", transition_path,
                ))
            else:
                dispatches[dispatch] = transition_index
        transition_records.append({
            "transition_id": transition.get("transition_id", f"transition[{transition_index}]"),
            "from": from_state,
            "to": to_state,
            "on": event,
            "priority": priority_value,
        })

    if initial is not None and initial not in states:
        issues.append(_issue("error", "initial_state_undefined", f"初始狀態不存在: {initial}", f"{path}.initial_state"))

    reachable: set[str] = set()
    if initial is not None and initial in states:
        reachable.add(initial)
        queue = deque([initial])
        while queue:
            current = queue.popleft()
            for target in adjacency.get(current, set()):
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
    for state in states:
        if state not in reachable:
            issues.append(_issue(
                "warning", "unreachable_state", f"不可達狀態: {state}", f"{path}.states.{state}",
            ))

    terminal = sorted(state for state in states if not adjacency.get(state))
    return {
        "quest_id": quest.get("quest_id", f"(unnamed-{index})"),
        "title": quest.get("title", ""),
        "initial_state": initial,
        "states": states,
        "reachable_states": [state for state in states if state in reachable],
        "terminal_states": terminal,
        "transition_count": len(transition_records),
        "transitions": transition_records,
        "issues": issues,
    }


def _scoped_state_machine_overview(machine: Any, index: int) -> dict[str, Any]:
    """Project compiled StateIR without creating a Runtime mutation path."""
    path = f"state_machines[{index}]"
    if not isinstance(machine, dict):
        return {
            "state_machine_id": f"(invalid-{index})",
            "owner_scope": None,
            "owner_id": None,
            "states": [],
            "transitions": [],
            "issues": [_issue("error", "invalid_state_machine", "StateIR 必須是物件", path)],
        }
    required = {
        "state_machine_id", "owner_scope", "owner_id", "states",
        "initial_state", "visibility", "authority", "transitions",
    }
    issues: list[dict[str, str]] = []
    missing = required - set(machine)
    if missing:
        issues.append(_issue(
            "error", "invalid_state_machine",
            f"StateIR 缺少欄位: {sorted(missing)}", path,
        ))
    transitions = machine.get("transitions") if isinstance(machine.get("transitions"), list) else []
    return {
        "state_machine_id": machine.get("state_machine_id", f"(unnamed-{index})"),
        "title": machine.get("title", ""),
        "owner_scope": machine.get("owner_scope"),
        "owner_id": machine.get("owner_id"),
        "states": list(machine.get("states", [])) if isinstance(machine.get("states"), list) else [],
        "initial_state": machine.get("initial_state"),
        "persistence": machine.get("persistence"),
        "visibility": machine.get("visibility"),
        "authority": machine.get("authority"),
        "transition_count": len(transitions),
        "transitions": [
            {
                "transition_id": transition.get("transition_id"),
                "from": transition.get("from"),
                "on": transition.get("on"),
                "to": transition.get("to"),
                "event_match": dict(transition.get("event_match", {})),
                "priority": transition.get("priority", 0),
            }
            for transition in transitions if isinstance(transition, dict)
        ],
        "issues": issues,
    }


def _action_behavior_overview(behavior: Any, index: int) -> dict[str, Any]:
    """Project compiled Action-scope authoring without exposing Scheduler writes."""
    if not isinstance(behavior, dict):
        return {
            "behavior_id": f"(invalid-{index})",
            "issues": [_issue(
                "error", "invalid_action_behavior", "Action behavior 必須是物件",
                f"action_behaviors[{index}]",
            )],
        }
    return {
        "behavior_id": behavior.get("behavior_id", f"(unnamed-{index})"),
        "title": behavior.get("title", ""),
        "verb": behavior.get("verb"),
        "duration_ticks": behavior.get("duration_ticks"),
        "execution_model": behavior.get("execution_model"),
        "entry_phase_id": behavior.get("entry_phase_id"),
        "terminal_phase_id": behavior.get("terminal_phase_id"),
        "phases": [
            {
                "phase_id": phase.get("phase_id"),
                "title": phase.get("title", ""),
                "duration_ticks": phase.get("duration_ticks"),
                "when": [dict(condition) for condition in phase.get("when", []) if isinstance(condition, dict)],
                "retry": dict(phase["retry"])
                if isinstance(phase.get("retry"), dict) else None,
                "child_action": deepcopy(phase.get("child_action")),
                "branches": deepcopy(phase.get("branches", [])),
            }
            for phase in behavior.get("phases", []) if isinstance(phase, dict)
        ],
        "completion_module": behavior.get("completion_module"),
        "concurrency": behavior.get("concurrency"),
        "interrupt_on": list(behavior.get("interrupt_on", [])),
        "issues": [],
    }


def _function_records(package: dict[str, Any]) -> list[dict[str, Any]]:
    entries = package.get("functions", {}).get("functions", []) if isinstance(package.get("functions"), dict) else []
    records = []
    for function in entries:
        if not isinstance(function, dict):
            continue
        records.append({
            "function_id": function.get("function_id"),
            "version": function.get("version"),
            "purity": function.get("purity"),
            "inputs": dict(function.get("inputs") or {}),
            "output": function.get("output"),
            "expression": function.get("expression"),
        })
    return sorted(records, key=lambda item: str(item.get("function_id", "")))


def _semantic_records_overview(package: dict[str, Any]) -> dict[str, Any]:
    """Project package semantic metadata without exposing a mutation path."""
    studio = package.get("studio") if isinstance(package.get("studio"), dict) else {}
    metadata_only = studio.get("semantic_records_are_metadata_only") is True
    records = studio.get("semantic_records")
    return {
        "format": studio.get("semantic_records_format", STUDIO_SEMANTIC_RECORDS_FORMAT),
        "metadata_only": metadata_only,
        "state_machines": deepcopy(records) if metadata_only and isinstance(records, dict) else {},
    }


def package_overview(package: dict[str, Any]) -> dict[str, Any]:
    """Project a Runtime Package into a read-only Studio overview."""
    if not isinstance(package, dict):
        raise ValueError("Runtime Package 必須是物件")

    manifest = package.get("manifest") if isinstance(package.get("manifest"), dict) else {}
    world = package.get("world") if isinstance(package.get("world"), dict) else {}
    entities = [entity for entity in package.get("entities", []) if isinstance(entity, dict)]
    initial_state = [cell for cell in package.get("initial_state", []) if isinstance(cell, dict)]
    modules = [module for module in manifest.get("modules", []) if isinstance(module, str)]
    function_records = _function_records(package)
    quests = [_quest_overview(quest, index) for index, quest in enumerate(package.get("quests", []))]
    state_machines = [
        _scoped_state_machine_overview(machine, index)
        for index, machine in enumerate(package.get("state_machines", []))
    ]
    action_behaviors = [
        _action_behavior_overview(behavior, index)
        for index, behavior in enumerate(package.get("action_behaviors", []))
    ]
    issues = [
        issue
        for record in [*quests, *state_machines, *action_behaviors]
        for issue in record["issues"]
    ]

    entity_type_counts = Counter(str(entity.get("entity_type", "unknown")) for entity in entities)
    state_namespace_counts = Counter(str(cell.get("namespace", "unknown")) for cell in initial_state)
    event_types = {
        transition.get("on")
        for quest in quests
        for transition in quest.get("transitions", [])
        if isinstance(transition.get("on"), str)
    }
    event_types.update(
        transition.get("on")
        for machine in state_machines
        for transition in machine.get("transitions", [])
        if isinstance(transition.get("on"), str)
    )
    if action_behaviors:
        event_types.update({
            "action.scheduled", "action.started", "action.completed",
            "action.progressed", "action.retry_scheduled", "action.cancelled",
            "action.branch_selected",
            "action.child_started", "action.child_completed", "action.child_failed",
            "action.interrupted", "action.failed",
        })
        event_types.update(
            event_type
            for behavior in action_behaviors
            for event_type in behavior.get("interrupt_on", [])
        )
    if package.get("dialogues", {}).get("dialogues"):
        event_types.add("dialogue.responded")

    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    world_id = manifest.get("world_id", world.get("world_id", ""))
    return {
        "format": STUDIO_OVERVIEW_FORMAT,
        "schema_contracts": dict(package.get("schema_contracts", {})),
        "planes": {
            "fms": {
                "world_id": world_id,
                "world_version": manifest.get("world_version"),
                "schema_version": manifest.get("schema_version"),
                "namespace": manifest.get("namespace"),
                "runtime_targets": manifest.get("targets", []),
            },
            "sms": {
                "runtime_package_format": package.get("format"),
                "snapshot_format": "compilableworld.snapshot/v0.6",
            },
            "tms": {"declared_modules": sorted(modules)},
            "dms": {"static_issue_count": len(issues)},
        },
        "entities": {
            "total": len(entities),
            "by_type": dict(sorted(entity_type_counts.items())),
            "records": [
                {"id": entity.get("entity_id"), "type": entity.get("entity_type"), "name": entity.get("name")}
                for entity in entities
            ],
        },
        "state": {
            "initial_cell_count": len(initial_state),
            "by_namespace": dict(sorted(state_namespace_counts.items())),
        },
        "events": {"declared": sorted(event_types)},
        "functions": {
            "count": len(function_records),
            "ids": [function.get("function_id", "") for function in function_records],
            "pure": all(function.get("purity") == "pure" for function in function_records),
            "records": function_records,
        },
        "quests": quests,
        "action_behaviors": action_behaviors,
        "state_machines": state_machines,
        "semantic_records": _semantic_records_overview(package),
        "player_templates": {
            "count": len(package.get("player_templates", []))
            if isinstance(package.get("player_templates"), list) else 0,
        },
        "sources": {"checksum_count": len(package.get("source_checksums", {}))},
        "diagnostics": {
            "errors": error_count,
            "warnings": warning_count,
            "issues": issues,
        },
    }


def function_catalog(package: dict[str, Any]) -> dict[str, Any]:
    """Return editor-facing FunctionIR metadata without exposing mutation APIs."""
    records = _function_records(package)
    return {
        "format": STUDIO_FUNCTION_CATALOG_FORMAT,
        "read_only": True,
        "functions": records,
    }


def schema_catalog() -> dict[str, Any]:
    """Return read-only authoring/package schema metadata for Studio."""
    return authoring_schema_catalog()


def function_preview(runtime: "WorldRuntime", function_id: str, values: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one validated FunctionIR without changing Runtime State."""
    if not isinstance(function_id, str) or not function_id.strip():
        raise ValueError("function_id must be a non-empty string")
    if not isinstance(values, dict):
        raise ValueError("inputs must be an object")
    record = next(
        (item for item in _function_records(runtime.package) if item.get("function_id") == function_id),
        None,
    )
    if record is None:
        raise ValueError(f"unknown FunctionIR: {function_id}")
    try:
        result = runtime.functions.evaluate(function_id, dict(values))
    except FunctionRegistryError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "format": STUDIO_FUNCTION_PREVIEW_FORMAT,
        "read_only": True,
        "function": record,
        "inputs": dict(values),
        "result": result,
    }


def runtime_overview(runtime: "WorldRuntime") -> dict[str, Any]:
    """Add DMS/runtime trace data to :func:`package_overview`."""
    overview = package_overview(runtime.package)
    for machine in overview["state_machines"]:
        owner_id = machine.get("owner_id")
        machine_id = machine.get("state_machine_id")
        if isinstance(owner_id, str) and isinstance(machine_id, str):
            machine["current_state"] = runtime.state.get(
                owner_id, "fsm", machine_id, machine.get("initial_state"),
            )
            machine["state_version"] = runtime.state.version(owner_id, "fsm", machine_id)
    overview["pending_actions"] = runtime.pending_actions()
    overview["runtime"] = {
        "diagnostics": runtime.diagnostics(),
        "modules": {
            module_id: asdict(module.contract)
            for module_id, module in sorted(runtime.modules.items())
        },
        "trace_tail": [event.to_dict() for event in runtime.event_log.events[-20:]],
    }
    return overview


__all__ = [
    "STUDIO_FUNCTION_CATALOG_FORMAT", "STUDIO_FUNCTION_PREVIEW_FORMAT",
    "STUDIO_OVERVIEW_FORMAT", "STUDIO_SCHEMA_CATALOG_FORMAT", "STUDIO_SEMANTIC_RECORDS_FORMAT",
    "function_catalog",
    "function_preview", "package_overview", "runtime_overview", "schema_catalog",
]
