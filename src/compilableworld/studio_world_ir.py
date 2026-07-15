"""Dependency-free EveGlyph YAML -> shared Studio World IR migration.

EveGlyph intentionally keeps YAML as an editor-facing format.  This module
accepts the small, documented YAML subset used by its ``entity``,
``entity_list`` and ``state_machine`` documents and emits a stable JSON World
IR artifact.  It does not guess missing Runtime facts such as room placement,
exit topology, or QuestModule event semantics.
"""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STUDIO_WORLD_IR_FORMAT = "compilableworld.studio-world-ir/v0.1"
EVEGLYPH_YAML_FORMAT = "eveglyph-world-yaml/v0.1"
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_RUNTIME_EVENT_TYPES = {"inventory.item_given", "movement.actor_moved", "dialogue.responded"}
_SEMANTIC_KEYS = ("variables", "events", "instructions", "responses")
_RANDOM_KINDS = {"boolean", "integer", "number", "choice"}
_RANDOM_CHOICE_LIMIT = 32
_RANDOM_RANGE_LIMIT = 1_000_000


class StudioWorldIRError(ValueError):
    """Raised when an input cannot be represented by the supported YAML subset."""


@dataclass(frozen=True)
class _YamlLine:
    indent: int
    text: str
    number: int


def _issue(severity: str, code: str, message: str, path: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "path": path}


def _find_colon(text: str) -> int:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if quote:
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == ":":
            return index
    return -1


def _prepare_lines(text: str) -> list[_YamlLine]:
    lines: list[_YamlLine] = []
    for number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw:
            raise StudioWorldIRError(f"tabs are not supported in EveGlyph YAML (line {number})")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append(_YamlLine(indent, stripped, number))
    return lines


def _split_mapping(text: str, line: _YamlLine) -> tuple[str, str]:
    index = _find_colon(text)
    if index <= 0:
        raise StudioWorldIRError(f"expected mapping entry at line {line.number}: {text}")
    key = text[:index].strip()
    if not _KEY_RE.match(key):
        raise StudioWorldIRError(f"invalid mapping key at line {line.number}: {key}")
    return key, text[index + 1 :].strip()


def _split_inline_list(raw: str, line: _YamlLine) -> list[Any]:
    inner = raw[1:-1].strip()
    if not inner:
        return []
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(inner):
        if quote:
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
        elif char in {'"', "'"}:
            quote = char
        elif char == ",":
            parts.append(inner[start:index].strip())
            start = index + 1
    parts.append(inner[start:].strip())
    return [_scalar(part, line) for part in parts]


def _scalar(raw: str, line: _YamlLine) -> Any:
    if not raw:
        return None
    if raw in {"|", ">", "|-", ">-", "|+", ">+"}:
        raise StudioWorldIRError(f"block scalar is not supported at line {line.number}")
    if raw.startswith(("&", "*", "!")):
        raise StudioWorldIRError(f"YAML anchors/tags are not supported at line {line.number}")
    if raw.startswith("[") and raw.endswith("]"):
        return _split_inline_list(raw, line)
    if raw.startswith("{") and raw.endswith("}"):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StudioWorldIRError(f"invalid inline object at line {line.number}") from exc
        if not isinstance(value, dict):
            raise StudioWorldIRError(f"inline object expected at line {line.number}")
        return value
    if raw.startswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StudioWorldIRError(f"invalid double-quoted scalar at line {line.number}") from exc
    if raw.startswith("'") and raw.endswith("'"):
        try:
            return ast.literal_eval(raw)
        except (SyntaxError, ValueError) as exc:
            raise StudioWorldIRError(f"invalid single-quoted scalar at line {line.number}") from exc
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"[-+]?\d+", raw):
        return int(raw)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\.\d+)(?:[eE][-+]?\d+)?", raw):
        return float(raw)
    return raw


def _parse_block(lines: list[_YamlLine], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines) or lines[index].indent != indent:
        raise StudioWorldIRError(f"invalid indentation near line {lines[index - 1].number if index else 1}")
    if lines[index].text.startswith("-"):
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_map(lines: list[_YamlLine], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines) and lines[index].indent == indent and not lines[index].text.startswith("-"):
        line = lines[index]
        key, raw = _split_mapping(line.text, line)
        if key in result:
            raise StudioWorldIRError(f"duplicate mapping key at line {line.number}: {key}")
        index += 1
        if raw:
            result[key] = _scalar(raw, line)
            continue
        if index < len(lines) and lines[index].indent > indent:
            result[key], index = _parse_block(lines, index, lines[index].indent)
        else:
            result[key] = None
    return result, index


