"""Fail-closed Studio World IR -> Runtime Package integration.

The normal Compiler remains the source of truth.  This adapter stages a copy
of a complete Runtime Authoring Layer, overlays only explicitly mapped Studio
entities and quest-target state machines, then calls ``compile_world``.  It
never mutates the base source directory and never turns free-form guards or
language records into executable Runtime rules.
"""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .compiler import CompileError, compile_world
from .studio_mapping import validate_studio_mapping


STUDIO_COMPILE_FORMAT = "compilableworld.studio-compile/v0.1"


class StudioCompileError(CompileError):
    """Raised when a Studio overlay is not explicit enough to compile."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StudioCompileError(f"無法讀取 Studio compile JSON: {path}") from exc


def _source_path(root: Path, manifest: dict[str, Any], key: str) -> Path:
    sources = manifest.get("sources")
    relative = sources.get(key) if isinstance(sources, dict) else None
    if not isinstance(relative, str) or not relative.strip():
        raise StudioCompileError(f"manifest.sources 缺少 {key}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise StudioCompileError(f"Studio overlay source path 越界: {relative}") from exc
    if not candidate.is_file():
        raise StudioCompileError(f"Studio overlay source 不存在: {relative}")
    return candidate


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise StudioCompileError(f"CSV 缺少標題: {path}")
            return list(reader.fieldnames), list(reader)
    except OSError as exc:
        raise StudioCompileError(f"無法讀取 CSV: {path}") from exc


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        raise StudioCompileError(f"無法寫入 Studio overlay CSV: {path}") from exc


def _as_component_text(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _overlay_entities(root: Path, manifest: dict[str, Any], world_ir: dict[str, Any], mapping: dict[str, Any]) -> None:
    plan = world_ir.get("migration_plan") if isinstance(world_ir.get("migration_plan"), dict) else {}
    planned = plan.get("entity_bindings") if isinstance(plan.get("entity_bindings"), list) else []
    records = world_ir.get("entities") if isinstance(world_ir.get("entities"), list) else []
    mapped = mapping.get("entities") if isinstance(mapping.get("entities"), dict) else {}
    if len(planned) != len(records):
        raise StudioCompileError("World IR entity bindings and records are inconsistent")
    if not planned:
        return

    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]] = {"entities": [], "items": []}
    for binding, record in zip(planned, records):
        key = binding.get("binding_key")
        decision = mapped.get(key) if isinstance(key, str) else None
        if not isinstance(decision, dict):
            raise StudioCompileError(f"missing entity mapping: {key}")
        target = decision.get("target_table")
        if target not in grouped:
            raise StudioCompileError(f"invalid entity target table: {target}")
        room = decision.get("room")
        if not isinstance(room, str) or not room.strip():
            raise StudioCompileError(f"entity mapping needs an explicit room: {key}")
        grouped[target].append((binding, record, decision))

    for target, additions in grouped.items():
        if not additions:
            continue
        source_key = "entities" if target == "entities" else "items"
        path = _source_path(root, manifest, source_key)
        headers, rows = _read_csv(path)
        id_key = "entity_id" if target == "entities" else "item_id"
        existing = {row.get(id_key, "") for row in rows}
        for binding, record, decision in additions:
            record_id = record.get("entity_id")
            if not isinstance(record_id, str) or not record_id.strip():
                raise StudioCompileError("Studio entity is missing entity_id")
            if record_id in existing:
                raise StudioCompileError(f"Studio overlay refuses to replace existing {id_key}: {record_id}")
            entity_type = record.get("entity_type")
            name = record.get("name")
            if not isinstance(name, str) or not name.strip():
                raise StudioCompileError(f"Studio entity needs an explicit name: {record_id}")
            if target == "entities" and (not isinstance(entity_type, str) or not entity_type.strip() or entity_type == "item"):
                raise StudioCompileError(f"Studio entity target mismatch: {record_id}")
            if target == "items" and entity_type != "item":
                raise StudioCompileError(f"Studio item mapping requires entity_type=item: {record_id}")
            metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
            row = {header: "" for header in headers}
            row[id_key] = record_id
            row["name"] = name
            row["room"] = str(decision["room"])
            if target == "entities":
                row["entity_type"] = str(entity_type)
                row["provenance"] = "studio_mapped"
                if "components" in row:
                    row["components"] = _as_component_text(metadata.get("components", "position"))
                for field in ("health", "str", "con", "mag", "agi", "dex", "phase_tier"):
                    if field in row and field in metadata:
                        row[field] = str(metadata[field])
            else:
                portable = metadata.get("portable")
                if not isinstance(portable, bool):
                    raise StudioCompileError(f"Studio item needs explicit metadata.portable: {record_id}")
                row["portable"] = "true" if portable else "false"
                row["provenance"] = "studio_mapped"
            rows.append(row)
            existing.add(record_id)
        _write_csv(path, headers, rows)


def _overlay_quests(root: Path, manifest: dict[str, Any], world_ir: dict[str, Any], mapping: dict[str, Any]) -> None:
    machines = world_ir.get("state_machines") if isinstance(world_ir.get("state_machines"), list) else []
    if not machines:
        return
    quests_path = _source_path(root, manifest, "quests")
    quests = _load_json(quests_path)
    if not isinstance(quests, list):
        raise StudioCompileError("quests.json 必須是陣列")
    existing = {quest.get("quest_id") for quest in quests if isinstance(quest, dict)}
    mapped_machines = mapping.get("state_machines") if isinstance(mapping.get("state_machines"), dict) else {}
    for machine in machines:
        machine_id = machine.get("state_machine_id")
        binding = mapped_machines.get(machine_id) if isinstance(machine_id, str) else None
        if not isinstance(binding, dict) or binding.get("target") != "quest":
            raise StudioCompileError(f"state machine requires explicit target=quest: {machine_id}")
        if any(transition.get("guards") for transition in machine.get("transitions", []) if isinstance(transition, dict)):
            raise StudioCompileError(f"free-form guards are not compilable in Studio v0.1: {machine_id}")
        if not isinstance(machine_id, str) or machine_id in existing:
            raise StudioCompileError(f"Studio quest overlay conflicts with existing quest_id: {machine_id}")
        event_mappings = binding.get("event_mappings") if isinstance(binding.get("event_mappings"), dict) else {}
        transitions: list[dict[str, Any]] = []
        for transition in machine.get("transitions", []):
            transition_id = transition.get("transition_id")
            event_mapping = event_mappings.get(transition_id) if isinstance(transition_id, str) else None
            if not isinstance(event_mapping, dict):
                raise StudioCompileError(f"missing event mapping: {machine_id}.{transition_id}")
            event_match = event_mapping.get("event_match", {})
            if not isinstance(event_match, dict):
                raise StudioCompileError(f"event_match must be an object: {machine_id}.{transition_id}")
            transitions.append({
                "transition_id": transition_id,
                "from": transition.get("from"),
                "on": event_mapping.get("event_type"),
                "to": transition.get("to"),
                "event_match": dict(event_match),
                "priority": 0,
            })
        quests.append({
            "quest_id": machine_id,
            "title": machine_id,
            "initial_state": machine.get("initial_state"),
            "canon_status": "studio_mapped",
            "transitions": transitions,
        })
        existing.add(machine_id)
    quests_path.write_text(json.dumps(quests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compile_studio_world_ir(
    source_dir: str | Path,
    world_ir: dict[str, Any],
    mapping: dict[str, Any],
    output_dir: str | Path,
) -> Path:
    """Compile a reviewed Studio overlay on top of a complete base world."""
    if not isinstance(world_ir, dict) or world_ir.get("format") != "compilableworld.studio-world-ir/v0.1":
        raise StudioCompileError("expected compilableworld.studio-world-ir/v0.1")
    if not isinstance(mapping, dict):
        raise StudioCompileError("Studio mapping root must be an object")
    if (world_ir.get("diagnostics") or {}).get("errors", 0):
        raise StudioCompileError("World IR has diagnostics errors; fix the draft before compile")
    report = validate_studio_mapping(world_ir, mapping)
    if not report["mapping_complete"] or not report["runtime_ready"]:
        issues = "; ".join(item["code"] for item in report["diagnostics"]["issues"])
        raise StudioCompileError(f"Studio mapping is not runtime-ready: {issues or 'unknown mapping error'}")

    root = Path(source_dir).resolve()
    if not root.is_dir():
        raise StudioCompileError(f"base Runtime source does not exist: {source_dir}")
    output = Path(output_dir).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise StudioCompileError("Studio compile output must be outside the base Runtime source")

    with tempfile.TemporaryDirectory(prefix="compilableworld-studio-") as temp:
        staged = Path(temp) / "source"
        shutil.copytree(root, staged, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))
        manifest = _load_json(staged / "manifest.json")
        if not isinstance(manifest, dict):
            raise StudioCompileError("base manifest.json must be an object")
        _overlay_entities(staged, manifest, world_ir, mapping)
        _overlay_quests(staged, manifest, world_ir, mapping)
        metadata = {
            "format": STUDIO_COMPILE_FORMAT,
            "world_ir_format": world_ir["format"],
            "mapping_format": mapping.get("format"),
            "base_world_id": manifest.get("world_id"),
            "mapped_entities": len(world_ir.get("entities", [])),
            "mapped_state_machines": len(world_ir.get("state_machines", [])),
            "semantic_records_are_metadata_only": True,
        }
        return compile_world(staged, output, package_metadata=metadata)


def compile_studio_files(
    source_dir: str | Path,
    world_ir_path: str | Path,
    mapping_path: str | Path,
    output_dir: str | Path,
) -> Path:
    world_ir = _load_json(Path(world_ir_path))
    mapping = _load_json(Path(mapping_path))
    return compile_studio_world_ir(source_dir, world_ir, mapping, output_dir)


__all__ = ["STUDIO_COMPILE_FORMAT", "StudioCompileError", "compile_studio_files", "compile_studio_world_ir"]
