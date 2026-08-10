from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import deque
from pathlib import Path
from typing import Any

from .action_behavior import (
    ACTION_BEHAVIOR_CHILD_ARG_FIELDS,
    ACTION_BEHAVIOR_CHILD_ARG_LIMIT,
    ACTION_BEHAVIOR_CHILD_MODULES,
    ACTION_BEHAVIOR_CHILD_REQUIRED_ARGS,
    ACTION_BEHAVIOR_CHILD_TARGET_VERBS,
    ACTION_BEHAVIOR_BRANCH_LIMIT,
    ACTION_BEHAVIOR_BRANCH_PRIORITY_LIMIT,
    ACTION_BEHAVIOR_CONCURRENCY,
    ACTION_BEHAVIOR_CONDITION_LIMIT,
    ACTION_BEHAVIOR_CONDITION_NAMESPACES,
    ACTION_BEHAVIOR_CONDITION_OPERATORS,
    ACTION_BEHAVIOR_CONDITION_SUBJECTS,
    ACTION_BEHAVIOR_DEFINITION_LIMIT,
    ACTION_BEHAVIOR_DURATION_LIMIT,
    ACTION_BEHAVIOR_EXECUTION_MODEL_STATIC_DAG,
    ACTION_BEHAVIOR_FORMAT,
    ACTION_BEHAVIOR_FORMAT_V1,
    ACTION_BEHAVIOR_FORMAT_V2,
    ACTION_BEHAVIOR_FORMAT_V3,
    ACTION_BEHAVIOR_FORMAT_V4,
    ACTION_BEHAVIOR_FORMAT_V5,
    ACTION_BEHAVIOR_FORMAT_V6,
    ACTION_BEHAVIOR_INTERRUPT_EVENTS,
    ACTION_BEHAVIOR_INTERRUPT_LIMIT,
    ACTION_BEHAVIOR_PHASE_LIMIT,
    ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT,
    ACTION_BEHAVIOR_SCHEMA_ID,
    ACTION_BEHAVIOR_SCHEMA_ID_V1,
    ACTION_BEHAVIOR_SCHEMA_ID_V2,
    ACTION_BEHAVIOR_SCHEMA_ID_V3,
    ACTION_BEHAVIOR_SCHEMA_ID_V4,
    ACTION_BEHAVIOR_SCHEMA_ID_V5,
    ACTION_BEHAVIOR_SCHEMA_ID_V6,
)
from .functions import FunctionDefinitionError, FunctionRegistry, validate_function_source
from .player_generation import template_records
from .schema_registry import SchemaContractError, csv_schema_columns, schema_contracts
from .state_machine import (
    STATE_MACHINE_DEFINITION_LIMIT,
    STATE_MACHINE_EVENT_MATCH_LIMIT,
    STATE_MACHINE_OWNER_SCOPES,
    STATE_MACHINE_PRIORITY_LIMIT,
    STATE_MACHINE_REQUIREMENT_LIMIT,
    STATE_MACHINE_REWARD_CURRENCY_LIMIT,
    STATE_MACHINE_STATE_LIMIT,
    STATE_MACHINE_TRANSITION_LIMIT,
    STATE_MACHINE_TRIGGER_EVENT_FIELDS,
    STATE_MACHINE_VISIBILITIES,
)


ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
ATTRIBUTE_COLUMNS = ("str", "con", "mag", "agi", "dex")
STATE_CONDITION_READ_NAMESPACES = {
    "position", "inventory", "door", "health", "status", "quest",
    "wallet", "fsm", "combat", "magic",
}
QUEST_TRIGGER_EVENT_FIELDS = STATE_MACHINE_TRIGGER_EVENT_FIELDS


class CompileError(ValueError):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompileError(f"無法讀取 JSON {path}: {exc}") from exc


def _load_csv(path: Path, schema_key: str | None = None) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if (
                not fieldnames
                or any(not isinstance(name, str) or not name.strip() for name in fieldnames)
                or len(fieldnames) != len(set(fieldnames))
            ):
                raise CompileError(f"CSV 標題缺失或重複: {path}")
            if schema_key:
                columns = csv_schema_columns(schema_key)
                allowed = {column.get("name") for column in columns}
                required = {column.get("name") for column in columns if column.get("required")}
                actual = set(fieldnames)
                unknown = sorted(actual - allowed)
                missing = sorted(required - actual)
                if unknown or missing:
                    raise CompileError(
                        f"{path.name} 不符合 {schema_key} CSV Schema: "
                        f"unknown={unknown}, missing={missing}"
                    )
            return list(reader)
    except OSError as exc:
        raise CompileError(f"無法讀取 CSV {path}: {exc}") from exc