def _parse_list(lines: list[_YamlLine], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines) and lines[index].indent == indent and lines[index].text.startswith("-"):
        line = lines[index]
        body = line.text[1:].strip()
        index += 1
        if not body:
            if index >= len(lines) or lines[index].indent <= indent:
                result.append(None)
            else:
                value, index = _parse_block(lines, index, lines[index].indent)
                result.append(value)
            continue
        colon = _find_colon(body)
        if colon <= 0 or not _KEY_RE.match(body[:colon].strip()):
            result.append(_scalar(body, line))
            if index < len(lines) and lines[index].indent > indent:
                raise StudioWorldIRError(f"nested value after scalar list item at line {lines[index].number}")
            continue

        key = body[:colon].strip()
        raw = body[colon + 1 :].strip()
        item: dict[str, Any] = {}
        if raw:
            item[key] = _scalar(raw, line)
        elif index < len(lines) and lines[index].indent > indent:
            item[key], index = _parse_block(lines, index, lines[index].indent)
        else:
            item[key] = None

        if index < len(lines) and lines[index].indent > indent:
            continuation_indent = lines[index].indent
            continuation, index = _parse_map(lines, index, continuation_indent)
            overlap = set(item) & set(continuation)
            if overlap:
                raise StudioWorldIRError(f"duplicate list-item keys: {sorted(overlap)}")
            item.update(continuation)
        result.append(item)
    return result, index


def parse_eveglyph_yaml(text: str) -> dict[str, Any]:
    """Parse the documented EveGlyph YAML subset without third-party deps."""
    lines = _prepare_lines(text)
    if not lines:
        raise StudioWorldIRError("empty EveGlyph YAML document")
    document, index = _parse_block(lines, 0, lines[0].indent)
    if index != len(lines):
        raise StudioWorldIRError(f"unexpected YAML content near line {lines[index].number}")
    if not isinstance(document, dict):
        raise StudioWorldIRError("EveGlyph YAML root must be a mapping")
    return document


