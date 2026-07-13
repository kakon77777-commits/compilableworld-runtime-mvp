from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import deque
from pathlib import Path
from typing import Any


ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
ATTRIBUTE_COLUMNS = ("str", "con", "mag", "agi", "dex")


class CompileError(ValueError):
    pass


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompileError(f"無法讀取 JSON {path}: {exc}") from exc


def _load_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise CompileError(f"CSV 標題缺失或重複: {path}")
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
    present = [attr for attr in ATTRIBUTE_COLUMNS if row.get(attr, "").strip()]
    if present and len(present) != len(ATTRIBUTE_COLUMNS):
        missing = [attr for attr in ATTRIBUTE_COLUMNS if attr not in present]
        raise CompileError(f"實體 {row.get('entity_id')} 只填了部分戰鬥屬性，缺少: {', '.join(missing)}")
    if present and row.get("health", "").strip():
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


def compile_world(source_dir: str | Path, output_dir: str | Path) -> Path:
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
    world = _load_json(resolved["world"])
    rooms = _load_csv(resolved["rooms"])
    exits = _load_csv(resolved["exits"])
    entities = _load_csv(resolved["entities"])
    items = _load_csv(resolved["items"])
    quests = _load_json(resolved["quests"])

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
    exit_ids = _unique(exits, "exit_id", "exits.csv")
    entity_ids = _unique(entities, "entity_id", "entities.csv")
    item_ids = _unique(items, "item_id", "items.csv")
    del exit_ids
    overlap = entity_ids & item_ids
    if overlap:
        raise CompileError(f"entity/item ID 衝突: {sorted(overlap)}")
    if not isinstance(quests, list):
        raise CompileError("quests.json 必須是陣列")
    for quest in quests:
        if not isinstance(quest, dict):
            raise CompileError("quests.json 的每筆任務必須是物件")
        _required(quest, ["quest_id", "title", "initial_state"], "quests.json")
        reward = quest.get("reward")
        if reward is not None:
            if not isinstance(reward, dict) or not isinstance(reward.get("currency", 0), int):
                raise CompileError(f"任務 {quest['quest_id']} 的 reward.currency 必須是整數")
    _unique(quests, "quest_id", "quests.json")

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
        if row.get("con", "").strip():
            for attr in ATTRIBUTE_COLUMNS:
                initial_state.append(_state(row["entity_id"], "combat", attr, int(row[attr])))
            if row.get("phase_tier", "").strip():
                initial_state.append(_state(row["entity_id"], "combat", "phase_tier", int(row["phase_tier"])))
            health = int(row["con"]) * 8
            initial_state.extend([
                _state(row["entity_id"], "health", "current", health),
                _state(row["entity_id"], "health", "max", health),
                _state(row["entity_id"], "status", "alive", True),
            ])
        elif row.get("health", "").strip():
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

    for owner, state_name in world.get("world_state_machines", {}).items():
        state_owner = manifest["world_id"] if owner == "world" else owner
        initial_state.append(_state(state_owner, "fsm", "state", state_name))
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
    package = {
        "format": "compilableworld.runtime-package/v0.1",
        "manifest": {
            "world_id": manifest["world_id"], "world_version": manifest["world_version"],
            "schema_version": manifest["schema_version"], "namespace": manifest["namespace"],
            "runtime_version": "0.1.0", "modules": modules,
        },
        "world": world,
        "rooms": rooms,
        "exits": exits,
        "entities": compiled_entities,
        "quests": quests,
        "initial_state": initial_state,
        "source_checksums": {
            str(path.relative_to(root)): _sha256(path)
            for path in [manifest_path, *resolved.values()]
        },
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    package_path = out / "world.package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = {
        "ok": True, "world_id": manifest["world_id"], "rooms": len(rooms),
        "exits": len(exits), "entities": len(compiled_entities), "states": len(initial_state),
        "modules": modules, "package_sha256": _sha256(package_path),
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