def _safe_source(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise CompileError(f"來源路徑越界: {relative}") from exc
    if not candidate.is_file():
        raise CompileError(f"來源不存在: {relative}")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _required(row: dict[str, str], fields: list[str], source: str) -> None:
    missing = [name for name in fields if not (row.get(name) or "").strip()]
    if missing:
        raise CompileError(f"{source} 缺少必填欄位: {', '.join(missing)}")


def _validate_attributes(row: dict[str, str]) -> None:
    """The five combat attributes (worlds/mingyun_zhiyu/data/drafts/combat_resolution_system.json)
    are all-or-nothing: a half-authored set would silently mix real and
    floor-default values in a way that's easy to author by accident."""
    present = [attr for attr in ATTRIBUTE_COLUMNS if (row.get(attr) or "").strip()]
    if present and len(present) != len(ATTRIBUTE_COLUMNS):
        missing = [attr for attr in ATTRIBUTE_COLUMNS if attr not in present]
        raise CompileError(f"實體 {row.get('entity_id')} 只填了部分戰鬥屬性，缺少: {', '.join(missing)}")
    if present and (row.get("health") or "").strip():
        raise CompileError(f"實體 {row.get('entity_id')} 同時有 health 與五維屬性 — HP 由 CON×8 推導，不能兩者都填")


def _unique(rows: list[dict[str, Any]], key: str, source: str) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        value = str(row[key])
        if not ID_RE.match(value):
            raise CompileError(f"{source} 含不合法 ID: {value}")
        if value in ids:
            raise CompileError(f"{source} 含重複 ID: {value}")
        ids.add(value)
    return ids


def compile_world(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    package_metadata: dict[str, Any] | None = None,
) -> Path:
    """Compile Authoring Layer files into one deterministic runtime package."""
    root = Path(source_dir).resolve()
    manifest_path = root / "manifest.json"
    manifest = _load_json(manifest_path)
    for key in ("world_id", "world_version", "schema_version", "namespace", "sources"):
        if key not in manifest:
            raise CompileError(f"manifest.json 缺少 {key}")
    if not ID_RE.match(manifest["world_id"]):
        raise CompileError("world_id 格式不合法")

    sources = manifest["sources"]
    required_sources = ("world", "rooms", "exits", "entities", "items", "quests")
    for key in required_sources:
        if key not in sources:
            raise CompileError(f"manifest.sources 缺少 {key}")

    resolved: dict[str, Path] = {
        key: _safe_source(root, str(sources[key])) for key in required_sources
    }
    if "narrative" in sources:
        resolved["narrative"] = _safe_source(root, str(sources["narrative"]))
    if "dialogues" in sources:
        resolved["dialogues"] = _safe_source(root, str(sources["dialogues"]))
    if "player_templates" in sources:
        resolved["player_templates"] = _safe_source(root, str(sources["player_templates"]))
    if "scenarios" in sources:
        resolved["scenarios"] = _safe_source(root, str(sources["scenarios"]))
    if "functions" in sources:
        resolved["functions"] = _safe_source(root, str(sources["functions"]))
    if "state_machines" in sources:
        resolved["state_machines"] = _safe_source(root, str(sources["state_machines"]))
    if "action_behaviors" in sources:
        resolved["action_behaviors"] = _safe_source(root, str(sources["action_behaviors"]))
    world = _load_json(resolved["world"])
    rooms = _load_csv(resolved["rooms"], "rooms")
    exits = _load_csv(resolved["exits"], "exits")
    entities = _load_csv(resolved["entities"], "entities")
    items = _load_csv(resolved["items"], "items")
    quests = _load_json(resolved["quests"])
    narrative = _load_json(resolved["narrative"]) if "narrative" in resolved else {"room_overlays": []}
    dialogues = _load_json(resolved["dialogues"]) if "dialogues" in resolved else {"dialogues": []}
    scenarios = _load_json(resolved["scenarios"]) if "scenarios" in resolved else {"scenarios": []}
    functions = _load_json(resolved["functions"]) if "functions" in resolved else {"functions": []}
    state_machines_source = (
        _load_json(resolved["state_machines"])
        if "state_machines" in resolved else {"format": "compilableworld.state-machines/v0.1", "state_machines": []}
    )
    action_behaviors_source = (
        _load_json(resolved["action_behaviors"])
        if "action_behaviors" in resolved else {"format": ACTION_BEHAVIOR_FORMAT, "behaviors": []}
    )
    try:
        player_templates = (
            template_records({"player_templates": _load_json(resolved["player_templates"])})
            if "player_templates" in resolved
            else template_records()
        )
    except (TypeError, ValueError) as exc:
        raise CompileError(f"player_templates invalid: {exc}") from exc

    for row in rooms:
        _required(row, ["room_id", "name", "description", "region"], "rooms.csv")
    for row in exits:
        _required(row, ["exit_id", "from_room", "to_room", "direction"], "exits.csv")
    for row in entities:
        _required(row, ["entity_id", "entity_type", "name", "room"], "entities.csv")
        _validate_attributes(row)
    for row in items:
        _required(row, ["item_id", "name", "room", "portable"], "items.csv")

    room_ids = _unique(rooms, "room_id", "rooms.csv")
    region_ids = {row["region"] for row in rooms}
    exit_ids = _unique(exits, "exit_id", "exits.csv")
    entity_ids = _unique(entities, "entity_id", "entities.csv")
    item_ids = _unique(items, "item_id", "items.csv")
    del exit_ids
    overlap = entity_ids & item_ids
    if overlap:
        raise CompileError(f"entity/item ID 衝突: {sorted(overlap)}")
    action_behaviors = _validate_action_behaviors(
        action_behaviors_source,
        entity_ids=entity_ids | item_ids,
    )
    state_machines = _validate_scoped_state_machines(
        state_machines_source,
        world_id=manifest["world_id"],
        region_ids=region_ids,
        room_ids=room_ids,
        entity_ids=entity_ids | item_ids,
    )
    quests = _validate_quests(
        quests, room_ids=room_ids, item_ids=item_ids,
        entity_types={row["entity_id"]: row["entity_type"] for row in entities},
    )
    narrative = _validate_narrative(narrative, room_ids)
    dialogues = _validate_dialogues(dialogues, {row["entity_id"]: row["entity_type"] for row in entities})
    scenarios = _validate_scenarios(
        scenarios,
        label="scenarios.json",
        world_id=manifest["world_id"],
        entity_ids=entity_ids,
        item_ids=item_ids,
    )
    try:
        functions = validate_function_source(functions)
    except FunctionDefinitionError as exc:
        raise CompileError(f"functions.json invalid: {exc}") from exc
    try:
        contract_ids = schema_contracts(verify=True)
    except SchemaContractError as exc:
        raise CompileError(f"schema contracts invalid: {exc}") from exc
    declared_source_schemas = manifest.get("source_schemas", {})
    if not isinstance(declared_source_schemas, dict):
        raise CompileError("manifest.source_schemas 必須是物件")
    unknown_schema_keys = set(declared_source_schemas) - set(contract_ids)
    if unknown_schema_keys:
        raise CompileError(f"manifest.source_schemas 含未知來源: {sorted(unknown_schema_keys)}")
    action_behavior_schema_id = {
        ACTION_BEHAVIOR_FORMAT_V1: ACTION_BEHAVIOR_SCHEMA_ID_V1,
        ACTION_BEHAVIOR_FORMAT_V2: ACTION_BEHAVIOR_SCHEMA_ID_V2,
        ACTION_BEHAVIOR_FORMAT_V3: ACTION_BEHAVIOR_SCHEMA_ID_V3,
        ACTION_BEHAVIOR_FORMAT_V4: ACTION_BEHAVIOR_SCHEMA_ID_V4,
        ACTION_BEHAVIOR_FORMAT_V5: ACTION_BEHAVIOR_SCHEMA_ID_V5,
        ACTION_BEHAVIOR_FORMAT_V6: ACTION_BEHAVIOR_SCHEMA_ID_V6,
        ACTION_BEHAVIOR_FORMAT: ACTION_BEHAVIOR_SCHEMA_ID,
    }.get(action_behaviors_source.get("format") if isinstance(action_behaviors_source, dict) else None)
    for source_key, declared_schema_id in declared_source_schemas.items():
        expected_schema_id = (
            action_behavior_schema_id
            if source_key == "action_behaviors" and action_behavior_schema_id is not None
            else contract_ids[source_key]
        )
        if declared_schema_id != expected_schema_id:
            raise CompileError(
                f"manifest.source_schemas.{source_key} 與正式契約不符: {declared_schema_id}"
            )
    function_registry = FunctionRegistry(functions)

    source_schema_ids = {
        key: contract_ids[key]
        for key in (
            "rooms", "exits", "entities", "items", "functions", "scenarios",
            "state_machines", "action_behaviors",
        )
        if key in sources
    }
    if "action_behaviors" in sources and action_behavior_schema_id is not None:
        source_schema_ids["action_behaviors"] = action_behavior_schema_id

    for row in exits:
        if row["from_room"] not in room_ids or row["to_room"] not in room_ids:
            raise CompileError(f"出口 {row['exit_id']} 引用不存在房間")
        door = row.get("door_entity", "").strip()
        if door and door not in entity_ids:
            raise CompileError(f"出口 {row['exit_id']} 引用不存在門 {door}")
    for row in entities:
        if row["room"] not in room_ids:
            raise CompileError(f"實體 {row['entity_id']} 引用不存在房間")
    for row in items:
        if row["room"] not in room_ids:
            raise CompileError(f"物品 {row['item_id']} 引用不存在房間")

    spawn = world.get("player_spawn")
    if spawn not in room_ids:
        raise CompileError("world.player_spawn 引用不存在房間")
    default_player = world.get("default_player_entity")
    if default_player and default_player not in entity_ids:
        raise CompileError("world.default_player_entity 引用不存在實體")
    _validate_reachability(room_ids, exits, spawn)

    compiled_entities: list[dict[str, Any]] = []
    initial_state: list[dict[str, Any]] = []
    for row in entities:
        components = [x for x in row.get("components", "").split("|") if x]
        compiled_entities.append({
            "entity_id": row["entity_id"], "entity_type": row["entity_type"],
            "name": row["name"], "components": components,
            "metadata": {"provenance": row.get("provenance", "human_authored")},
        })
        initial_state.append(_state(row["entity_id"], "position", "room", row["room"]))
        if (row.get("con") or "").strip():
            attrs = {attr: int(row[attr]) for attr in ATTRIBUTE_COLUMNS}
            for attr, value in attrs.items():
                initial_state.append(_state(row["entity_id"], "combat", attr, value))
            if (row.get("phase_tier") or "").strip():
                initial_state.append(_state(row["entity_id"], "combat", "phase_tier", int(row["phase_tier"])))
            health = int(function_registry.evaluate("combat.hp_from_con", {"con": attrs["con"]})) if function_registry.has("combat.hp_from_con") else attrs["con"] * 8
            mp_max = int(function_registry.evaluate("player.mp_from_mag", {"mag": attrs["mag"]})) if function_registry.has("player.mp_from_mag") else attrs["mag"] * 5
            fp_max = int(function_registry.evaluate("player.fp_from_mag_dex", {"mag": attrs["mag"], "dex": attrs["dex"]})) if function_registry.has("player.fp_from_mag_dex") else (attrs["mag"] + attrs["dex"]) * 2
            initial_state.extend([
                _state(row["entity_id"], "health", "current", health),
                _state(row["entity_id"], "health", "max", health),
                _state(row["entity_id"], "status", "alive", True),
                _state(row["entity_id"], "magic", "mp_current", mp_max),
                _state(row["entity_id"], "magic", "mp_max", mp_max),
                _state(row["entity_id"], "magic", "fp_current", fp_max),
                _state(row["entity_id"], "magic", "fp_max", fp_max),
            ])
        elif (row.get("health") or "").strip():
            health = int(row["health"])
            initial_state.extend([
                _state(row["entity_id"], "health", "current", health),
                _state(row["entity_id"], "health", "max", health),
                _state(row["entity_id"], "status", "alive", True),
            ])
    for row in items:
        compiled_entities.append({
            "entity_id": row["item_id"], "entity_type": "item", "name": row["name"],
            "components": ["position", "inventory"],
            "metadata": {"portable": _bool(row["portable"]), "provenance": row.get("provenance", "human_authored")},
        })
        initial_state.extend([
            _state(row["item_id"], "position", "room", row["room"]),
            _state(row["item_id"], "inventory", "carrier", None),
        ])
    for row in exits:
        door = row.get("door_entity", "").strip()
        if door:
            initial_state.extend([
                _state(door, "door", "open", _bool(row.get("open", "false"))),
                _state(door, "door", "locked", _bool(row.get("locked", "false"))),
                _state(door, "door", "key_id", row.get("key_id", "").strip() or None),
            ])

    legacy_world_state_machines = world.get("world_state_machines", {})
    if not isinstance(legacy_world_state_machines, dict):
        raise CompileError("world.world_state_machines 必須是物件")
    for owner, state_name in legacy_world_state_machines.items():
        if not isinstance(owner, str) or (owner != "world" and not ID_RE.match(owner)):
            raise CompileError(f"world.world_state_machines owner 不合法: {owner}")
        if not isinstance(state_name, str) or not ID_RE.match(state_name):
            raise CompileError(f"world.world_state_machines state 不合法: {state_name}")
        state_owner = manifest["world_id"] if owner == "world" else owner
        initial_state.append(_state(state_owner, "fsm", "state", state_name))
    for machine in state_machines:
        initial_state.append(_state(
            machine["owner_id"], "fsm", machine["state_machine_id"], machine["initial_state"]
        ))
    if default_player:
        initial_state.append(_state(default_player, "wallet", "currency", 0))
        for quest in quests:
            initial_state.append(_state(default_player, "quest", quest["quest_id"], quest["initial_state"]))

    modules = manifest.get("modules", [
        "room.core", "movement.core", "door.core", "inventory.core",
        "health.core", "combat.basic", "dialogue.core", "quest.core",
    ])
    if not isinstance(modules, list) or not modules or len(modules) != len(set(modules)):
        raise CompileError("manifest.modules 必須是非空且不重複的陣列")
    for module_id in modules:
        if not isinstance(module_id, str) or not ID_RE.match(module_id):
            raise CompileError(f"不合法 module ID: {module_id}")
    if state_machines and "state_machine.core" not in modules:
        raise CompileError("state_machines source 需要 manifest.modules 宣告 state_machine.core")
    for behavior in action_behaviors:
        if behavior["completion_module"] not in modules:
            raise CompileError(
                f"action behavior {behavior['behavior_id']} 的 completion_module "
                f"未在 manifest.modules 宣告: {behavior['completion_module']}"
            )
        for phase in behavior.get("phases", []):
            child_action = phase.get("child_action")
            if isinstance(child_action, dict) and child_action["module_id"] not in modules:
                raise CompileError(
                    f"action behavior {behavior['behavior_id']} child step "
                    f"{child_action['step_id']} module is not in manifest.modules: "
                    f"{child_action['module_id']}"
                )
            for branch in phase.get("branches", []):
                branch_child = branch.get("child_action")
                if (
                    isinstance(branch_child, dict)
                    and branch_child["module_id"] not in modules
                ):
                    raise CompileError(
                        f"action behavior {behavior['behavior_id']} branch "
                        f"{branch['branch_id']} child module is not in manifest.modules: "
                        f"{branch_child['module_id']}"
                    )
    package = {
        "format": "compilableworld.runtime-package/v0.1",
        "manifest": {
            "world_id": manifest["world_id"], "world_version": manifest["world_version"],
            "schema_version": manifest["schema_version"], "namespace": manifest["namespace"],
            "runtime_version": "0.1.0", "modules": modules,
            "source_schemas": source_schema_ids,
        },
        "world": world,
        "rooms": rooms,
        "exits": exits,
        "entities": compiled_entities,
        "action_behaviors": action_behaviors,
        "state_machines": state_machines,
        "quests": quests,
        "narrative": narrative,
        "dialogues": dialogues,
        "scenarios": scenarios,
        "functions": functions,
        # Basic AI-proposed player templates are runtime data, not canon
        # protagonist records.  A package may replace this list later without
        # changing the player-generation API.
        "player_templates": player_templates,
        "initial_state": initial_state,
        # These IDs make the package self-describing for Studio/EveGlyph.
        # The actual schema documents remain repository-level authoring assets.
        "schema_contracts": contract_ids,
        "source_checksums": {
            str(path.relative_to(root)): _sha256(path)
            for path in [manifest_path, *resolved.values()]
        },
    }
    if package_metadata is not None:
        if not isinstance(package_metadata, dict):
            raise CompileError("package_metadata 必須是物件")
        package["studio"] = dict(package_metadata)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    package_path = out / "world.package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = {
        "ok": True, "world_id": manifest["world_id"], "rooms": len(rooms),
        "exits": len(exits), "entities": len(compiled_entities), "states": len(initial_state),
        "modules": modules, "dialogues": len(dialogues["dialogues"]),
        "scenarios": len(scenarios["scenarios"]), "functions": len(functions["functions"]),
        "action_behaviors": len(action_behaviors),
        "state_machines": len(state_machines),
        "package_sha256": _sha256(package_path),
    }
    (out / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return package_path


def validate_world(source_dir: str | Path) -> dict[str, Any]:
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        package_path = compile_world(source_dir, temp)
        package = _load_json(package_path)
        return {
            "ok": True,
            "world_id": package["manifest"]["world_id"],
            "rooms": len(package["rooms"]),
            "entities": len(package["entities"]),
        }


def _state(owner: str, namespace: str, key: str, value: Any) -> dict[str, Any]:
    return {"owner": owner, "namespace": namespace, "key": key, "value": value, "version": 0}


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _finite_json_scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, (str, bool, int))
        or (isinstance(value, float) and math.isfinite(value))
    )