def _ordered_unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _entity_record(raw: Any, source_path: str, index: int, issues: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        issues.append(_issue("error", "invalid_entity", "entity must be a mapping", f"{source_path}.entities[{index}]"))
        raw = {}
    entity_id = raw.get("id")
    entity_type = raw.get("type")
    if not entity_id:
        issues.append(_issue("error", "missing_id", "entity is missing id", f"{source_path}.entities[{index}].id"))
        entity_id = f"(unnamed-{index})"
    elif not isinstance(entity_id, str) or not _ID_RE.match(entity_id):
        issues.append(_issue("error", "invalid_id", "entity id is not a valid ID", f"{source_path}.entities[{index}].id"))
    if not entity_type:
        issues.append(_issue("warning", "missing_type", "entity is missing type", f"{source_path}.entities[{index}].type"))
    metadata = {key: value for key, value in raw.items() if key not in {"id", "type", "name"}}
    return {
        "entity_id": entity_id,
        "entity_type": str(entity_type).lower() if entity_type is not None else None,
        "name": raw.get("name", ""),
        "metadata": metadata,
        "source_document": source_path,
    }


def _normalize_entity_document(doc: dict[str, Any], source_path: str, issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    if doc.get("kind") == "entity":
        return [_entity_record(doc, source_path, 0, issues)]
    entities = doc.get("entities")
    if not isinstance(entities, list) or not entities:
        issues.append(_issue("warning", "empty_entity_list", "entity_list has no entities", f"{source_path}.entities"))
        return []
    records = [_entity_record(entity, source_path, index, issues) for index, entity in enumerate(entities)]
    seen: dict[str, int] = {}
    for index, record in enumerate(records):
        entity_id = record["entity_id"]
        if entity_id in seen:
            issues.append(_issue("error", "duplicate_id", f"duplicate entity id: {entity_id}", f"{source_path}.entities[{index}].id"))
        else:
            seen[entity_id] = index
    return records


def _validate_random_spec(spec: Any, path: str, issues: list[dict[str, str]]) -> None:
    """Validate the non-executable random contract carried by a variable."""
    if spec is None:
        return
    if not isinstance(spec, dict):
        issues.append(_issue("error", "invalid_random_spec", "variable random must be a mapping", path))
        return
    kind = spec.get("kind")
    if kind not in _RANDOM_KINDS:
        issues.append(_issue("error", "invalid_random_kind", "random kind is not supported", f"{path}.kind"))
        return
    if kind == "boolean":
        return
    if kind == "choice":
        values = spec.get("values")
        if not isinstance(values, list) or not values:
            issues.append(_issue("error", "invalid_random_values", "choice random needs a non-empty values list", f"{path}.values"))
            return
        if len(values) > _RANDOM_CHOICE_LIMIT:
            issues.append(_issue("error", "random_choice_limit_exceeded", f"choice random exceeds {_RANDOM_CHOICE_LIMIT} values", f"{path}.values"))
        for index, value in enumerate(values):
            if not isinstance(value, (str, int, float, bool)) or (isinstance(value, float) and not math.isfinite(value)):
                issues.append(_issue("error", "invalid_random_value", "random choices must be scalar values", f"{path}.values[{index}]"))
        return
    minimum, maximum = spec.get("min"), spec.get("max")
    if not isinstance(minimum, (int, float)) or isinstance(minimum, bool) or not math.isfinite(minimum):
        issues.append(_issue("error", "invalid_random_bounds", "random min must be a finite number", f"{path}.min"))
        return
    if not isinstance(maximum, (int, float)) or isinstance(maximum, bool) or not math.isfinite(maximum):
        issues.append(_issue("error", "invalid_random_bounds", "random max must be a finite number", f"{path}.max"))
        return
    if maximum < minimum:
        issues.append(_issue("error", "reversed_random_bounds", "random max cannot be smaller than min", path))
    if maximum - minimum > _RANDOM_RANGE_LIMIT:
        issues.append(_issue("error", "random_range_limit_exceeded", f"random range exceeds {_RANDOM_RANGE_LIMIT}", path))
    if kind == "integer" and (not isinstance(minimum, int) or not isinstance(maximum, int)):
        issues.append(_issue("error", "invalid_integer_bounds", "integer random bounds must be integers", path))


def _normalize_semantic_records(doc: dict[str, Any], source_path: str, issues: list[dict[str, str]]) -> dict[str, list[dict[str, Any]]]:
    """Preserve Studio semantic records without treating them as executable rules."""
    normalized: dict[str, list[dict[str, Any]]] = {}
    for key in _SEMANTIC_KEYS:
        raw_records = doc.get(key, [])
        if raw_records is None:
            raw_records = []
        if not isinstance(raw_records, list):
            issues.append(_issue("error", "invalid_semantic_records", f"{key} must be a list", f"{source_path}.{key}"))
            normalized[key] = []
            continue
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, record in enumerate(raw_records):
            path = f"{source_path}.{key}[{index}]"
            if not isinstance(record, dict):
                issues.append(_issue("error", "invalid_semantic_record", "semantic record must be a mapping", path))
                continue
            record_id = record.get("id") or record.get("name")
            if not isinstance(record_id, str) or not record_id.strip():
                issues.append(_issue("error", "missing_semantic_id", "semantic record needs id or name", f"{path}.id"))
            elif record_id in seen:
                issues.append(_issue("error", "duplicate_semantic_id", f"duplicate semantic id: {record_id}", f"{path}.id"))
            else:
                seen.add(record_id)
            if key == "variables":
                _validate_random_spec(record.get("random"), f"{path}.random", issues)
            records.append(dict(record))
        normalized[key] = records
    return normalized


def _normalize_state_machine(doc: dict[str, Any], source_path: str, issues: list[dict[str, str]]) -> dict[str, Any]:
    machine_id = doc.get("id") or Path(source_path).stem
    initial = doc.get("initial")
    transitions = doc.get("transitions") if isinstance(doc.get("transitions"), list) else []
    states = _ordered_unique([
        *(doc.get("states") if isinstance(doc.get("states"), list) else []),
        initial,
        *(transition.get("from") for transition in transitions if isinstance(transition, dict)),
        *(transition.get("to") for transition in transitions if isinstance(transition, dict)),
    ])
    if not initial:
        issues.append(_issue("error", "no_initial_state", "state machine has no initial state", f"{source_path}.initial"))
    elif initial not in states:
        issues.append(_issue("error", "initial_state_undefined", f"initial state is undefined: {initial}", f"{source_path}.initial"))

    normalized_transitions: list[dict[str, Any]] = []
    dispatches: dict[tuple[Any, Any], int] = {}
    adjacency: dict[str, set[str]] = {}
    for index, transition in enumerate(transitions):
        path = f"{source_path}.transitions[{index}]"
        if not isinstance(transition, dict):
            issues.append(_issue("error", "invalid_transition", "transition must be a mapping", path))
            continue
        from_state = transition.get("from")
        to_state = transition.get("to")
        event = transition.get("on")
        if not from_state or from_state not in states:
            issues.append(_issue("error", "transition_from_undefined", f"from state is undefined: {from_state}", f"{path}.from"))
        if not to_state or to_state not in states:
            issues.append(_issue("error", "transition_to_undefined", f"to state is undefined: {to_state}", f"{path}.to"))
        if not event:
            issues.append(_issue("error", "missing_transition_event", "transition is missing on", f"{path}.on"))
        dispatch = (from_state, event)
        if from_state and event:
            if dispatch in dispatches:
                issues.append(_issue("warning", "conflicting_transition", f"duplicate from/on transition: {from_state} + {event}", path))
            else:
                dispatches[dispatch] = index
        if isinstance(from_state, str) and isinstance(to_state, str):
            adjacency.setdefault(from_state, set()).add(to_state)
        guards = transition.get("guards", [])
        if guards is None:
            guards = []
        if not isinstance(guards, list) or any(not isinstance(guard, str) for guard in guards):
            issues.append(_issue("error", "invalid_guards", "guards must be a string array", f"{path}.guards"))
            guards = []
        metadata = {key: value for key, value in transition.items() if key not in {"from", "to", "on", "guards", "transition_id"}}
        normalized_transitions.append({
            "transition_id": transition.get("transition_id") or f"{machine_id}.transition.{index + 1}",
            "from": from_state,
            "to": to_state,
            "on": event,
            "guards": list(guards),
            "metadata": metadata,
        })

    reachable: set[str] = set()
    if isinstance(initial, str) and initial in states:
        reachable.add(initial)
        queue = [initial]
        while queue:
            current = queue.pop(0)
            for target in sorted(adjacency.get(current, set())):
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
    for state in states:
        if state not in reachable:
            issues.append(_issue("warning", "unreachable_state", f"state is unreachable: {state}", f"{source_path}.states.{state}"))
    semantic = _normalize_semantic_records(doc, source_path, issues)
    return {
        "state_machine_id": machine_id,
        "initial_state": initial,
        "states": states,
        "reachable_states": [state for state in states if state in reachable],
        "transitions": normalized_transitions,
        **semantic,
        "source_document": source_path,
    }


def discover_eveglyph_yaml(source: str | Path) -> tuple[Path, list[Path]]:
    root = Path(source).resolve()
    if root.is_file():
        if root.suffix.lower() not in {".yaml", ".yml"}:
            raise StudioWorldIRError(f"source is not an EveGlyph YAML file: {source}")
        return root.parent, [root]
    if not root.is_dir():
        raise StudioWorldIRError(f"source path does not exist: {source}")
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".yaml", ".yml"})
    if not files:
        raise StudioWorldIRError(f"no EveGlyph YAML files found: {source}")
    return root, files


