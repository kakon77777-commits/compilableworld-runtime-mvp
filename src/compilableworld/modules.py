from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .kernel import WorldRuntime
from .models import ActionIR, EventIR, ModuleContract, StateDelta, TransitionResult


@dataclass
class BaseModule:
    contract: ModuleContract

    def event(self, event_type: str, action: ActionIR, payload: dict[str, Any], target: str | None = None) -> EventIR:
        return EventIR(event_type, self.contract.module_id, payload, target=target or action.actor_id)


class RoomModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("room.core", "0.1.0", "TMS", ["look"], ["room.observed"], ["position.*"], [], ["entity", "state", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        room_id = runtime.state.get(action.actor_id, "position", "room")
        room = next((r for r in runtime.package["rooms"] if r["room_id"] == room_id), None)
        if not room:
            return TransitionResult(False, message="目前位置不存在")
        visible = [e.entity_id for e in runtime.registry.values() if runtime.state.get(e.entity_id, "position", "room") == room_id and e.entity_id != action.actor_id]
        return TransitionResult(True, events=[self.event("room.observed", action, {"room_id": room_id, "visible": visible})], message=room["description"])


class MovementModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("movement.core", "0.1.0", "TMS", ["move"], ["movement.actor_moved"], ["position.*", "door.*"], ["position.*"], ["entity", "state", "action", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        current = runtime.state.get(action.actor_id, "position", "room")
        direction = str(action.args.get("direction", "")).lower()
        edge = _find_exit(runtime.package["exits"], current, direction)
        if edge is None:
            return TransitionResult(False, message=f"此處無法往 {direction} 移動")
        door = edge.get("door_entity", "").strip()
        if door and runtime.state.get(door, "door", "locked", False):
            return TransitionResult(False, message="門被鎖住了")
        if door and not runtime.state.get(door, "door", "open", False):
            return TransitionResult(False, message="門尚未打開")
        target = _exit_target(edge, current)
        delta = StateDelta(action.actor_id, "position", "room", "set", target, source_module=self.contract.module_id)
        event = self.event("movement.actor_moved", action, {"from": current, "to": target, "direction": direction})
        return TransitionResult(True, [delta], [event], f"你往 {direction} 移動。")


class DoorModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("door.core", "0.1.0", "TMS", ["open", "unlock"], ["door.opened", "door.unlocked"], ["position.*", "door.*", "inventory.*"], ["door.*"], ["entity", "state", "action", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        door = action.target_id
        if not door or not runtime.registry.contains(door):
            return TransitionResult(False, message="找不到門")
        actor_room = runtime.state.get(action.actor_id, "position", "room")
        door_room = runtime.state.get(door, "position", "room")
        if actor_room != door_room:
            return TransitionResult(False, message="門不在目前場景")
        if action.verb == "unlock":
            if not runtime.state.get(door, "door", "locked", False):
                return TransitionResult(False, message="門沒有上鎖")
            key = runtime.state.get(door, "door", "key_id")
            if key and runtime.state.get(key, "inventory", "carrier") != action.actor_id:
                return TransitionResult(False, message="你沒有正確的鑰匙")
            return TransitionResult(True, [StateDelta(door, "door", "locked", "set", False, source_module=self.contract.module_id)], [self.event("door.unlocked", action, {"door": door}, door)], "你解開了門鎖。")
        if runtime.state.get(door, "door", "locked", False):
            return TransitionResult(False, message="門被鎖住了")
        if runtime.state.get(door, "door", "open", False):
            return TransitionResult(False, message="門已經開著")
        return TransitionResult(True, [StateDelta(door, "door", "open", "set", True, source_module=self.contract.module_id)], [self.event("door.opened", action, {"door": door}, door)], "你打開了門。")


class InventoryModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("inventory.core", "0.1.0", "TMS", ["take", "drop", "inventory"], ["inventory.item_added", "inventory.item_removed", "inventory.observed"], ["position.*", "inventory.*"], ["position.*", "inventory.*"], ["entity", "state", "action", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        if action.verb == "inventory":
            items = [e.entity_id for e in runtime.registry.values() if runtime.state.get(e.entity_id, "inventory", "carrier") == action.actor_id]
            return TransitionResult(True, events=[self.event("inventory.observed", action, {"items": items})], message="物品欄: " + (", ".join(items) or "空"))
        item = action.target_id
        if not item or not runtime.registry.contains(item) or runtime.registry.get(item).entity_type != "item":
            return TransitionResult(False, message="找不到物品")
        room = runtime.state.get(action.actor_id, "position", "room")
        if action.verb == "take":
            if not runtime.registry.get(item).metadata.get("portable", False):
                return TransitionResult(False, message="該物品不可攜帶")
            if runtime.state.get(item, "position", "room") != room:
                return TransitionResult(False, message="物品不在此處")
            deltas = [
                StateDelta(item, "position", "room", "set", None, source_module=self.contract.module_id),
                StateDelta(item, "inventory", "carrier", "set", action.actor_id, source_module=self.contract.module_id),
            ]
            return TransitionResult(True, deltas, [self.event("inventory.item_added", action, {"item": item})], f"你拿起了 {runtime.registry.get(item).name}。")
        if runtime.state.get(item, "inventory", "carrier") != action.actor_id:
            return TransitionResult(False, message="物品不在你的物品欄")
        deltas = [
            StateDelta(item, "inventory", "carrier", "set", None, source_module=self.contract.module_id),
            StateDelta(item, "position", "room", "set", room, source_module=self.contract.module_id),
        ]
        return TransitionResult(True, deltas, [self.event("inventory.item_removed", action, {"item": item})], f"你放下了 {runtime.registry.get(item).name}。")


class HealthModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("health.core", "0.1.0", "TMS", ["status"], ["health.observed"], ["health.*", "status.*"], [], ["entity", "state", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        current = runtime.state.get(action.actor_id, "health", "current")
        maximum = runtime.state.get(action.actor_id, "health", "max")
        return TransitionResult(True, events=[self.event("health.observed", action, {"current": current, "max": maximum})], message=f"生命值: {current}/{maximum}")


class CombatModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("combat.basic", "0.1.0", "TMS", ["attack"], ["combat.damage_applied", "combat.actor_defeated"], ["position.*", "health.*", "status.*"], ["health.*", "status.*"], ["entity", "state", "action", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        target = action.target_id
        if not target or not runtime.registry.contains(target):
            return TransitionResult(False, message="攻擊目標不存在")
        if runtime.state.get(action.actor_id, "position", "room") != runtime.state.get(target, "position", "room"):
            return TransitionResult(False, message="目標不在同一場景")
        if not runtime.state.get(target, "status", "alive", True):
            return TransitionResult(False, message="目標已失去行動能力")
        health = runtime.state.get(target, "health", "current")
        if health is None:
            return TransitionResult(False, message="目標沒有生命元件")
        damage = max(1, min(int(action.args.get("damage", 5)), 20))
        remaining = max(0, health - damage)
        deltas = [StateDelta(target, "health", "current", "set", remaining, source_module=self.contract.module_id)]
        events = [self.event("combat.damage_applied", action, {"target": target, "damage": damage, "remaining": remaining}, target)]
        if remaining == 0:
            deltas.append(StateDelta(target, "status", "alive", "set", False, source_module=self.contract.module_id))
            events.append(self.event("combat.actor_defeated", action, {"target": target}, target))
        return TransitionResult(True, deltas, events, f"攻擊造成 {damage} 點傷害。")


class DialogueModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("dialogue.core", "0.1.0", "TMS", ["say"], ["dialogue.spoken"], ["position.*"], [], ["entity", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        text = str(action.args.get("text", "")).strip()
        if not text:
            return TransitionResult(False, message="不能說空白內容")
        return TransitionResult(True, events=[self.event("dialogue.spoken", action, {"text": text})], message=f"你說：{text}")


class QuestModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("quest.core", "0.1.0", "TMS", ["quests"], ["quest.observed"], ["quest.*"], [], ["entity", "state", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        summaries = []
        for quest in runtime.package.get("quests", []):
            state = runtime.state.get(action.actor_id, "quest", quest["quest_id"], quest.get("initial_state", "available"))
            summaries.append(f"{quest['title']}[{state}]")
        return TransitionResult(True, events=[self.event("quest.observed", action, {"quests": summaries})], message="任務: " + (", ".join(summaries) or "無"))


def install_builtin_modules(runtime: WorldRuntime) -> None:
    available = {
        module.contract.module_id: module for module in [
            RoomModule(), MovementModule(), DoorModule(), InventoryModule(),
            HealthModule(), CombatModule(), DialogueModule(), QuestModule(),
        ]
    }
    for module_id in runtime.package["manifest"]["modules"]:
        if module_id not in available:
            raise ValueError(f"Runtime Package 要求未知模組: {module_id}")
        runtime.register_module(available[module_id])


def _find_exit(exits: list[dict[str, str]], current: str, direction: str) -> dict[str, str] | None:
    opposites = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
    for edge in exits:
        if edge["from_room"] == current and edge["direction"].lower() == direction:
            return edge
        if _truth(edge.get("bidirectional", "false")) and edge["to_room"] == current and opposites.get(edge["direction"].lower()) == direction:
            return edge
    return None


def _exit_target(edge: dict[str, str], current: str) -> str:
    return edge["to_room"] if edge["from_room"] == current else edge["from_room"]


def _truth(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