def _validate_action_child(
    raw_child: Any,
    *,
    label: str,
    authored_verbs: set[str],
    entity_ids: set[str],
    step_ids: set[str],
) -> dict[str, Any] | None:
    if raw_child is None:
        return None
    allowed = {"step_id", "verb", "target", "args"}
    if not isinstance(raw_child, dict):
        raise CompileError(f"{label} must be an object or null")
    unknown = set(raw_child) - allowed
    missing = allowed - set(raw_child)
    if unknown:
        raise CompileError(f"{label} contains unknown fields: {sorted(unknown)}")
    if missing:
        raise CompileError(f"{label} is missing fields: {sorted(missing)}")

    step_id = raw_child["step_id"]
    verb = raw_child["verb"]
    if not isinstance(step_id, str) or not ID_RE.match(step_id):
        raise CompileError(f"{label}.step_id is invalid")
    if step_id in step_ids:
        raise CompileError(f"{label}.step_id is duplicated: {step_id}")
    step_ids.add(step_id)
    if verb not in ACTION_BEHAVIOR_CHILD_MODULES:
        raise CompileError(f"{label}.verb is not a bounded primitive: {verb}")
    if verb in authored_verbs:
        raise CompileError(f"{label}.verb cannot invoke an authored behavior: {verb}")

    target = raw_child["target"]
    normalized_target: dict[str, str] | None = None
    if target is not None:
        if not isinstance(target, dict) or "source" not in target:
            raise CompileError(f"{label}.target must be a bounded target object or null")
        source = target.get("source")
        expected_fields = {"source"} if source == "parent_target" else {"source", "entity_id"}
        if set(target) != expected_fields or source not in {"parent_target", "entity"}:
            raise CompileError(f"{label}.target shape is invalid")
        if source == "entity":
            entity_id = target.get("entity_id")
            if not isinstance(entity_id, str) or entity_id not in entity_ids:
                raise CompileError(f"{label}.target.entity_id references an unknown entity")
            normalized_target = {"source": "entity", "entity_id": entity_id}
        else:
            normalized_target = {"source": "parent_target"}
    if verb in ACTION_BEHAVIOR_CHILD_TARGET_VERBS and normalized_target is None:
        raise CompileError(f"{label}.target is required for {verb}")
    if verb not in ACTION_BEHAVIOR_CHILD_TARGET_VERBS and normalized_target is not None:
        raise CompileError(f"{label}.target is forbidden for {verb}")

    args = raw_child["args"]
    if not isinstance(args, dict) or len(args) > ACTION_BEHAVIOR_CHILD_ARG_LIMIT:
        raise CompileError(
            f"{label}.args must be an object with at most {ACTION_BEHAVIOR_CHILD_ARG_LIMIT} fields"
        )
    allowed_args = ACTION_BEHAVIOR_CHILD_ARG_FIELDS[verb]
    required_args = ACTION_BEHAVIOR_CHILD_REQUIRED_ARGS.get(verb, set())
    if set(args) - allowed_args:
        raise CompileError(f"{label}.args contains unsupported fields: {sorted(set(args) - allowed_args)}")
    if required_args - set(args):
        raise CompileError(f"{label}.args is missing fields: {sorted(required_args - set(args))}")
    normalized_args: dict[str, Any] = {}
    for key, value in args.items():
        if not _finite_json_scalar(value):
            raise CompileError(f"{label}.args.{key} must be a finite JSON scalar")
        if key in {"direction", "recipient", "spell", "text", "topic"} and (
            not isinstance(value, str) or not value.strip()
        ):
            raise CompileError(f"{label}.args.{key} must be a non-empty string")
        normalized_args[key] = value.strip() if isinstance(value, str) else value
    recipient = normalized_args.get("recipient")
    if verb == "give" and recipient not in entity_ids:
        raise CompileError(f"{label}.args.recipient references an unknown entity")
    return {
        "step_id": step_id,
        "verb": verb,
        "module_id": ACTION_BEHAVIOR_CHILD_MODULES[verb],
        "target": normalized_target,
        "args": normalized_args,
    }


def _validate_action_branch_conditions(
    raw_conditions: Any,
    *,
    label: str,
    condition_ids: set[str],
) -> list[dict[str, Any]]:
    if (
        not isinstance(raw_conditions, list)
        or len(raw_conditions) > ACTION_BEHAVIOR_CONDITION_LIMIT
    ):
        raise CompileError(
            f"{label} must contain at most {ACTION_BEHAVIOR_CONDITION_LIMIT} conditions"
        )
    normalized: list[dict[str, Any]] = []
    allowed = {"condition_id", "subject", "namespace", "key", "operator", "value"}
    for index, condition in enumerate(raw_conditions):
        condition_label = f"{label}[{index}]"
        if not isinstance(condition, dict):
            raise CompileError(f"{condition_label} must be an object")
        unknown = set(condition) - allowed
        missing = allowed - set(condition)
        if unknown:
            raise CompileError(
                f"{condition_label} contains unknown fields: {sorted(unknown)}"
            )
        if missing:
            raise CompileError(
                f"{condition_label} is missing fields: {sorted(missing)}"
            )
        condition_id = condition["condition_id"]
        subject = condition["subject"]
        namespace = condition["namespace"]
        key = condition["key"]
        operator = condition["operator"]
        expected = condition["value"]
        if not isinstance(condition_id, str) or not ID_RE.match(condition_id):
            raise CompileError(f"{condition_label}.condition_id is invalid")
        if condition_id in condition_ids:
            raise CompileError(f"duplicate action condition_id: {condition_id}")
        condition_ids.add(condition_id)
        if subject not in ACTION_BEHAVIOR_CONDITION_SUBJECTS:
            raise CompileError(f"{condition_label}.subject is unsupported")
        if namespace not in ACTION_BEHAVIOR_CONDITION_NAMESPACES:
            raise CompileError(f"{condition_label}.namespace is unsupported")
        if not isinstance(key, str) or not ID_RE.match(key):
            raise CompileError(f"{condition_label}.key is invalid")
        if operator not in ACTION_BEHAVIOR_CONDITION_OPERATORS:
            raise CompileError(f"{condition_label}.operator is unsupported")
        if not _finite_json_scalar(expected):
            raise CompileError(f"{condition_label}.value must be a finite JSON scalar")
        if operator in {
            "less_than", "less_or_equal", "greater_than", "greater_or_equal",
        } and (isinstance(expected, bool) or not isinstance(expected, (int, float))):
            raise CompileError(f"{condition_label}.value must be numeric")
        normalized.append({
            "condition_id": condition_id,
            "subject": subject,
            "namespace": namespace,
            "key": key,
            "operator": operator,
            "value": expected,
        })
    return normalized