def _migration_plan(entities: list[dict[str, Any]], state_machines: list[dict[str, Any]]) -> dict[str, Any]:
    entity_bindings: list[dict[str, Any]] = []
    missing_room_bindings: list[str] = []
    binding_totals: dict[str, int] = {}
    binding_seen: dict[str, int] = {}
    for entity in entities:
        base_key = f"{entity.get('source_document')}::{entity.get('entity_id')}"
        binding_totals[base_key] = binding_totals.get(base_key, 0) + 1
    for entity in entities:
        metadata = entity.get("metadata") if isinstance(entity.get("metadata"), dict) else {}
        location = metadata.get("location") if isinstance(metadata.get("location"), str) else None
        base_key = f"{entity.get('source_document')}::{entity.get('entity_id')}"
        binding_seen[base_key] = binding_seen.get(base_key, 0) + 1
        binding_key = base_key
        if binding_totals[base_key] > 1:
            binding_key = f"{base_key}::{binding_seen[base_key]}"
        status = "candidate" if location else "needs_review"
        if not location:
            missing_room_bindings.append(binding_key)
        entity_bindings.append({
            "binding_key": binding_key,
            "entity_id": entity.get("entity_id"),
            "source_document": entity.get("source_document"),
            "target_table": "items" if entity.get("entity_type") == "item" else "entities",
            "proposed_room": location,
            "status": status,
        })

    state_machine_bindings: list[dict[str, Any]] = []
    unmapped_events: list[str] = []
    guarded_transitions: list[str] = []
    for machine in state_machines:
        transitions: list[dict[str, Any]] = []
        for transition in machine.get("transitions", []):
            source_event = transition.get("on")
            event_status = "candidate" if source_event in _RUNTIME_EVENT_TYPES else "needs_review"
            if event_status == "needs_review":
                unmapped_events.append(f"{machine.get('state_machine_id')}::{transition.get('transition_id')}")
            guards = transition.get("guards", [])
            if guards:
                guarded_transitions.append(f"{machine.get('state_machine_id')}::{transition.get('transition_id')}")
            transitions.append({
                "transition_id": transition.get("transition_id"),
                "source_event": source_event,
                "proposed_runtime_event": source_event if event_status == "candidate" else None,
                "guards": list(guards),
                "status": "needs_review" if event_status == "needs_review" or guards else "candidate",
            })
        state_machine_bindings.append({
            "state_machine_id": machine.get("state_machine_id"),
            "source_document": machine.get("source_document"),
            "proposed_target": "quest" if str(machine.get("state_machine_id", "")).startswith("quest.") else None,
            "transitions": transitions,
            "status": "needs_review" if any(item["status"] == "needs_review" for item in transitions) else "candidate",
        })

    required_decisions: list[dict[str, Any]] = []
    if missing_room_bindings:
        required_decisions.append({
            "code": "entity_room_binding",
            "count": len(missing_room_bindings),
            "binding_keys": missing_room_bindings,
            "message": "Assign a Runtime room to each entity before CSV/Package compilation.",
        })
    if unmapped_events:
        required_decisions.append({
            "code": "runtime_event_mapping",
            "count": len(unmapped_events),
            "binding_keys": unmapped_events,
            "message": "Map each Studio event to an allowed Runtime EventIR or add an explicit Runtime Module contract.",
        })
    if guarded_transitions:
        required_decisions.append({
            "code": "guard_semantics",
            "count": len(guarded_transitions),
            "binding_keys": guarded_transitions,
            "message": "Declare how each guard reads Runtime State; free-form guard strings are not compiled as Python.",
        })
    return {
        "format": "compilableworld.studio-migration-plan/v0.1",
        "status": "blocked" if required_decisions else "reviewable",
        "entity_bindings": entity_bindings,
        "state_machine_bindings": state_machine_bindings,
        "mapping_template": {
            "entities": {
                binding["binding_key"]: {
                    "room": binding["proposed_room"],
                    "target_table": binding["target_table"],
                }
                for binding in entity_bindings
            },
            "state_machines": {
                binding["state_machine_id"]: {
                    "event_mappings": {
                        transition["transition_id"]: {"event_type": transition["proposed_runtime_event"]}
                        for transition in binding["transitions"]
                    },
                    "guard_policy": None,
                }
                for binding in state_machine_bindings
            },
        },
        "required_decisions": required_decisions,
    }