def _validate_action_behaviors(
    source: Any,
    *,
    entity_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(source, dict):
        raise CompileError("action_behaviors.json 必須是物件")
    unknown_root = set(source) - {"format", "behaviors"}
    if unknown_root:
        raise CompileError(f"action_behaviors.json 含未知欄位: {sorted(unknown_root)}")
    source_format = source.get("format")
    if source_format not in {
        ACTION_BEHAVIOR_FORMAT_V1, ACTION_BEHAVIOR_FORMAT_V2,
        ACTION_BEHAVIOR_FORMAT_V3, ACTION_BEHAVIOR_FORMAT_V4,
        ACTION_BEHAVIOR_FORMAT_V5, ACTION_BEHAVIOR_FORMAT_V6,
        ACTION_BEHAVIOR_FORMAT,
    }:
        raise CompileError("action_behaviors.json format 不支援")
    behaviors = source.get("behaviors")
    if not isinstance(behaviors, list):
        raise CompileError("action_behaviors.json.behaviors 必須是陣列")
    if len(behaviors) > ACTION_BEHAVIOR_DEFINITION_LIMIT:
        raise CompileError(
            f"action_behaviors.json 不可超過 {ACTION_BEHAVIOR_DEFINITION_LIMIT} 個 behavior"
        )

    common = {
        "behavior_id", "title", "verb", "completion_module", "concurrency", "interrupt_on",
    }
    allowed = common | ({"duration_ticks"} if source_format == ACTION_BEHAVIOR_FORMAT_V1 else {"phases"})
    behavior_ids: set[str] = set()
    verbs: set[str] = set()
    authored_verbs = {
        behavior.get("verb")
        for behavior in behaviors
        if isinstance(behavior, dict) and isinstance(behavior.get("verb"), str)
    }
    normalized: list[dict[str, Any]] = []
    for index, behavior in enumerate(behaviors):
        label = f"action_behaviors.json.behaviors[{index}]"
        if not isinstance(behavior, dict):
            raise CompileError(f"{label} 必須是物件")
        unknown = set(behavior) - allowed
        missing = allowed - set(behavior)
        if unknown:
            raise CompileError(f"{label} 含未知欄位: {sorted(unknown)}")
        if missing:
            raise CompileError(f"{label} 缺少必填欄位: {sorted(missing)}")

        behavior_id = behavior["behavior_id"]
        verb = behavior["verb"]
        completion_module = behavior["completion_module"]
        if not isinstance(behavior_id, str) or not ID_RE.match(behavior_id):
            raise CompileError(f"{label}.behavior_id 不合法")
        if behavior_id in behavior_ids:
            raise CompileError(f"action_behaviors.json 含重複 behavior_id: {behavior_id}")
        behavior_ids.add(behavior_id)
        if not isinstance(verb, str) or not ID_RE.match(verb):
            raise CompileError(f"{label}.verb 不合法")
        if verb in verbs:
            raise CompileError(f"action_behaviors.json 同一 verb 只能有一個 behavior: {verb}")
        verbs.add(verb)
        if not isinstance(completion_module, str) or not ID_RE.match(completion_module):
            raise CompileError(f"{label}.completion_module 不合法")
        title = behavior["title"]
        if not isinstance(title, str) or not title.strip():
            raise CompileError(f"{label}.title 必須是非空字串")
        phases: list[dict[str, Any]] = []
        execution_model: str | None = None
        entry_phase_id: str | None = None
        terminal_phase_id: str | None = None
        if source_format == ACTION_BEHAVIOR_FORMAT_V1:
            duration = behavior["duration_ticks"]
            if (
                isinstance(duration, bool)
                or not isinstance(duration, int)
                or not 1 <= duration <= ACTION_BEHAVIOR_DURATION_LIMIT
            ):
                raise CompileError(
                    f"{label}.duration_ticks 必須是 1 到 {ACTION_BEHAVIOR_DURATION_LIMIT} 的整數"
                )
        else:
            raw_phases = behavior["phases"]
            if (
                not isinstance(raw_phases, list)
                or not 2 <= len(raw_phases) <= ACTION_BEHAVIOR_PHASE_LIMIT
            ):
                raise CompileError(
                    f"{label}.phases 必須包含 2 到 {ACTION_BEHAVIOR_PHASE_LIMIT} 個 phase"
                )
            phase_ids: set[str] = set()
            condition_ids: set[str] = set()
            child_step_ids: set[str] = set()
            branch_ids: set[str] = set()
            behavior_has_branches = False
            behavior_has_split = False
            duration = 0
            for phase_index, phase in enumerate(raw_phases):
                phase_label = f"{label}.phases[{phase_index}]"
                if not isinstance(phase, dict):
                    raise CompileError(f"{phase_label} 必須是物件")
                phase_allowed = {"phase_id", "title", "duration_ticks"}
                if source_format in {
                    ACTION_BEHAVIOR_FORMAT_V3,
                    ACTION_BEHAVIOR_FORMAT_V4,
                    ACTION_BEHAVIOR_FORMAT_V5,
                    ACTION_BEHAVIOR_FORMAT_V6,
                    ACTION_BEHAVIOR_FORMAT,
                }:
                    phase_allowed.add("when")
                if source_format in {
                    ACTION_BEHAVIOR_FORMAT_V4,
                    ACTION_BEHAVIOR_FORMAT_V5,
                    ACTION_BEHAVIOR_FORMAT_V6,
                    ACTION_BEHAVIOR_FORMAT,
                }:
                    phase_allowed.add("retry")
                if source_format == ACTION_BEHAVIOR_FORMAT_V5:
                    phase_allowed.add("child_action")
                if source_format in {ACTION_BEHAVIOR_FORMAT_V6, ACTION_BEHAVIOR_FORMAT}:
                    phase_allowed.add("branches")
                phase_unknown = set(phase) - phase_allowed
                phase_missing = phase_allowed - set(phase)
                if phase_unknown:
                    raise CompileError(f"{phase_label} 含未知欄位: {sorted(phase_unknown)}")
                if phase_missing:
                    raise CompileError(f"{phase_label} 缺少必填欄位: {sorted(phase_missing)}")
                phase_id = phase["phase_id"]
                phase_title = phase["title"]
                phase_duration = phase["duration_ticks"]
                if not isinstance(phase_id, str) or not ID_RE.match(phase_id):
                    raise CompileError(f"{phase_label}.phase_id 不合法")
                if phase_id in phase_ids:
                    raise CompileError(f"{label}.phases 含重複 phase_id: {phase_id}")
                phase_ids.add(phase_id)
                if not isinstance(phase_title, str) or not phase_title.strip():
                    raise CompileError(f"{phase_label}.title 必須是非空字串")
                if (
                    isinstance(phase_duration, bool)
                    or not isinstance(phase_duration, int)
                    or not 1 <= phase_duration <= ACTION_BEHAVIOR_DURATION_LIMIT
                ):
                    raise CompileError(
                        f"{phase_label}.duration_ticks 必須是 1 到 {ACTION_BEHAVIOR_DURATION_LIMIT} 的整數"
                    )
                duration += phase_duration
                if duration > ACTION_BEHAVIOR_DURATION_LIMIT:
                    raise CompileError(
                        f"{label}.phases 總 duration 不可超過 {ACTION_BEHAVIOR_DURATION_LIMIT}"
                    )
                normalized_when: list[dict[str, Any]] = []
                if source_format in {
                    ACTION_BEHAVIOR_FORMAT_V3,
                    ACTION_BEHAVIOR_FORMAT_V4,
                    ACTION_BEHAVIOR_FORMAT_V5,
                    ACTION_BEHAVIOR_FORMAT_V6,
                    ACTION_BEHAVIOR_FORMAT,
                }:
                    raw_when = phase["when"]
                    if (
                        not isinstance(raw_when, list)
                        or len(raw_when) > ACTION_BEHAVIOR_CONDITION_LIMIT
                    ):
                        raise CompileError(
                            f"{phase_label}.when 必須是最多 {ACTION_BEHAVIOR_CONDITION_LIMIT} 個條件"
                        )
                    if phase_index == 0 and raw_when:
                        raise CompileError(f"{phase_label}.when 第一個 phase 必須為空")
                    for condition_index, condition in enumerate(raw_when):
                        condition_label = f"{phase_label}.when[{condition_index}]"
                        condition_allowed = {
                            "condition_id", "subject", "namespace", "key", "operator", "value",
                        }
                        if not isinstance(condition, dict):
                            raise CompileError(f"{condition_label} 必須是物件")
                        condition_unknown = set(condition) - condition_allowed
                        condition_missing = condition_allowed - set(condition)
                        if condition_unknown:
                            raise CompileError(
                                f"{condition_label} 含未知欄位: {sorted(condition_unknown)}"
                            )
                        if condition_missing:
                            raise CompileError(
                                f"{condition_label} 缺少必填欄位: {sorted(condition_missing)}"
                            )
                        condition_id = condition["condition_id"]
                        subject = condition["subject"]
                        namespace = condition["namespace"]
                        key = condition["key"]
                        operator = condition["operator"]
                        expected = condition["value"]
                        if not isinstance(condition_id, str) or not ID_RE.match(condition_id):
                            raise CompileError(f"{condition_label}.condition_id 不合法")
                        if condition_id in condition_ids:
                            raise CompileError(
                                f"{label} 含重複 condition_id: {condition_id}"
                            )
                        condition_ids.add(condition_id)
                        if subject not in ACTION_BEHAVIOR_CONDITION_SUBJECTS:
                            raise CompileError(f"{condition_label}.subject 不支援")
                        if namespace not in ACTION_BEHAVIOR_CONDITION_NAMESPACES:
                            raise CompileError(f"{condition_label}.namespace 不支援")
                        if not isinstance(key, str) or not ID_RE.match(key):
                            raise CompileError(f"{condition_label}.key 不合法")
                        if operator not in ACTION_BEHAVIOR_CONDITION_OPERATORS:
                            raise CompileError(f"{condition_label}.operator 不支援")
                        if not _finite_json_scalar(expected):
                            raise CompileError(f"{condition_label}.value 必須是 finite JSON scalar")
                        if operator in {
                            "less_than", "less_or_equal", "greater_than", "greater_or_equal",
                        } and (
                            isinstance(expected, bool) or not isinstance(expected, (int, float))
                        ):
                            raise CompileError(f"{condition_label}.value 數值比較必須使用 number")
                        normalized_when.append({
                            "condition_id": condition_id,
                            "subject": subject,
                            "namespace": namespace,
                            "key": key,
                            "operator": operator,
                            "value": expected,
                        })
                phase_record = {
                    "phase_id": phase_id,
                    "title": phase_title.strip(),
                    "duration_ticks": phase_duration,
                }
                if source_format in {
                    ACTION_BEHAVIOR_FORMAT_V3,
                    ACTION_BEHAVIOR_FORMAT_V4,
                    ACTION_BEHAVIOR_FORMAT_V5,
                    ACTION_BEHAVIOR_FORMAT_V6,
                    ACTION_BEHAVIOR_FORMAT,
                }:
                    phase_record["when"] = normalized_when
                if source_format in {
                    ACTION_BEHAVIOR_FORMAT_V4,
                    ACTION_BEHAVIOR_FORMAT_V5,
                    ACTION_BEHAVIOR_FORMAT_V6,
                    ACTION_BEHAVIOR_FORMAT,
                }:
                    retry = phase["retry"]
                    if phase_index == 0 and retry is not None:
                        raise CompileError(f"{phase_label}.retry is forbidden on the first phase")
                    if not normalized_when and retry is not None:
                        raise CompileError(f"{phase_label}.retry requires at least one when condition")
                    if retry is not None:
                        retry_allowed = {"max_attempts", "interval_ticks", "timeout_ticks"}
                        if not isinstance(retry, dict):
                            raise CompileError(f"{phase_label}.retry must be an object or null")
                        retry_unknown = set(retry) - retry_allowed
                        retry_missing = retry_allowed - set(retry)
                        if retry_unknown:
                            raise CompileError(
                                f"{phase_label}.retry contains unknown fields: {sorted(retry_unknown)}"
                            )
                        if retry_missing:
                            raise CompileError(
                                f"{phase_label}.retry is missing fields: {sorted(retry_missing)}"
                            )
                        max_attempts = retry["max_attempts"]
                        interval_ticks = retry["interval_ticks"]
                        timeout_ticks = retry["timeout_ticks"]
                        if (
                            isinstance(max_attempts, bool)
                            or not isinstance(max_attempts, int)
                            or not 1 <= max_attempts <= ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT
                        ):
                            raise CompileError(
                                f"{phase_label}.retry.max_attempts must be between 1 and "
                                f"{ACTION_BEHAVIOR_RETRY_ATTEMPT_LIMIT}"
                            )
                        for retry_key, retry_value in {
                            "interval_ticks": interval_ticks,
                            "timeout_ticks": timeout_ticks,
                        }.items():
                            if (
                                isinstance(retry_value, bool)
                                or not isinstance(retry_value, int)
                                or not 1 <= retry_value <= ACTION_BEHAVIOR_DURATION_LIMIT
                            ):
                                raise CompileError(
                                    f"{phase_label}.retry.{retry_key} must be between 1 and "
                                    f"{ACTION_BEHAVIOR_DURATION_LIMIT}"
                                )
                        phase_record["retry"] = {
                            "max_attempts": max_attempts,
                            "interval_ticks": interval_ticks,
                            "timeout_ticks": timeout_ticks,
                        }
                    else:
                        phase_record["retry"] = None
                if source_format == ACTION_BEHAVIOR_FORMAT_V5:
                    raw_child = phase["child_action"]
                    if phase_index == len(raw_phases) - 1 and raw_child is not None:
                        raise CompileError(
                            f"{phase_label}.child_action is forbidden on the final phase"
                        )
                    phase_record["child_action"] = _validate_action_child(
                        raw_child,
                        label=f"{phase_label}.child_action",
                        authored_verbs=authored_verbs,
                        entity_ids=entity_ids,
                        step_ids=child_step_ids,
                    )
                if source_format in {ACTION_BEHAVIOR_FORMAT_V6, ACTION_BEHAVIOR_FORMAT}:
                    raw_branches = phase["branches"]
                    if not isinstance(raw_branches, list):
                        raise CompileError(f"{phase_label}.branches must be an array")
                    if (
                        source_format == ACTION_BEHAVIOR_FORMAT_V6
                        and phase_index == len(raw_phases) - 1
                    ):
                        if raw_branches:
                            raise CompileError(
                                f"{phase_label}.branches is forbidden on the final phase"
                            )
                        phase_record["branches"] = []
                    elif raw_branches:
                        behavior_has_branches = True
                        behavior_has_split = behavior_has_split or len(raw_branches) >= 2
                        minimum_branches = (
                            1 if source_format == ACTION_BEHAVIOR_FORMAT else 2
                        )
                        if not minimum_branches <= len(raw_branches) <= ACTION_BEHAVIOR_BRANCH_LIMIT:
                            raise CompileError(
                                f"{phase_label}.branches must contain {minimum_branches} to "
                                f"{ACTION_BEHAVIOR_BRANCH_LIMIT} alternatives"
                            )
                        normalized_branches: list[dict[str, Any]] = []
                        priorities: set[int] = set()
                        fallback_count = 0
                        conditional_priorities: list[int] = []
                        fallback_priority: int | None = None
                        branch_allowed = {
                            "branch_id", "priority", "when", "child_action",
                        }
                        if source_format == ACTION_BEHAVIOR_FORMAT:
                            branch_allowed.add("next_phase_id")
                        for branch_index, branch in enumerate(raw_branches):
                            branch_label = f"{phase_label}.branches[{branch_index}]"
                            if not isinstance(branch, dict):
                                raise CompileError(f"{branch_label} must be an object")
                            unknown = set(branch) - branch_allowed
                            missing = branch_allowed - set(branch)
                            if unknown:
                                raise CompileError(
                                    f"{branch_label} contains unknown fields: {sorted(unknown)}"
                                )
                            if missing:
                                raise CompileError(
                                    f"{branch_label} is missing fields: {sorted(missing)}"
                                )
                            branch_id = branch["branch_id"]
                            priority = branch["priority"]
                            next_phase_id = branch.get("next_phase_id")
                            if not isinstance(branch_id, str) or not ID_RE.match(branch_id):
                                raise CompileError(f"{branch_label}.branch_id is invalid")
                            if branch_id in branch_ids:
                                raise CompileError(f"duplicate action branch_id: {branch_id}")
                            branch_ids.add(branch_id)
                            if (
                                isinstance(priority, bool)
                                or not isinstance(priority, int)
                                or not 0 <= priority <= ACTION_BEHAVIOR_BRANCH_PRIORITY_LIMIT
                            ):
                                raise CompileError(
                                    f"{branch_label}.priority must be between 0 and "
                                    f"{ACTION_BEHAVIOR_BRANCH_PRIORITY_LIMIT}"
                                )
                            if priority in priorities:
                                raise CompileError(
                                    f"{phase_label}.branches priorities must be unique"
                                )
                            priorities.add(priority)
                            if source_format == ACTION_BEHAVIOR_FORMAT and (
                                not isinstance(next_phase_id, str)
                                or not ID_RE.match(next_phase_id)
                            ):
                                raise CompileError(
                                    f"{branch_label}.next_phase_id is invalid"
                                )
                            branch_when = _validate_action_branch_conditions(
                                branch["when"],
                                label=f"{branch_label}.when",
                                condition_ids=condition_ids,
                            )
                            if branch_when:
                                conditional_priorities.append(priority)
                            else:
                                fallback_count += 1
                                fallback_priority = priority
                            branch_record = {
                                "branch_id": branch_id,
                                "priority": priority,
                                "when": branch_when,
                                "child_action": _validate_action_child(
                                    branch["child_action"],
                                    label=f"{branch_label}.child_action",
                                    authored_verbs=authored_verbs,
                                    entity_ids=entity_ids,
                                    step_ids=child_step_ids,
                                ),
                            }
                            if source_format == ACTION_BEHAVIOR_FORMAT:
                                branch_record["next_phase_id"] = next_phase_id
                            normalized_branches.append(branch_record)
                        if fallback_count != 1:
                            raise CompileError(
                                f"{phase_label}.branches requires exactly one unconditional fallback"
                            )
                        if conditional_priorities and fallback_priority >= min(
                            conditional_priorities
                        ):
                            raise CompileError(
                                f"{phase_label}.branches fallback must have the lowest priority"
                            )
                        normalized_branches.sort(
                            key=lambda item: (-item["priority"], item["branch_id"])
                        )
                        phase_record["branches"] = normalized_branches
                    else:
                        phase_record["branches"] = []
                phases.append(phase_record)
            if source_format == ACTION_BEHAVIOR_FORMAT_V5 and not child_step_ids:
                raise CompileError(f"{label}.phases must declare at least one child_action")
            if source_format == ACTION_BEHAVIOR_FORMAT_V6 and not behavior_has_branches:
                raise CompileError(f"{label}.phases must declare at least one branch set")
            if source_format == ACTION_BEHAVIOR_FORMAT_V6 and not child_step_ids:
                raise CompileError(f"{label}.branches must declare at least one child_action")
            if source_format == ACTION_BEHAVIOR_FORMAT:
                if not behavior_has_split:
                    raise CompileError(
                        f"{label}.phases must declare at least one conditional routing split"
                    )
                phase_by_id = {phase["phase_id"]: phase for phase in phases}
                terminal_ids = [
                    phase["phase_id"] for phase in phases if not phase["branches"]
                ]
                if len(terminal_ids) != 1:
                    raise CompileError(
                        f"{label}.phases must declare exactly one terminal phase"
                    )
                for phase in phases:
                    for branch in phase["branches"]:
                        target_id = branch["next_phase_id"]
                        if target_id not in phase_by_id:
                            raise CompileError(
                                f"{label} branch {branch['branch_id']} references unknown "
                                f"next_phase_id: {target_id}"
                            )
                        if target_id == phase["phase_id"]:
                            raise CompileError(
                                f"{label} branch {branch['branch_id']} cannot route to itself"
                            )

                entry_phase_id = phases[0]["phase_id"]
                terminal_phase_id = terminal_ids[0]
                visiting: set[str] = set()
                visited: set[str] = set()

                def visit_phase(phase_id: str) -> None:
                    if phase_id in visiting:
                        raise CompileError(f"{label}.phases routing graph contains a cycle")
                    if phase_id in visited:
                        return
                    visiting.add(phase_id)
                    for branch in phase_by_id[phase_id]["branches"]:
                        visit_phase(branch["next_phase_id"])
                    visiting.remove(phase_id)
                    visited.add(phase_id)

                visit_phase(entry_phase_id)
                unreachable = sorted(set(phase_by_id) - visited)
                if unreachable:
                    raise CompileError(
                        f"{label}.phases contains unreachable phases: {unreachable}"
                    )

                longest_cache: dict[str, int] = {}

                def longest_duration(phase_id: str) -> int:
                    cached = longest_cache.get(phase_id)
                    if cached is not None:
                        return cached
                    phase = phase_by_id[phase_id]
                    tail = max(
                        (
                            longest_duration(branch["next_phase_id"])
                            for branch in phase["branches"]
                        ),
                        default=0,
                    )
                    result = phase["duration_ticks"] + tail
                    longest_cache[phase_id] = result
                    return result

                duration = longest_duration(entry_phase_id)
                execution_model = ACTION_BEHAVIOR_EXECUTION_MODEL_STATIC_DAG
        if behavior["concurrency"] != ACTION_BEHAVIOR_CONCURRENCY:
            raise CompileError(f"{label}.concurrency 目前只支援 {ACTION_BEHAVIOR_CONCURRENCY}")
        interrupt_on = behavior["interrupt_on"]
        if (
            not isinstance(interrupt_on, list)
            or len(interrupt_on) > ACTION_BEHAVIOR_INTERRUPT_LIMIT
            or len(interrupt_on) != len(set(interrupt_on))
            or any(event_type not in ACTION_BEHAVIOR_INTERRUPT_EVENTS for event_type in interrupt_on)
        ):
            raise CompileError(
                f"{label}.interrupt_on 必須是不重複、最多 {ACTION_BEHAVIOR_INTERRUPT_LIMIT} 個受支援 EventIR"
            )
        record = {
            "behavior_id": behavior_id,
            "title": title.strip(),
            "verb": verb,
            "duration_ticks": duration,
            "completion_module": completion_module,
            "concurrency": ACTION_BEHAVIOR_CONCURRENCY,
            "interrupt_on": list(interrupt_on),
        }
        if phases:
            record["phases"] = phases
        if execution_model is not None:
            record.update({
                "execution_model": execution_model,
                "entry_phase_id": entry_phase_id,
                "terminal_phase_id": terminal_phase_id,
            })
        normalized.append(record)
    return normalized


def _validate_scoped_state_machines(
    source: Any,
    *,
    world_id: str,
    region_ids: set[str],
    room_ids: set[str],
    entity_ids: set[str],
) -> list[dict[str, Any]]:
    """Validate versioned World/Region/Scene/Entity/System StateIR.

    These machines are intentionally narrower than quests: a transition may
    select a bounded EventIR payload and priority, but it has no free-form
    guard, reward, arbitrary effect, or direct StateStore path.  Its only
    effect is changing its own ``owner::fsm::state_machine_id`` cell.
    """
    if not isinstance(source, dict):
        raise CompileError("state_machines.json 必須是物件")
    unknown_root = set(source) - {"format", "state_machines"}
    if unknown_root:
        raise CompileError(f"state_machines.json 含未知欄位: {sorted(unknown_root)}")
    if source.get("format") != "compilableworld.state-machines/v0.1":
        raise CompileError("state_machines.json format 不支援")
    machines = source.get("state_machines")
    if not isinstance(machines, list):
        raise CompileError("state_machines.json.state_machines 必須是陣列")
    if len(machines) > STATE_MACHINE_DEFINITION_LIMIT:
        raise CompileError(
            f"state_machines.json 不可超過 {STATE_MACHINE_DEFINITION_LIMIT} 台狀態機"
        )

    normalized: list[dict[str, Any]] = []
    machine_ids: set[str] = set()
    state_paths: set[tuple[str, str]] = set()
    allowed = {
        "state_machine_id", "title", "owner_scope", "owner_id", "states",
        "initial_state", "persistence", "visibility", "authority", "transitions",
    }
    required = set(allowed)
    for index, machine in enumerate(machines):
        label = f"state_machines.json.state_machines[{index}]"
        if not isinstance(machine, dict):
            raise CompileError(f"{label} 必須是物件")
        unknown = set(machine) - allowed
        if unknown:
            raise CompileError(f"{label} 含未知欄位: {sorted(unknown)}")
        missing = required - set(machine)
        if missing:
            raise CompileError(f"{label} 缺少必填欄位: {sorted(missing)}")

        machine_id = machine["state_machine_id"]
        if not isinstance(machine_id, str) or not ID_RE.match(machine_id) or machine_id == "state":
            raise CompileError(f"{label}.state_machine_id 不合法或與 legacy fsm.state 衝突")
        if machine_id in machine_ids:
            raise CompileError(f"state_machines.json 含重複 state_machine_id: {machine_id}")
        machine_ids.add(machine_id)

        title = machine["title"]
        if not isinstance(title, str) or not title.strip():
            raise CompileError(f"{label}.title 必須是非空字串")
        owner_scope = machine["owner_scope"]
        source_owner_id = machine["owner_id"]
        if owner_scope not in STATE_MACHINE_OWNER_SCOPES:
            raise CompileError(f"{label}.owner_scope 不支援: {owner_scope}")
        if not isinstance(source_owner_id, str) or not ID_RE.match(source_owner_id):
            raise CompileError(f"{label}.owner_id 不合法")
        owner_id = _resolve_state_machine_owner(
            owner_scope, source_owner_id, label,
            world_id=world_id, region_ids=region_ids,
            room_ids=room_ids, entity_ids=entity_ids,
        )
        state_path = (owner_id, machine_id)
        if state_path in state_paths:
            raise CompileError(f"{label} 與其他狀態機使用重複 StateStore path: {state_path}")
        state_paths.add(state_path)

        states = machine["states"]
        if (
            not isinstance(states, list)
            or not 2 <= len(states) <= STATE_MACHINE_STATE_LIMIT
            or any(not isinstance(state, str) or not ID_RE.match(state) for state in states)
            or len(states) != len(set(states))
        ):
            raise CompileError(
                f"{label}.states 必須是 2 到 {STATE_MACHINE_STATE_LIMIT} 個不重複合法 ID"
            )
        initial_state = machine["initial_state"]
        if initial_state not in states:
            raise CompileError(f"{label}.initial_state 不在 states 中")
        if machine["persistence"] != "runtime":
            raise CompileError(f"{label}.persistence v0.1 只支援 runtime")
        visibility = machine["visibility"]
        if visibility not in STATE_MACHINE_VISIBILITIES:
            raise CompileError(f"{label}.visibility 不支援: {visibility}")
        if machine["authority"] != "state_machine.core":
            raise CompileError(f"{label}.authority 必須是 state_machine.core")

        transitions = _validate_scoped_transitions(
            machine["transitions"], label, states=set(states), initial_state=initial_state,
        )
        normalized.append({
            "state_machine_id": machine_id,
            "title": title.strip(),
            "owner_scope": owner_scope,
            "owner_id": owner_id,
            "states": list(states),
            "initial_state": initial_state,
            "persistence": "runtime",
            "visibility": visibility,
            "authority": "state_machine.core",
            "transitions": transitions,
        })
    return normalized


def _resolve_state_machine_owner(
    owner_scope: str,
    owner_id: str,
    label: str,
    *,
    world_id: str,
    region_ids: set[str],
    room_ids: set[str],
    entity_ids: set[str],
) -> str:
    if owner_scope == "world":
        if owner_id not in {"world", world_id}:
            raise CompileError(f"{label}.owner_id 的 world scope 必須是 world 或 {world_id}")
        return world_id
    if owner_scope == "region":
        if not owner_id.startswith("region.") or owner_id not in region_ids:
            raise CompileError(f"{label}.owner_id 引用不存在 region: {owner_id}")
        return owner_id
    if owner_scope == "scene":
        if owner_id not in room_ids:
            raise CompileError(f"{label}.owner_id 引用不存在 scene/room: {owner_id}")
        return owner_id
    if owner_scope == "entity":
        if owner_id not in entity_ids:
            raise CompileError(f"{label}.owner_id 引用不存在 entity: {owner_id}")
        return owner_id
    if not owner_id.startswith("system."):
        raise CompileError(f"{label}.owner_id 的 system scope 必須以 system. 開頭")
    return owner_id


def _validate_scoped_transitions(
    transitions: Any,
    label: str,
    *,
    states: set[str],
    initial_state: str,
) -> list[dict[str, Any]]:
    if (
        not isinstance(transitions, list)
        or not 1 <= len(transitions) <= STATE_MACHINE_TRANSITION_LIMIT
    ):
        raise CompileError(
            f"{label}.transitions 必須是 1 到 {STATE_MACHINE_TRANSITION_LIMIT} 條 transition"
        )
    normalized: list[dict[str, Any]] = []
    transition_ids: set[str] = set()
    dispatches: set[tuple[str, str, int]] = set()
    allowed = {"transition_id", "from", "on", "to", "event_match", "priority"}
    required = {"transition_id", "from", "on", "to"}
    for index, transition in enumerate(transitions):
        transition_label = f"{label}.transitions[{index}]"
        if not isinstance(transition, dict):
            raise CompileError(f"{transition_label} 必須是物件")
        unknown = set(transition) - allowed
        if unknown:
            raise CompileError(f"{transition_label} 含未知欄位: {sorted(unknown)}")
        missing = required - set(transition)
        if missing:
            raise CompileError(f"{transition_label} 缺少必填欄位: {sorted(missing)}")

        transition_id = transition["transition_id"]
        from_state = transition["from"]
        event_type = transition["on"]
        to_state = transition["to"]
        priority = transition.get("priority", 0)
        if not isinstance(transition_id, str) or not ID_RE.match(transition_id):
            raise CompileError(f"{transition_label}.transition_id 不合法")
        if transition_id in transition_ids:
            raise CompileError(f"{label}.transitions 含重複 transition_id: {transition_id}")
        transition_ids.add(transition_id)
        if from_state not in states or to_state not in states or from_state == to_state:
            raise CompileError(f"{transition_label}.from/to 不在 states 中或未改變狀態")
        if from_state in {"completed", "failed"}:
            raise CompileError(f"{transition_label} 不可從終態 {from_state} 再轉移")
        if event_type not in STATE_MACHINE_TRIGGER_EVENT_FIELDS:
            raise CompileError(f"{transition_label}.on 不在 StateMachineModule EventIR 白名單中")
        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
            or not 0 <= priority <= STATE_MACHINE_PRIORITY_LIMIT
        ):
            raise CompileError(
                f"{transition_label}.priority 必須是 0 到 {STATE_MACHINE_PRIORITY_LIMIT} 的整數"
            )
        dispatch = (from_state, event_type, priority)
        if dispatch in dispatches:
            raise CompileError(
                f"{label}.transitions 的 from/on/priority 不可重複: {dispatch}"
            )
        dispatches.add(dispatch)

        event_match = transition.get("event_match", {})
        if not isinstance(event_match, dict):
            raise CompileError(f"{transition_label}.event_match 必須是物件")
        if len(event_match) > STATE_MACHINE_EVENT_MATCH_LIMIT:
            raise CompileError(
                f"{transition_label}.event_match 不可超過 {STATE_MACHINE_EVENT_MATCH_LIMIT} 個欄位"
            )
        unknown_match = set(event_match) - STATE_MACHINE_TRIGGER_EVENT_FIELDS[event_type]
        if unknown_match:
            raise CompileError(
                f"{transition_label}.event_match 含不屬於 {event_type} 的欄位: {sorted(unknown_match)}"
            )
        if any(not _json_scalar(value) for value in event_match.values()):
            raise CompileError(f"{transition_label}.event_match 值必須是 finite JSON 純量")
        normalized.append({
            "transition_id": transition_id,
            "from": from_state,
            "on": event_type,
            "to": to_state,
            "event_match": dict(event_match),
            "priority": priority,
        })

    _validate_transition_reachability(initial_state, normalized, label)
    reachable = {initial_state}
    changed = True
    while changed:
        changed = False
        for transition in normalized:
            if transition["from"] in reachable and transition["to"] not in reachable:
                reachable.add(transition["to"])
                changed = True
    unreachable_states = states - reachable
    if unreachable_states:
        raise CompileError(
            f"{label}.states 含從 initial_state 不可達狀態: {sorted(unreachable_states)}"
        )
    return normalized


def _validate_quests(
    quests: Any,
    *,
    room_ids: set[str],
    item_ids: set[str],
    entity_types: dict[str, str],
) -> list[dict[str, Any]]:
    """Validate both the legacy one-step quest form and v0.1 transitions.

    A quest with no ``transitions`` keeps the original ``requirements`` plus
    root ``reward`` semantics. A quest with transitions has an explicit
    state-machine edge for each EventIR trigger; it cannot mix the legacy
    root requirements/reward fields, so authors never have to infer which
    mechanism owns a state change.
    """
    if not isinstance(quests, list):
        raise CompileError("quests.json 必須是陣列")
    normalized: list[dict[str, Any]] = []
    quest_ids: set[str] = set()
    for index, quest in enumerate(quests):
        label = f"quests.json[{index}]"
        if not isinstance(quest, dict):
            raise CompileError(f"{label} 必須是物件")
        quest_id = quest.get("quest_id")
        title = quest.get("title")
        initial_state = quest.get("initial_state")
        if not isinstance(quest_id, str) or not ID_RE.match(quest_id):
            raise CompileError(f"{label}.quest_id 不合法")
        if quest_id in quest_ids:
            raise CompileError(f"quests.json 含重複 quest_id: {quest_id}")
        quest_ids.add(quest_id)
        if not isinstance(title, str) or not title.strip():
            raise CompileError(f"{label}.title 必須是非空字串")
        if not isinstance(initial_state, str) or not ID_RE.match(initial_state):
            raise CompileError(f"{label}.initial_state 不合法")

        compiled = dict(quest)
        if "transitions" in quest:
            if "requirements" in quest or "reward" in quest:
                raise CompileError(f"任務 {quest_id} 使用 transitions 時，requirements 與 reward 必須寫在各 transition 內")
            compiled["transitions"] = _validate_quest_transitions(
                quest["transitions"], label, initial_state=initial_state, room_ids=room_ids,
                item_ids=item_ids, entity_types=entity_types,
            )
        else:
            compiled["requirements"] = _validate_requirements(
                quest.get("requirements", []), label,
                room_ids=room_ids, item_ids=item_ids, entity_types=entity_types,
            )
            reward = quest.get("reward")
            if reward is not None:
                compiled["reward"] = _validate_reward(reward, label)
        normalized.append(compiled)
    return normalized