def _collect_document(
    document: dict[str, Any],
    source_path: str,
    documents: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    state_machines: list[dict[str, Any]],
    diagnostics: list[dict[str, str]],
) -> None:
    kind = document.get("kind")
    document_id = document.get("id") or Path(source_path).stem
    if kind not in {"entity", "entity_list", "state_machine"}:
        diagnostics.append(_issue("error", "unsupported_kind", f"unsupported EveGlyph kind: {kind}", f"{source_path}.kind"))
    documents.append({"source_path": source_path, "kind": kind or "unknown", "document_id": document_id, "content": document})
    if kind in {"entity", "entity_list"}:
        entities.extend(_normalize_entity_document(document, source_path, diagnostics))
    elif kind == "state_machine":
        state_machines.append(_normalize_state_machine(document, source_path, diagnostics))


def _build_world_ir(
    documents: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    state_machines: list[dict[str, Any]],
    diagnostics: list[dict[str, str]],
) -> dict[str, Any]:
    error_count = sum(issue["severity"] == "error" for issue in diagnostics)
    migration_plan = _migration_plan(entities, state_machines)
    return {
        "format": STUDIO_WORLD_IR_FORMAT,
        "source_format": EVEGLYPH_YAML_FORMAT,
        "compile_ready": False,
        "compile_blockers": [
            "Entity YAML does not guarantee Runtime room/exit placement for every record.",
            "State-machine guards and events require explicit Runtime QuestModule mapping.",
            "A Runtime Package still needs world, rooms, exits, items, and manifest source provenance.",
        ],
        "documents": documents,
        "entities": entities,
        "state_machines": state_machines,
        "migration_plan": migration_plan,
        "diagnostics": {
            "errors": error_count,
            "warnings": len(diagnostics) - error_count,
            "issues": diagnostics,
        },
        "summary": {
            "documents": len(documents),
            "entities": len(entities),
            "state_machines": len(state_machines),
        },
    }