def _validate_quest_transitions(
    transitions: Any,
    label: str,
    *,
    initial_state: str,
    room_ids: set[str],
    item_ids: set[str],
    entity_types: dict[str, str],
) -> list[dict[str, Any]]:
    if not isinstance(transitions, list) or not transitions:
        raise CompileError(f"{label}.transitions 必須是非空陣列")
    normalized: list[dict[str, Any]] = []
    transition_ids: set[str] = set()
    dispatches: set[tuple[str, str, int]] = set()
    allowed = {"transition_id", "from", "on", "to", "event_match", "requirements", "reward", "priority"}
    required = {"transition_id", "from", "on", "to"}
    for index, transition in enumerate(transitions):
        transition_label = f"{label}.transitions[{index}]"
        if not isinstance(transition, dict):
            raise CompileError(f"{transition_label} 必須是物件")
        unknown = set(transition) - allowed
        if unknown:
            raise CompileError(f"{transition_label} 含未知欄位: {sorted(unknown)}")
        if not required.issubset(transition):
            raise CompileError(f"{transition_label} 缺少必填欄位: {sorted(required - set(transition))}")
        transition_id = transition["transition_id"]
        from_state = transition["from"]
        event_type = transition["on"]
        to_state = transition["to"]
        priority = transition.get("priority", 0)
        if not isinstance(transition_id, str) or not ID_RE.match(transition_id):
            raise CompileError(f"{transition_label}.transition_id 不合法")
        if transition_id in transition_ids:
            raise CompileError(f"{label}.transitions 含重複 transition_id: {transition_id}")
        transition_ids.add(transition_id)
        if not isinstance(from_state, str) or not ID_RE.match(from_state):
            raise CompileError(f"{transition_label}.from 不合法")
        if not isinstance(to_state, str) or not ID_RE.match(to_state) or to_state == from_state:
            raise CompileError(f"{transition_label}.to 不合法或未改變狀態")
        if from_state in {"completed", "failed"}:
            raise CompileError(f"{transition_label} 不可從終態 {from_state} 再轉移")
        if not isinstance(event_type, str) or event_type not in QUEST_TRIGGER_EVENT_FIELDS:
            raise CompileError(f"{transition_label}.on 不在 QuestModule 支援的 EventIR 白名單中")
        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
            or not 0 <= priority <= STATE_MACHINE_PRIORITY_LIMIT
        ):
            raise CompileError(
                f"{transition_label}.priority 必須是 0 到 {STATE_MACHINE_PRIORITY_LIMIT} 的整數"
            )
        dispatch = (from_state, event_type, priority)
        if dispatch in dispatches:
            raise CompileError(f"{label}.transitions 的 from/on/priority 不可重複，否則會有未解決分支衝突: {dispatch}")
        dispatches.add(dispatch)

        event_match = transition.get("event_match", {})
        if not isinstance(event_match, dict):
            raise CompileError(f"{transition_label}.event_match 必須是物件")
        if len(event_match) > STATE_MACHINE_EVENT_MATCH_LIMIT:
            raise CompileError(
                f"{transition_label}.event_match 不可超過 {STATE_MACHINE_EVENT_MATCH_LIMIT} 個欄位"
            )
        unknown_match = set(event_match) - QUEST_TRIGGER_EVENT_FIELDS[event_type]
        if unknown_match:
            raise CompileError(f"{transition_label}.event_match 含不屬於 {event_type} 的欄位: {sorted(unknown_match)}")
        for key, value in event_match.items():
            if not _json_scalar(value):
                raise CompileError(f"{transition_label}.event_match.{key} 必須是 JSON 純量")

        requirements = _validate_requirements(
            transition.get("requirements", []), transition_label,
            room_ids=room_ids, item_ids=item_ids, entity_types=entity_types,
        )
        reward = transition.get("reward")
        if reward is not None and to_state != "completed":
            raise CompileError(f"{transition_label}.reward 只允許出現在轉入 completed 的 transition")
        normalized_transition: dict[str, Any] = {
            "transition_id": transition_id,
            "from": from_state,
            "on": event_type,
            "to": to_state,
            "event_match": dict(event_match),
            "requirements": requirements,
            "priority": priority,
        }
        if reward is not None:
            normalized_transition["reward"] = _validate_reward(reward, transition_label)
        normalized.append(normalized_transition)
    _validate_transition_reachability(initial_state, normalized, label)
    return normalized


def _validate_transition_reachability(
    initial_state: str, transitions: list[dict[str, Any]], label: str,
) -> None:
    """Reject structurally unreachable authored branches.

    Conditions are intentionally ignored here: this proves graph reachability,
    not that a particular world playthrough can satisfy every branch.  A
    transition whose source can never be reached from the declared initial
    state is almost always stale authoring data and must not rely on source
    order or a future direct state mutation to become executable.
    """
    reachable = {initial_state}
    changed = True
    while changed:
        changed = False
        for transition in transitions:
            if transition["from"] in reachable and transition["to"] not in reachable:
                reachable.add(transition["to"])
                changed = True
    unreachable = [
        transition["transition_id"]
        for transition in transitions
        if transition["from"] not in reachable
    ]
    if unreachable:
        raise CompileError(
            f"{label}.transitions 含從 initial_state 不可達的分支: {sorted(unreachable)}"
        )


def _validate_requirements(
    requirements: Any,
    label: str,
    *,
    room_ids: set[str],
    item_ids: set[str],
    entity_types: dict[str, str],
) -> list[str]:
    if not isinstance(requirements, list):
        raise CompileError(f"{label}.requirements 必須是陣列")
    if len(requirements) > STATE_MACHINE_REQUIREMENT_LIMIT:
        raise CompileError(
            f"{label}.requirements 不可超過 {STATE_MACHINE_REQUIREMENT_LIMIT} 條"
        )
    normalized: list[str] = []
    for index, requirement in enumerate(requirements):
        requirement_label = f"{label}.requirements[{index}]"
        if not isinstance(requirement, str):
            raise CompileError(f"{requirement_label} 必須是字串")
        parts = requirement.split(":")
        if parts[0] == "deliver" and len(parts) == 3:
            _, item_id, target_id = parts
            if item_id not in item_ids:
                raise CompileError(f"{requirement_label} 引用不存在物品: {item_id}")
            if target_id not in entity_types or entity_types[target_id] not in {"character", "creature"}:
                raise CompileError(f"{requirement_label} 引用不存在或不可交付的對象: {target_id}")
        elif parts[0] == "reach" and len(parts) == 2:
            if parts[1] not in room_ids:
                raise CompileError(f"{requirement_label} 引用不存在房間: {parts[1]}")
        else:
            raise CompileError(f"{requirement_label} 使用未知或格式錯誤的 requirement")
        normalized.append(requirement)
    return normalized


def _validate_reward(reward: Any, label: str) -> dict[str, Any]:
    if not isinstance(reward, dict):
        raise CompileError(f"{label}.reward 必須是物件")
    unknown = set(reward) - {"currency"}
    if unknown:
        raise CompileError(f"{label}.reward 只支援 currency: {sorted(unknown)}")
    currency = reward.get("currency", 0)
    if (
        isinstance(currency, bool)
        or not isinstance(currency, int)
        or not 0 <= currency <= STATE_MACHINE_REWARD_CURRENCY_LIMIT
    ):
        raise CompileError(
            f"{label}.reward.currency 必須是 0 到 {STATE_MACHINE_REWARD_CURRENCY_LIMIT} 的整數"
        )
    return {"currency": currency}