def import_eveglyph_document(document: dict[str, Any], source_path: str = "eveglyph-studio-draft.yaml") -> dict[str, Any]:
    """Normalize one already-parsed EveGlyph document without filesystem access."""
    if not isinstance(document, dict):
        raise StudioWorldIRError("EveGlyph YAML root must be a mapping")
    documents: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    state_machines: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    _collect_document(document, source_path, documents, entities, state_machines, diagnostics)
    return _build_world_ir(documents, entities, state_machines, diagnostics)


def import_eveglyph_text(text: str, source_path: str = "eveglyph-studio-draft.yaml") -> dict[str, Any]:
    """Normalize one EveGlyph YAML text payload without writing or executing it."""
    documents: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    state_machines: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    try:
        document = parse_eveglyph_yaml(text)
    except (StudioWorldIRError, TypeError) as exc:
        diagnostics.append(_issue("error", "parse_error", str(exc), source_path))
        documents.append({"source_path": source_path, "kind": "unknown", "document_id": Path(source_path).stem, "content": None})
        return _build_world_ir(documents, entities, state_machines, diagnostics)
    _collect_document(document, source_path, documents, entities, state_machines, diagnostics)
    return _build_world_ir(documents, entities, state_machines, diagnostics)


def import_eveglyph_yaml(source: str | Path) -> dict[str, Any]:
    """Normalize an EveGlyph YAML file/directory into shared Studio World IR."""
    root, files = discover_eveglyph_yaml(source)
    documents: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    state_machines: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    for path in files:
        source_path = path.relative_to(root).as_posix()
        try:
            document = parse_eveglyph_yaml(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, StudioWorldIRError) as exc:
            diagnostics.append(_issue("error", "parse_error", str(exc), source_path))
            documents.append({"source_path": source_path, "kind": "unknown", "document_id": path.stem, "content": None})
            continue
        _collect_document(document, source_path, documents, entities, state_machines, diagnostics)
    return _build_world_ir(documents, entities, state_machines, diagnostics)


def write_world_ir(world_ir: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(world_ir, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_migration_plan(world_ir: dict[str, Any], output: str | Path) -> Path:
    """Write only the human-reviewable mapping plan from a World IR artifact."""
    plan = world_ir.get("migration_plan")
    if not isinstance(plan, dict):
        raise StudioWorldIRError("World IR does not contain migration_plan")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


__all__ = [
    "EVEGLYPH_YAML_FORMAT", "STUDIO_WORLD_IR_FORMAT", "StudioWorldIRError",
    "discover_eveglyph_yaml", "import_eveglyph_document", "import_eveglyph_text",
    "import_eveglyph_yaml", "parse_eveglyph_yaml",
    "write_migration_plan", "write_world_ir",
]