def _validate_narrative(narrative: Any, room_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Validate the v0.1 read-only room-overlay grammar at compile time.

    Keeping the grammar deliberately narrow makes the authoring contract
    inspectable and lets ``room.core`` declare every state namespace it reads.
    New projection kinds can be added as separate, versioned compiler rules.
    """
    if not isinstance(narrative, dict):
        raise CompileError("narrative.json 必須是物件")
    unknown = set(narrative) - {"room_overlays"}
    if unknown:
        raise CompileError(f"narrative.json 含未知欄位: {sorted(unknown)}")
    overlays = narrative.get("room_overlays", [])
    if not isinstance(overlays, list):
        raise CompileError("narrative.room_overlays 必須是陣列")

    normalized: list[dict[str, Any]] = []
    for index, overlay in enumerate(overlays):
        label = f"narrative.room_overlays[{index}]"
        if not isinstance(overlay, dict):
            raise CompileError(f"{label} 必須是物件")
        unknown_overlay = set(overlay) - {"room_id", "when", "text", "mode"}
        if unknown_overlay:
            raise CompileError(f"{label} 含未知欄位: {sorted(unknown_overlay)}")
        room_id = overlay.get("room_id")
        text = overlay.get("text")
        when = overlay.get("when")
        mode = overlay.get("mode", "append")
        if not isinstance(room_id, str) or room_id not in room_ids:
            raise CompileError(f"{label}.room_id 引用不存在房間")
        if not isinstance(text, str) or not text.strip():
            raise CompileError(f"{label}.text 必須是非空字串")
        if mode not in {"append", "replace"}:
            raise CompileError(f"{label}.mode 必須是 append 或 replace")
        if not isinstance(when, list) or not when:
            raise CompileError(f"{label}.when 必須是非空陣列")

        conditions = _validate_state_conditions(when, label, allowed_variables={"$actor"})
        normalized.append({"room_id": room_id, "when": conditions, "text": text, "mode": mode})
    return {"room_overlays": normalized}


def _validate_dialogues(dialogues: Any, entity_types: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """Validate authored, read-only NPC dialogue variants.

    A dialogue script is deliberately not a state machine. It is a
    deterministic projection of the current state for one nearby speaker.
    ``when`` may be empty for a fallback; otherwise it uses the same
    inspectable StateStore condition grammar as room overlays, plus
    ``$speaker`` for the addressed NPC. Selection occurs in the Runtime and
    never creates a StateDelta by itself.
    """
    if not isinstance(dialogues, dict):
        raise CompileError("dialogues.json 必須是物件")
    unknown = set(dialogues) - {"dialogues"}
    if unknown:
        raise CompileError(f"dialogues.json 含未知欄位: {sorted(unknown)}")
    entries = dialogues.get("dialogues", [])
    if not isinstance(entries, list):
        raise CompileError("dialogues.dialogues 必須是陣列")

    normalized: list[dict[str, Any]] = []
    dialogue_ids: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"dialogues.dialogues[{index}]"
        if not isinstance(entry, dict):
            raise CompileError(f"{label} 必須是物件")
        required = {"dialogue_id", "speaker_id", "topic", "when", "text"}
        unknown_entry = set(entry) - required
        if unknown_entry:
            raise CompileError(f"{label} 含未知欄位: {sorted(unknown_entry)}")
        if set(entry) != required:
            raise CompileError(f"{label} 必須剛好包含 dialogue_id、speaker_id、topic、when、text")
        dialogue_id = entry["dialogue_id"]
        speaker_id = entry["speaker_id"]
        topic = entry["topic"]
        text = entry["text"]
        if not isinstance(dialogue_id, str) or not ID_RE.match(dialogue_id):
            raise CompileError(f"{label}.dialogue_id 不合法")
        if dialogue_id in dialogue_ids:
            raise CompileError(f"dialogues.json 含重複 dialogue_id: {dialogue_id}")
        dialogue_ids.add(dialogue_id)
        if not isinstance(speaker_id, str) or speaker_id not in entity_types:
            raise CompileError(f"{label}.speaker_id 引用不存在說話者")
        if entity_types[speaker_id] not in {"character", "creature"}:
            raise CompileError(f"{label}.speaker_id 必須是 character 或 creature")
        if not isinstance(topic, str) or not ID_RE.match(topic):
            raise CompileError(f"{label}.topic 不合法")
        if not isinstance(text, str) or not text.strip():
            raise CompileError(f"{label}.text 必須是非空字串")
        if not isinstance(entry["when"], list):
            raise CompileError(f"{label}.when 必須是陣列")
        conditions = _validate_state_conditions(entry["when"], label, allowed_variables={"$actor", "$speaker"})
        normalized.append({
            "dialogue_id": dialogue_id,
            "speaker_id": speaker_id,
            "topic": topic,
            "when": conditions,
            "text": text,
        })
    return {"dialogues": normalized}


def _validate_scenarios(
    scenarios: Any,
    *,
    label: str,
    world_id: str,
    entity_ids: set[str],
    item_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Validate portable Given/When/Then scenarios for Studio and Runtime."""
    if not isinstance(scenarios, dict):
        raise CompileError(f"{label} 必須是物件")
    unknown = set(scenarios) - {"scenarios"}
    if unknown:
        raise CompileError(f"{label} 含未知欄位: {sorted(unknown)}")
    entries = scenarios.get("scenarios", [])
    if not isinstance(entries, list):
        raise CompileError(f"{label}.scenarios 必須是陣列")

    known_entities = set(entity_ids)
    known_targets = entity_ids | item_ids
    known_state_owners = known_targets | {world_id}
    normalized: list[dict[str, Any]] = []
    scenario_ids: set[str] = set()

    def validate_state_assertions(raw: Any, assertion_label: str) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            raise CompileError(f"{assertion_label} 必須是陣列")
        assertions: list[dict[str, Any]] = []
        for assertion_index, assertion in enumerate(raw):
            path = f"{assertion_label}[{assertion_index}]"
            required = {"owner", "namespace", "key", "equals"}
            if not isinstance(assertion, dict) or set(assertion) != required:
                raise CompileError(f"{path} 必須剛好包含 owner、namespace、key、equals")
            owner = assertion["owner"]
            namespace = assertion["namespace"]
            key = assertion["key"]
            expected = assertion["equals"]
            if not isinstance(owner, str) or (owner != "$actor" and owner not in known_state_owners):
                raise CompileError(f"{path}.owner 必須是 $actor 或已知實體/物品/世界 ID")
            if not isinstance(namespace, str) or namespace not in STATE_CONDITION_READ_NAMESPACES:
                raise CompileError(f"{path}.namespace 不在狀態唯讀白名單中")
            if not isinstance(key, str) or not ID_RE.match(key):
                raise CompileError(f"{path}.key 不合法")
            if not _json_scalar(expected):
                raise CompileError(f"{path}.equals 必須是 JSON 純量")
            assertions.append({"owner": owner, "namespace": namespace, "key": key, "equals": expected})
        return assertions

    for index, entry in enumerate(entries):
        entry_label = f"{label}.scenarios[{index}]"
        if not isinstance(entry, dict):
            raise CompileError(f"{entry_label} 必須是物件")
        allowed = {"scenario_id", "title", "actor_id", "given", "when", "expect", "tags"}
        unknown_entry = set(entry) - allowed
        if unknown_entry:
            raise CompileError(f"{entry_label} 含未知欄位: {sorted(unknown_entry)}")
        scenario_id = entry.get("scenario_id")
        title = entry.get("title")
        if not isinstance(scenario_id, str) or not ID_RE.match(scenario_id):
            raise CompileError(f"{entry_label}.scenario_id 不合法")
        if scenario_id in scenario_ids:
            raise CompileError(f"{label} 含重複 scenario_id: {scenario_id}")
        scenario_ids.add(scenario_id)
        if not isinstance(title, str) or not title.strip():
            raise CompileError(f"{entry_label}.title 必須是非空字串")

        actor_id = entry.get("actor_id")
        if actor_id is not None and (not isinstance(actor_id, str) or actor_id not in known_entities):
            raise CompileError(f"{entry_label}.actor_id 必須引用已知 entity")
        given = validate_state_assertions(entry.get("given", []), f"{entry_label}.given")
        actions = entry.get("when")
        if not isinstance(actions, list) or not actions:
            raise CompileError(f"{entry_label}.when 必須是非空陣列")
        normalized_actions: list[dict[str, Any]] = []
        for action_index, action in enumerate(actions):
            action_label = f"{entry_label}.when[{action_index}]"
            if not isinstance(action, dict):
                raise CompileError(f"{action_label} 必須是物件")
            allowed_action = {"verb", "actor", "target_id", "args", "delay"}
            unknown_action = set(action) - allowed_action
            if unknown_action:
                raise CompileError(f"{action_label} 含未知欄位: {sorted(unknown_action)}")
            verb = action.get("verb")
            actor = action.get("actor", "$actor")
            target_id = action.get("target_id")
            args = action.get("args", {})
            delay = action.get("delay", 0)
            if not isinstance(verb, str) or not ID_RE.match(verb):
                raise CompileError(f"{action_label}.verb 不合法")
            if not isinstance(actor, str) or (actor != "$actor" and actor not in known_entities):
                raise CompileError(f"{action_label}.actor 必須是 $actor 或已知 entity")
            if target_id is not None and (not isinstance(target_id, str) or target_id not in known_targets):
                raise CompileError(f"{action_label}.target_id 必須引用已知 entity 或 item")
            if not isinstance(args, dict) or not _json_value(args):
                raise CompileError(f"{action_label}.args 必須是 JSON 物件")
            if isinstance(delay, bool) or not isinstance(delay, int) or delay < 0:
                raise CompileError(f"{action_label}.delay 必須是非負整數")
            normalized_actions.append({
                "verb": verb, "actor": actor, "target_id": target_id,
                "args": dict(args), "delay": delay,
            })

        expect = entry.get("expect")
        if not isinstance(expect, dict):
            raise CompileError(f"{entry_label}.expect 必須是物件")
        unknown_expect = set(expect) - {"state", "events", "status"}
        if unknown_expect:
            raise CompileError(f"{entry_label}.expect 含未知欄位: {sorted(unknown_expect)}")
        expected_state = validate_state_assertions(expect.get("state", []), f"{entry_label}.expect.state")
        expected_events = expect.get("events", [])
        if not isinstance(expected_events, list) or any(not isinstance(event, str) or not ID_RE.match(event) for event in expected_events):
            raise CompileError(f"{entry_label}.expect.events 必須是合法事件 ID 陣列")
        expected_status = expect.get("status", "completed")
        if expected_status not in {"completed", "failed"}:
            raise CompileError(f"{entry_label}.expect.status 只能是 completed 或 failed")
        tags = entry.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) or not ID_RE.match(tag) for tag in tags):
            raise CompileError(f"{entry_label}.tags 必須是合法 ID 陣列")
        normalized.append({
            "scenario_id": scenario_id,
            "title": title,
            "actor_id": actor_id,
            "given": given,
            "when": normalized_actions,
            "expect": {"state": expected_state, "events": list(expected_events), "status": expected_status},
            "tags": list(tags),
        })
    return {"scenarios": normalized}


def _validate_state_conditions(
    conditions: list[Any], label: str, *, allowed_variables: set[str],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for condition_index, condition in enumerate(conditions):
        condition_label = f"{label}.when[{condition_index}]"
        if not isinstance(condition, dict):
            raise CompileError(f"{condition_label} 必須是物件")
        unknown_condition = set(condition) - {"owner", "namespace", "key", "equals"}
        if unknown_condition:
            raise CompileError(f"{condition_label} 含未知欄位: {sorted(unknown_condition)}")
        required = {"owner", "namespace", "key", "equals"}
        if set(condition) != required:
            raise CompileError(f"{condition_label} 必須剛好包含 owner、namespace、key、equals")
        owner = condition["owner"]
        namespace = condition["namespace"]
        key = condition["key"]
        expected = condition["equals"]
        if not isinstance(owner, str) or (owner not in allowed_variables and not ID_RE.match(owner)):
            raise CompileError(f"{condition_label}.owner 不合法")
        if not isinstance(namespace, str) or namespace not in STATE_CONDITION_READ_NAMESPACES:
            raise CompileError(f"{condition_label}.namespace 不在狀態條件唯讀白名單中")
        if not isinstance(key, str) or not ID_RE.match(key):
            raise CompileError(f"{condition_label}.key 不合法")
        if not _json_scalar(expected):
            raise CompileError(f"{condition_label}.equals 必須是 JSON 純量")
        normalized.append({"owner": owner, "namespace": namespace, "key": key, "equals": expected})
    return normalized


def _json_scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, (str, int, bool))
        or (isinstance(value, float) and math.isfinite(value))
    )


def _json_value(value: Any) -> bool:
    if _json_scalar(value):
        return True
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _validate_reachability(room_ids: set[str], exits: list[dict[str, str]], spawn: str) -> None:
    graph: dict[str, set[str]] = {room: set() for room in room_ids}
    for edge in exits:
        graph[edge["from_room"]].add(edge["to_room"])
        if _bool(edge.get("bidirectional", "false")):
            graph[edge["to_room"]].add(edge["from_room"])
    seen = {spawn}
    queue = deque([spawn])
    while queue:
        current = queue.popleft()
        for target in graph[current] - seen:
            seen.add(target)
            queue.append(target)
    unreachable = room_ids - seen
    if unreachable:
        raise CompileError(f"從出生點不可達房間: {sorted(unreachable)}")
