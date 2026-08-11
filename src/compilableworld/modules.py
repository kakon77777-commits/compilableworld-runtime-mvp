from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .combat_formulas import (
    ATTRIBUTE_FLOOR, Attributes, action_economy, apply_damage, damage,
    decay_status_effects, has_status, hit_chance, initiative_value, melee_ar,
    melee_dr, refresh_status, tier_effective_ar,
)
from .dialogue import select_dialogue
from .kernel import WorldRuntime
from .models import ActionIR, EventIR, ModuleContract, StateDelta, TransitionResult
from .state_machine import (
    STATE_MACHINE_CONDITION_LIMIT,
    STATE_MACHINE_PRIORITY_LIMIT,
    STATE_MACHINE_TIMER_TICK_LIMIT,
    resolve_state_machine_actor,
    state_machine_condition_matches,
    state_machine_is_active_leaf,
    state_machine_lineage,
    state_machine_resolve_leaf,
    state_machine_state_matches,
)
from .narrative import render_room_description


@dataclass
class BaseModule:
    contract: ModuleContract

    def event(self, event_type: str, action: ActionIR, payload: dict[str, Any], target: str | None = None) -> EventIR:
        return EventIR(event_type, self.contract.module_id, payload, target=target or action.actor_id)

    def on_register(self, runtime: WorldRuntime) -> None:
        """Optional hook: called once after the Kernel registers this module.
        Default no-op; modules that need to subscribe to other modules' events
        (e.g. QuestModule) override this instead of reaching into the Kernel
        at evaluate()-time."""


class RoomModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract("room.core", "0.1.0", "TMS", ["look"], ["room.observed"], ["position.*", "inventory.*", "door.*", "health.*", "status.*", "quest.*", "wallet.*", "fsm.*", "combat.*", "magic.*"], [], ["entity", "state", "event"]))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        room_id = runtime.state.get(action.actor_id, "position", "room")
        room = next((r for r in runtime.package["rooms"] if r["room_id"] == room_id), None)
        if not room:
            return TransitionResult(False, message="目前位置不存在")
        visible = [e.entity_id for e in runtime.registry.values() if runtime.state.get(e.entity_id, "position", "room") == room_id and e.entity_id != action.actor_id]
        description = render_room_description(runtime, action.actor_id, room)
        return TransitionResult(True, events=[self.event("room.observed", action, {"room_id": room_id, "visible": visible, "description": description})], message=description)


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
        if runtime.registry.get(door).entity_type != "door":
            return TransitionResult(False, message="這不是可以開關上鎖的東西")
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
        super().__init__(ModuleContract("inventory.core", "0.1.0", "TMS", ["take", "drop", "give", "inventory"], ["inventory.item_added", "inventory.item_removed", "inventory.item_given", "inventory.observed"], ["position.*", "inventory.*"], ["position.*", "inventory.*"], ["entity", "state", "action", "event"]))

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
        if action.verb == "give":
            recipient = str(action.args.get("recipient", "")).strip()
            if not recipient or not runtime.registry.contains(recipient):
                return TransitionResult(False, message="找不到交付對象")
            if runtime.registry.get(recipient).entity_type not in {"character", "creature"}:
                return TransitionResult(False, message="該對象無法接收物品")
            if runtime.state.get(item, "inventory", "carrier") != action.actor_id:
                return TransitionResult(False, message="物品不在你的物品欄")
            if runtime.state.get(recipient, "position", "room") != room:
                return TransitionResult(False, message="交付對象不在此處")
            if _is_needed_key(item, runtime):
                return TransitionResult(False, message="這是重要的鑰匙，你猶豫著沒有交出去。")
            deltas = [StateDelta(item, "inventory", "carrier", "set", recipient, source_module=self.contract.module_id)]
            payload = {"item": item, "actor": action.actor_id, "recipient": recipient}
            return TransitionResult(True, deltas, [self.event("inventory.item_given", action, payload)], f"你把 {runtime.registry.get(item).name} 交給了 {runtime.registry.get(recipient).name}。")
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
    """Two resolvers, chosen per-fight, never mixed mid-fight:

    1. Formula path — used only when BOTH combatants have authored the five
       combat attributes (str/con/mag/agi/dex) in entities.csv. Uses
       combat_formulas.py, which reproduces (regression-tested, see
       tests/test_combat_formulas.py) the exact ratio-based hit/damage/tier-
       gate math from worlds/mingyun_zhiyu/data/drafts/combat_resolution_system.json
       — Neo's own approved canon combat design, not an approximation of it.
    2. Simple path — the v0.2 fallback (85% hit chance, 3-7 flat damage
       range) for entities with no authored attributes. Deliberately kept
       rather than defaulting everyone to the attribute floor (10): the real
       formula's constants (HP=CONx8, damage x0.1 scaling) are calibrated for
       canon characters with hundreds of attribute points and produce absurdly
       grindy fights at floor-level (10-20) numbers — a real, verified finding
       from actually running the math, not a guess. Applying the formula path
       to starter-zone content needs Neo's input on how that content should be
       scaled, so it isn't forced here."""

    HIT_CHANCE = 0.85
    DAMAGE_RANGE = (3, 7)
    COUNTER_HIT_CHANCE = 0.75
    COUNTER_DAMAGE_RANGE = (1, 3)

    def __init__(self) -> None:
        super().__init__(ModuleContract(
            "combat.basic", "0.1.0", "TMS", ["attack"],
            ["combat.damage_applied", "combat.actor_defeated", "combat.attack_missed"],
            ["position.*", "health.*", "status.*", "combat.*"], ["health.*", "status.*", "combat.temp_hp", "combat.status_effects"], ["entity", "state", "action", "event"],
        ))

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
        target_name = runtime.registry.get(target).name
        if self._has_attributes(action.actor_id, runtime) and self._has_attributes(target, runtime):
            return self._resolve_formula(action, runtime, target, target_name, health)
        return self._resolve_simple(action, runtime, target, target_name, health)

    @staticmethod
    def _has_attributes(entity_id: str, runtime: WorldRuntime) -> bool:
        return runtime.state.version(entity_id, "combat", "con") >= 0

    @staticmethod
    def _attributes_of(entity_id: str, runtime: WorldRuntime) -> Attributes:
        return Attributes(
            str_=runtime.state.get(entity_id, "combat", "str", ATTRIBUTE_FLOOR),
            con=runtime.state.get(entity_id, "combat", "con", ATTRIBUTE_FLOOR),
            mag=runtime.state.get(entity_id, "combat", "mag", ATTRIBUTE_FLOOR),
            agi=runtime.state.get(entity_id, "combat", "agi", ATTRIBUTE_FLOOR),
            dex=runtime.state.get(entity_id, "combat", "dex", ATTRIBUTE_FLOOR),
        )

    def _resolve_simple(self, action: ActionIR, runtime: WorldRuntime, target: str, target_name: str, health: int) -> TransitionResult:
        if random.random() > self.HIT_CHANCE:
            event = self.event("combat.attack_missed", action, {"target": target}, target)
            return TransitionResult(True, events=[event], message=f"你的攻擊被 {target_name} 閃開了。")
        dmg = random.randint(*self.DAMAGE_RANGE)
        remaining = max(0, health - dmg)
        deltas = [StateDelta(target, "health", "current", "set", remaining, source_module=self.contract.module_id)]
        events = [self.event("combat.damage_applied", action, {"target": target, "damage": dmg, "remaining": remaining}, target)]
        if remaining == 0:
            deltas.append(StateDelta(target, "status", "alive", "set", False, source_module=self.contract.module_id))
            events.append(self.event("combat.actor_defeated", action, {"target": target}, target))
            return TransitionResult(True, deltas, events, f"攻擊造成 {dmg} 點傷害，{target_name} 倒下了。")
        if "combatant" in runtime.registry.get(target).components:
            actor_health = runtime.state.get(action.actor_id, "health", "current")
            if actor_health is not None and actor_health > 0:
                if random.random() > self.COUNTER_HIT_CHANCE:
                    events.append(self.event("combat.attack_missed", action, {"target": action.actor_id}, action.actor_id))
                    return TransitionResult(True, deltas, events, f"攻擊造成 {dmg} 點傷害，{target_name} 的反擊撲了空。")
                counter = random.randint(*self.COUNTER_DAMAGE_RANGE)
                actor_remaining = max(0, actor_health - counter)
                deltas.append(StateDelta(action.actor_id, "health", "current", "set", actor_remaining, source_module=self.contract.module_id))
                events.append(self.event("combat.damage_applied", action, {"target": action.actor_id, "damage": counter, "remaining": actor_remaining}, action.actor_id))
                if actor_remaining == 0:
                    deltas.append(StateDelta(action.actor_id, "status", "alive", "set", False, source_module=self.contract.module_id))
                    events.append(self.event("combat.actor_defeated", action, {"target": action.actor_id}, action.actor_id))
                return TransitionResult(True, deltas, events, f"攻擊造成 {dmg} 點傷害，{target_name} 反擊造成 {counter} 點傷害。")
        return TransitionResult(True, deltas, events, f"攻擊造成 {dmg} 點傷害。")

    def _resolve_formula(self, action: ActionIR, runtime: WorldRuntime, target: str, target_name: str, health: int) -> TransitionResult:
        """turn_and_initiative_structure: one submitted `attack` = one Exchange.
        IV = AGI+0.5*DEX (x1.5 under haste_疾風) decides Actions_per_exchange
        per side (clamped 1-4); the faster side's hits all resolve before the
        slower side's, which is a real simplification of the source file's
        "interleaved" narration — documented, not hidden. Attributes/tier
        don't change mid-exchange, so AR/DR are computed once; only the
        hit-roll and damage-roll vary per swing. health/temp_hp are threaded
        as local values across the loop (nothing is committed mid-evaluate(),
        so re-reading runtime.state between swings would see stale
        pre-exchange numbers). Status effects decay by exactly one Exchange
        for BOTH participants, computed once right after the attacker's
        volley (before any early return) so every exit path includes it —
        both sides "experienced" this Exchange regardless of whether the
        defender gets to counter. A status hitting zero exchanges is removed;
        if that status was shield_buff, any temp_hp still standing dissipates
        with it (source: "持續至耗盡或3次交鋒" — whichever comes first)."""
        attacker_attrs = self._attributes_of(action.actor_id, runtime)
        defender_attrs = self._attributes_of(target, runtime)
        attacker_tier = runtime.state.get(action.actor_id, "combat", "phase_tier", 0)
        defender_tier = runtime.state.get(target, "combat", "phase_tier", 0)
        attacker_statuses = runtime.state.get(action.actor_id, "combat", "status_effects", [])
        defender_statuses = runtime.state.get(target, "combat", "status_effects", [])
        attacker_haste = 1.5 if has_status(attacker_statuses, "haste_疾風") else 1.0
        defender_haste = 1.5 if has_status(defender_statuses, "haste_疾風") else 1.0
        attacker_ar_eff = tier_effective_ar(melee_ar(attacker_attrs, registry=runtime.functions), attacker_tier, defender_tier)
        defender_dr = melee_dr(defender_attrs, registry=runtime.functions)
        attacker_actions = action_economy(
            initiative_value(attacker_attrs, registry=runtime.functions) * attacker_haste,
            initiative_value(defender_attrs, registry=runtime.functions) * defender_haste,
            registry=runtime.functions,
        )

        deltas: list[StateDelta] = []
        events: list[EventIR] = []
        target_health, target_temp_hp = health, runtime.state.get(target, "combat", "temp_hp", 0)
        hits = total_damage = 0
        defeated = False
        for _ in range(attacker_actions):
            if random.random() > hit_chance(attacker_ar_eff, defender_dr, registry=runtime.functions):
                events.append(self.event("combat.attack_missed", action, {"target": target}, target))
                continue
            dmg = damage(attacker_ar_eff, defender_dr, registry=runtime.functions)
            target_health, target_temp_hp = apply_damage(target_health, target_temp_hp, dmg)
            hits += 1
            total_damage += dmg
            events.append(self.event("combat.damage_applied", action, {"target": target, "damage": dmg, "remaining": target_health}, target))
            if target_health == 0:
                defeated = True
                break

        actor_temp_hp = runtime.state.get(action.actor_id, "combat", "temp_hp", 0)
        decayed_defender_statuses = decay_status_effects(defender_statuses)
        decayed_attacker_statuses = decay_status_effects(attacker_statuses)
        if has_status(defender_statuses, "shield_buff") and not has_status(decayed_defender_statuses, "shield_buff"):
            target_temp_hp = 0
        if has_status(attacker_statuses, "shield_buff") and not has_status(decayed_attacker_statuses, "shield_buff"):
            actor_temp_hp = 0
        if decayed_defender_statuses != defender_statuses:
            deltas.append(StateDelta(target, "combat", "status_effects", "set", decayed_defender_statuses, source_module=self.contract.module_id))
        if decayed_attacker_statuses != attacker_statuses:
            deltas.append(StateDelta(action.actor_id, "combat", "status_effects", "set", decayed_attacker_statuses, source_module=self.contract.module_id))

        if hits:
            deltas.append(StateDelta(target, "health", "current", "set", target_health, source_module=self.contract.module_id))
        if target_temp_hp != runtime.state.get(target, "combat", "temp_hp", 0):
            deltas.append(StateDelta(target, "combat", "temp_hp", "set", target_temp_hp, source_module=self.contract.module_id))
        if actor_temp_hp != runtime.state.get(action.actor_id, "combat", "temp_hp", 0):
            deltas.append(StateDelta(action.actor_id, "combat", "temp_hp", "set", actor_temp_hp, source_module=self.contract.module_id))

        exchange_msg = self._exchange_message(attacker_actions, hits, total_damage, target_name)
        if defeated:
            deltas.append(StateDelta(target, "status", "alive", "set", False, source_module=self.contract.module_id))
            events.append(self.event("combat.actor_defeated", action, {"target": target}, target))
            return TransitionResult(True, deltas, events, f"{exchange_msg}，{target_name} 倒下了。")
        if hits == 0 or "combatant" not in runtime.registry.get(target).components:
            return TransitionResult(True, deltas, events, f"{exchange_msg}。")
        actor_health = runtime.state.get(action.actor_id, "health", "current")
        if actor_health is None or actor_health <= 0:
            return TransitionResult(True, deltas, events, f"{exchange_msg}。")

        counter_ar_eff = tier_effective_ar(melee_ar(defender_attrs, registry=runtime.functions), defender_tier, attacker_tier)
        attacker_dr = melee_dr(attacker_attrs, registry=runtime.functions)
        defender_actions = action_economy(
            initiative_value(defender_attrs, registry=runtime.functions) * defender_haste,
            initiative_value(attacker_attrs, registry=runtime.functions) * attacker_haste,
            registry=runtime.functions,
        )
        counter_hits = counter_damage_total = 0
        actor_defeated = False
        for _ in range(defender_actions):
            if random.random() > hit_chance(counter_ar_eff, attacker_dr, registry=runtime.functions):
                events.append(self.event("combat.attack_missed", action, {"target": action.actor_id}, action.actor_id))
                continue
            counter_dmg = damage(counter_ar_eff, attacker_dr, registry=runtime.functions)
            actor_health, actor_temp_hp = apply_damage(actor_health, actor_temp_hp, counter_dmg)
            counter_hits += 1
            counter_damage_total += counter_dmg
            events.append(self.event("combat.damage_applied", action, {"target": action.actor_id, "damage": counter_dmg, "remaining": actor_health}, action.actor_id))
            if actor_health == 0:
                actor_defeated = True
                break
        if counter_hits:
            deltas.append(StateDelta(action.actor_id, "health", "current", "set", actor_health, source_module=self.contract.module_id))
            # StateStore.commit() resolves repeated "set" deltas to the same path in
            # order (last wins), so this correctly supersedes the earlier expiry-driven
            # temp_hp delta above if counter-damage further reduced the shield this exchange.
            deltas.append(StateDelta(action.actor_id, "combat", "temp_hp", "set", actor_temp_hp, source_module=self.contract.module_id))
        if actor_defeated:
            deltas.append(StateDelta(action.actor_id, "status", "alive", "set", False, source_module=self.contract.module_id))
            events.append(self.event("combat.actor_defeated", action, {"target": action.actor_id}, action.actor_id))

        counter_msg = self._counter_message(defender_actions, counter_hits, counter_damage_total, target_name)
        tail = "，你倒下了。" if actor_defeated else "。"
        return TransitionResult(True, deltas, events, f"{exchange_msg}，{counter_msg}{tail}")

    @staticmethod
    def _exchange_message(actions: int, hits: int, total_damage: int, target_name: str) -> str:
        if hits == 0:
            return f"你揮出 {actions} 次攻擊，全部被 {target_name} 閃開了" if actions > 1 else f"你的攻擊被 {target_name} 閃開了"
        if actions == 1:
            return f"攻擊造成 {total_damage} 點傷害"
        return f"你連續攻擊 {actions} 次、命中 {hits} 次，共造成 {total_damage} 點傷害"

    @staticmethod
    def _counter_message(actions: int, hits: int, total_damage: int, target_name: str) -> str:
        if hits == 0:
            return f"{target_name} 的反擊全數落空" if actions > 1 else f"{target_name} 的反擊撲了空"
        if actions == 1:
            return f"{target_name} 反擊造成 {total_damage} 點傷害"
        return f"{target_name} 反擊 {actions} 次、命中 {hits} 次，共造成 {total_damage} 點傷害"


class MagicModule(BaseModule):
    """rule_magic_casting_system (combat_resolution_system.json) — MP/FP pools
    are already derived from MAG/DEX at compile time (see compiler.py). Only
    instant-cast spells (symbol_count<=5, cast_time_exchanges=1) are
    implemented: multi-exchange channeling needs interrupt-on-hit logic
    layered on the Exchange loop that combat.basic now has, not built yet.
    Two spells wired up as real, working proof rather than stubbing the whole
    38-symbol combo library at once: 護盾術/shield (the source file's own
    illustrative_calc_examples entry) and 疾風步/haste (status_catalog's
    haste_疾風, IV x1.5 for 3 exchanges — demonstrates the status-effect
    framework interacting with the Exchange/action-economy system, not just
    temp_hp). symbol_count=3 for 疾風步 is this module's own inference from
    the combo tag count in status_catalog's combo_home note ("風+自身+持續"),
    not source-stated — the source only gives illustrative_calc_examples
    numbers for 護盾術/傳送術/烈焰爆裂, not this one."""

    SPELLS = {
        "護盾術": {"symbol_count": 5, "effect": "shield"},
        "疾風步": {"symbol_count": 3, "effect": "haste"},
    }

    def __init__(self) -> None:
        super().__init__(ModuleContract(
            "magic.core", "0.1.0", "TMS", ["cast"], ["magic.cast"],
            ["combat.*", "magic.*"], ["combat.temp_hp", "combat.status_effects", "magic.*"], ["entity", "state", "action", "event"],
        ))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        spell_name = str(action.args.get("spell", "")).strip()
        spell = self.SPELLS.get(spell_name)
        if spell is None:
            return TransitionResult(False, message=f"未知的法術: {spell_name}")
        if runtime.state.version(action.actor_id, "combat", "mag") < 0:
            return TransitionResult(False, message="你尚未覺醒規則魔法")
        mp_cost = spell["symbol_count"] * 8
        fp_cost = spell["symbol_count"] * 5
        mp = runtime.state.get(action.actor_id, "magic", "mp_current", 0)
        fp = runtime.state.get(action.actor_id, "magic", "fp_current", 0)
        if mp < mp_cost or fp < fp_cost:
            return TransitionResult(False, message=f"魔力或精神力不足（需要 MP{mp_cost}/FP{fp_cost}，剩餘 MP{mp}/FP{fp}）")
        deltas = [
            StateDelta(action.actor_id, "magic", "mp_current", "subtract", mp_cost, source_module=self.contract.module_id),
            StateDelta(action.actor_id, "magic", "fp_current", "subtract", fp_cost, source_module=self.contract.module_id),
        ]
        statuses = runtime.state.get(action.actor_id, "combat", "status_effects", [])
        if spell["effect"] == "shield":
            mag = runtime.state.get(action.actor_id, "combat", "mag", ATTRIBUTE_FLOOR)
            temp_hp = mag * 2
            deltas.append(StateDelta(action.actor_id, "combat", "temp_hp", "set", temp_hp, source_module=self.contract.module_id))
            deltas.append(StateDelta(action.actor_id, "combat", "status_effects", "set", refresh_status(statuses, "shield_buff", 3), source_module=self.contract.module_id))
            event = self.event("magic.cast", action, {"spell": spell_name, "effect": "shield", "temp_hp": temp_hp})
            return TransitionResult(True, deltas, [event], f"你施展了{spell_name}，獲得 {temp_hp} 點護盾，持續至耗盡或 3 次交鋒。")
        if spell["effect"] == "haste":
            deltas.append(StateDelta(action.actor_id, "combat", "status_effects", "set", refresh_status(statuses, "haste_疾風", 3), source_module=self.contract.module_id))
            event = self.event("magic.cast", action, {"spell": spell_name, "effect": "haste"})
            return TransitionResult(True, deltas, [event], f"你施展了{spell_name}，身法在接下來 3 次交鋒間變得更加迅捷。")
        return TransitionResult(False, message="法術效果尚未實作")


class DialogueModule(BaseModule):
    def __init__(self) -> None:
        super().__init__(ModuleContract(
            "dialogue.core", "0.1.0", "TMS", ["say", "talk"],
            ["dialogue.spoken", "dialogue.responded"],
            ["position.*", "inventory.*", "door.*", "health.*", "status.*", "quest.*", "wallet.*", "fsm.*", "combat.*", "magic.*"],
            [], ["entity", "state", "event"],
        ))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        if action.verb == "say":
            text = str(action.args.get("text", "")).strip()
            if not text:
                return TransitionResult(False, message="不能說空白內容")
            return TransitionResult(True, events=[self.event("dialogue.spoken", action, {"text": text})], message=f"你說：{text}")

        speaker_id = action.target_id
        if not speaker_id or not runtime.registry.contains(speaker_id):
            return TransitionResult(False, message="找不到可以交談的對象")
        speaker = runtime.registry.get(speaker_id)
        if speaker.entity_type not in {"character", "creature"} or speaker_id == action.actor_id:
            return TransitionResult(False, message="這個對象無法交談")
        actor_room = runtime.state.get(action.actor_id, "position", "room")
        if runtime.state.get(speaker_id, "position", "room") != actor_room:
            return TransitionResult(False, message="對方不在目前場景")
        if not runtime.state.get(speaker_id, "status", "alive", True):
            return TransitionResult(False, message="對方已無法回應")

        topic = str(action.args.get("topic", "default")).strip().lower() or "default"
        line = select_dialogue(runtime, action.actor_id, speaker_id, topic)
        if line is None:
            return TransitionResult(False, message="這個話題暫時得不到回應")
        response = f"{speaker.name}：{line['text']}"
        event = self.event("dialogue.responded", action, {
            "speaker_id": speaker_id,
            "speaker_name": speaker.name,
            "topic": topic,
            "resolved_topic": line["topic"],
            "dialogue_id": line["dialogue_id"],
            "text": line["text"],
        })
        return TransitionResult(True, events=[event], message=response)


class ExplorationModule(BaseModule):
    """Small real completion module for the authored long-action pipeline."""

    def __init__(self) -> None:
        super().__init__(ModuleContract(
            "exploration.core", "0.1.0", "TMS", ["search"],
            ["exploration.searched"],
            ["position.*", "status.*", "exploration.*"],
            ["exploration.*"],
            ["entity", "state", "action", "event", "scheduler"],
        ))

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        if not runtime.state.get(action.actor_id, "status", "alive", True):
            return TransitionResult(False, message="你已無法繼續搜索")
        room_id = runtime.state.get(action.actor_id, "position", "room")
        room = next((item for item in runtime.package["rooms"] if item["room_id"] == room_id), None)
        if room is None:
            return TransitionResult(False, message="目前場景不存在，搜索中止")
        count = runtime.state.get(action.actor_id, "exploration", "search_count", 0) + 1
        delta = StateDelta(
            action.actor_id, "exploration", "search_count", "set", count,
            source_module=self.contract.module_id,
        )
        event = self.event(
            "exploration.searched", action,
            {"room_id": room_id, "search_count": count},
        )
        return TransitionResult(
            True, [delta], [event],
            f"你仔細搜索了{room['name']}（累計 {count} 次）。",
        )


class StateMachineModule(BaseModule):
    """Execute compiled non-Quest StateIR for hierarchical world scopes.

    A machine can only write its own ``owner::fsm::state_machine_id`` cell and,
    when it declares a timer, its reserved
    ``owner::fsm_runtime::state_machine_id`` entry tick. Event payload
    equality, bounded StateStore conditions, deterministic tick timers, and
    priority are compiled ahead of time; this module does not evaluate prose
    guards, arbitrary effects, wall-clock time, or Python expressions.
    """

    def __init__(self) -> None:
        super().__init__(ModuleContract(
            "state_machine.core", "0.5.0", "TMS", [],
            ["fsm.timer_elapsed", "fsm.transitioned", "fsm.completed", "fsm.failed"],
            ["fsm.*", "fsm_runtime.*"], ["fsm.*", "fsm_runtime.*"],
            ["state", "event", "clock"],
        ))
        self._runtime: WorldRuntime | None = None

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        return TransitionResult(False, message="state_machine.core 不接受直接 ActionIR")

    def on_register(self, runtime: WorldRuntime) -> None:
        self._runtime = runtime
        trigger_events = {
            transition.get("on")
            for machine in runtime.package.get("state_machines", [])
            for transition in machine.get("transitions", [])
            if isinstance(transition, dict) and isinstance(transition.get("on"), str)
        }
        for event_type in sorted(trigger_events):
            runtime.events.subscribe(event_type, self._on_event)

    def _on_event(self, event: EventIR) -> None:
        runtime = self._runtime
        assert runtime is not None
        if event.event_type.startswith("fsm.") and event.source != self.contract.module_id:
            return
        actor_id = resolve_state_machine_actor(runtime, event)
        for machine in runtime.package.get("state_machines", []):
            self._apply_transition(machine, event, runtime, actor_id=actor_id)

    def advance_timers(self, tick: int) -> None:
        """Commit every due StateIR timer at one deterministic tick boundary.

        Timer candidates become eligible after their authored delay and remain
        eligible while their owner-only conditions are false. All machines are
        selected from the same pre-commit state and committed as one bounded
        StateDelta/EventIR batch. No background thread or wall clock exists.
        """
        runtime = self._runtime
        assert runtime is not None
        if (
            isinstance(tick, bool)
            or not isinstance(tick, int)
            or tick < 0
            or runtime.scheduler.tick != tick
        ):
            return
        deltas: list[StateDelta] = []
        events: list[EventIR] = []
        machines = [
            machine for machine in runtime.package.get("state_machines", [])
            if isinstance(machine, dict)
        ]
        for machine in sorted(
            machines,
            key=lambda item: (str(item.get("owner_id", "")), str(item.get("state_machine_id", ""))),
        ):
            selected = self._select_timed_transition(machine, runtime, tick)
            if selected is None:
                continue
            machine_deltas, machine_events = self._transition_effects(
                machine, selected, runtime, trigger_event=None, tick=tick,
            )
            deltas.extend(machine_deltas)
            events.extend(machine_events)
        if deltas:
            runtime.commit_reaction(self, deltas, events)

    def _select_timed_transition(
        self, machine: dict[str, Any], runtime: WorldRuntime, tick: int,
    ) -> dict[str, Any] | None:
        machine_id = machine.get("state_machine_id")
        owner_id = machine.get("owner_id")
        initial_state = machine.get("initial_leaf", machine.get("initial_state"))
        if not all(isinstance(value, str) and value for value in (
            machine_id, owner_id, initial_state,
        )):
            return None
        current = runtime.state.get(owner_id, "fsm", machine_id, initial_state)
        if not state_machine_is_active_leaf(machine, current):
            return None
        missing = object()
        entered_tick = runtime.state.get(
            owner_id, "fsm_runtime", machine_id, missing,
        )
        if (
            entered_tick is missing
            or isinstance(entered_tick, bool)
            or not isinstance(entered_tick, int)
            or entered_tick < 0
            or entered_tick > tick
        ):
            return None
        matches = []
        for transition in machine.get("transitions", []):
            if not isinstance(transition, dict) or transition.get("from") != current:
                continue
            after_ticks = transition.get("after_ticks")
            if (
                isinstance(after_ticks, bool)
                or not isinstance(after_ticks, int)
                or not 1 <= after_ticks <= STATE_MACHINE_TIMER_TICK_LIMIT
                or tick < entered_tick + after_ticks
            ):
                continue
            if self._transition_conditions_match(
                runtime, machine, transition, actor_id=None,
            ):
                matches.append(transition)
        return self._select_unique_priority(matches)

    def _apply_transition(
        self, machine: dict[str, Any], event: EventIR, runtime: WorldRuntime,
        *, actor_id: str | None,
    ) -> None:
        machine_id = machine.get("state_machine_id")
        owner_id = machine.get("owner_id")
        initial_leaf = machine.get("initial_leaf", machine.get("initial_state"))
        if not all(
            isinstance(value, str) and value
            for value in (machine_id, owner_id, initial_leaf)
        ):
            return
        current = runtime.state.get(
            owner_id, "fsm", machine_id, initial_leaf,
        )
        if not state_machine_is_active_leaf(machine, current):
            return
        matches = [
            transition for transition in machine.get("transitions", [])
            if isinstance(transition, dict)
            and state_machine_state_matches(machine, transition.get("from"), current)
            and transition.get("on") == event.event_type
            and isinstance(transition.get("event_match", {}), dict)
            and all(
                key in event.payload and event.payload[key] == value
                for key, value in transition.get("event_match", {}).items()
            )
            and self._transition_conditions_match(
                runtime, machine, transition, actor_id=actor_id,
            )
        ]
        if not matches:
            return
        transition = self._select_event_transition(machine, current, matches)
        if transition is None:
            return
        deltas, events = self._transition_effects(
            machine, transition, runtime, trigger_event=event, tick=runtime.scheduler.tick,
        )
        if deltas:
            runtime.commit_reaction(self, deltas, events)

    def _transition_effects(
        self,
        machine: dict[str, Any],
        transition: dict[str, Any],
        runtime: WorldRuntime,
        *,
        trigger_event: EventIR | None,
        tick: int,
    ) -> tuple[list[StateDelta], list[EventIR]]:
        machine_id = machine["state_machine_id"]
        owner_id = machine["owner_id"]
        current = runtime.state.get(
            owner_id, "fsm", machine_id,
            machine.get("initial_leaf", machine.get("initial_state")),
        )
        target_state = state_machine_resolve_leaf(machine, transition.get("to"))
        if (
            not state_machine_is_active_leaf(machine, current)
            or target_state is None
            or target_state == current
        ):
            return [], []
        deltas = [StateDelta(
            owner_id, "fsm", machine_id, "set", target_state,
            source_module=self.contract.module_id,
        )]
        if self._machine_has_timers(machine):
            deltas.append(StateDelta(
                owner_id, "fsm_runtime", machine_id, "set", tick,
                source_module=self.contract.module_id,
            ))
        payload = {
            "state_machine_id": machine_id,
            "title": machine["title"],
            "owner_scope": machine["owner_scope"],
            "owner_id": owner_id,
            "transition_id": transition["transition_id"],
            "from": transition["from"],
            "to": transition["to"],
            "from_leaf": current,
            "to_leaf": target_state,
            "trigger": trigger_event.event_type if trigger_event else "fsm.timer_elapsed",
        }
        visibility = self._event_visibility(machine)
        target = owner_id if machine["owner_scope"] == "entity" else None
        events: list[EventIR] = []
        if trigger_event is None:
            after_ticks = transition["after_ticks"]
            entered_tick = runtime.state.get(owner_id, "fsm_runtime", machine_id)
            timer_event = EventIR(
                "fsm.timer_elapsed", self.contract.module_id,
                {
                    **payload,
                    "after_ticks": after_ticks,
                    "entered_tick": entered_tick,
                    "eligible_at_tick": entered_tick + after_ticks,
                    "fired_at_tick": tick,
                },
                target=target, visibility=visibility,
            )
            timer_event.correlation_id = timer_event.event_id
            events.append(timer_event)
            trigger_event = timer_event
        events.append(EventIR(
            "fsm.transitioned", self.contract.module_id, payload,
            target=target, causation_id=trigger_event.event_id,
            correlation_id=trigger_event.correlation_id, visibility=visibility,
        ))
        if target_state in {"completed", "failed"}:
            events.append(EventIR(
                f"fsm.{target_state}", self.contract.module_id, payload,
                target=target, causation_id=trigger_event.event_id,
                correlation_id=trigger_event.correlation_id, visibility=visibility,
            ))
        return deltas, events

    @staticmethod
    def _machine_has_timers(machine: dict[str, Any]) -> bool:
        return any(
            isinstance(transition, dict) and "after_ticks" in transition
            for transition in machine.get("transitions", [])
        )

    @staticmethod
    def _transition_conditions_match(
        runtime: WorldRuntime,
        machine: dict[str, Any],
        transition: dict[str, Any],
        *,
        actor_id: str | None,
    ) -> bool:
        conditions = transition.get("when", [])
        return (
            isinstance(conditions, list)
            and len(conditions) <= STATE_MACHINE_CONDITION_LIMIT
            and all(
                state_machine_condition_matches(
                    runtime, machine, condition, actor_id=actor_id,
                )
                for condition in conditions
            )
        )

    @staticmethod
    def _select_unique_priority(
        matches: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        valid = [
            candidate for candidate in matches
            if isinstance(candidate.get("priority"), int)
            and not isinstance(candidate.get("priority"), bool)
            and 0 <= candidate["priority"] <= STATE_MACHINE_PRIORITY_LIMIT
        ]
        if not valid:
            return None
        highest = max(candidate["priority"] for candidate in valid)
        selected = [candidate for candidate in valid if candidate["priority"] == highest]
        return selected[0] if len(selected) == 1 else None

    @staticmethod
    def _select_event_transition(
        machine: dict[str, Any],
        active_leaf: str,
        matches: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Select by priority, then by deepest matching source state."""
        valid = [
            candidate for candidate in matches
            if isinstance(candidate.get("priority"), int)
            and not isinstance(candidate.get("priority"), bool)
            and 0 <= candidate["priority"] <= STATE_MACHINE_PRIORITY_LIMIT
            and state_machine_state_matches(
                machine, candidate.get("from"), active_leaf,
            )
        ]
        if not valid:
            return None
        highest_priority = max(candidate["priority"] for candidate in valid)
        priority_matches = [
            candidate for candidate in valid
            if candidate["priority"] == highest_priority
        ]
        deepest = max(
            len(state_machine_lineage(machine, candidate.get("from")))
            for candidate in priority_matches
        )
        selected = [
            candidate for candidate in priority_matches
            if len(state_machine_lineage(machine, candidate.get("from"))) == deepest
        ]
        return selected[0] if len(selected) == 1 else None

    @staticmethod
    def _event_visibility(machine: dict[str, Any]) -> str:
        visibility = machine["visibility"]
        if visibility in {"public", "observable"}:
            return "public"
        if visibility == "private" and machine["owner_scope"] == "entity":
            return "private"
        return "audit"


class QuestModule(BaseModule):
    """Event-reactive quest state transitions.

    Legacy quests still complete from ``available`` when their root
    requirements become true. New authored quests carry explicit transitions
    in the Runtime Package: ``from`` + EventIR ``on`` + optional payload
    match/requirements → ``to``. QuestModule is the only module that writes
    ``quest.*`` or rewards, so dialogue remains an event-only projection.
    """

    def __init__(self) -> None:
        super().__init__(ModuleContract(
            "quest.core", "0.1.0", "TMS", ["quests"],
            ["quest.observed", "quest.transitioned", "quest.completed", "quest.failed"],
            ["quest.*", "inventory.*", "position.*"], ["quest.*", "wallet.*"], ["entity", "state", "event"],
        ))
        self._runtime: WorldRuntime | None = None

    def evaluate(self, action: ActionIR, runtime: WorldRuntime) -> TransitionResult:
        summaries = []
        for quest in runtime.package.get("quests", []):
            state = runtime.state.get(action.actor_id, "quest", quest["quest_id"], quest.get("initial_state", "available"))
            summaries.append(f"{quest['title']}[{state}]")
        return TransitionResult(True, events=[self.event("quest.observed", action, {"quests": summaries})], message="任務: " + (", ".join(summaries) or "無"))

    def on_register(self, runtime: WorldRuntime) -> None:
        self._runtime = runtime
        trigger_events: set[str] = set()
        for quest in runtime.package.get("quests", []):
            transitions = quest.get("transitions")
            if transitions:
                trigger_events.update(transition["on"] for transition in transitions)
            else:
                trigger_events.update({"inventory.item_given", "movement.actor_moved"})
        for event_type in sorted(trigger_events):
            runtime.events.subscribe(event_type, self._on_progress_event)

    def _on_progress_event(self, event: EventIR) -> None:
        runtime = self._runtime
        assert runtime is not None
        if event.event_type.startswith("fsm.") and event.source != "state_machine.core":
            return
        actor_id = resolve_state_machine_actor(runtime, event)
        if actor_id is None:
            return
        for quest in runtime.package.get("quests", []):
            if quest.get("transitions"):
                self._apply_authored_transition(actor_id, quest, event, runtime)
            else:
                self._apply_legacy_completion(actor_id, quest, event, runtime)

    def _apply_authored_transition(
        self, actor_id: str, quest: dict[str, Any], event: EventIR, runtime: WorldRuntime,
    ) -> None:
        quest_id = quest["quest_id"]
        current = runtime.state.get(actor_id, "quest", quest_id, quest.get("initial_state", "available"))
        matches = [
            transition for transition in quest["transitions"]
            if transition["from"] == current
            and transition["on"] == event.event_type
            and self._event_matches(event, transition["event_match"])
            and self._requirements_met(actor_id, transition["requirements"], runtime)
        ]
        if not matches:
            return
        transition = max(matches, key=lambda candidate: candidate["priority"])
        target_state = transition["to"]
        deltas = [StateDelta(actor_id, "quest", quest_id, "set", target_state, source_module=self.contract.module_id)]
        reward = transition.get("reward") or {}
        currency = int(reward.get("currency", 0))
        if target_state == "completed" and currency:
            deltas.append(StateDelta(actor_id, "wallet", "currency", "add", currency, source_module=self.contract.module_id))

        transition_payload = {
            "quest_id": quest_id,
            "title": quest["title"],
            "transition_id": transition["transition_id"],
            "from": current,
            "to": target_state,
            "trigger": event.event_type,
        }
        events = [EventIR(
            "quest.transitioned", self.contract.module_id, transition_payload,
            target=actor_id, causation_id=event.event_id, correlation_id=event.correlation_id,
        )]
        if target_state == "completed":
            events.append(EventIR(
                "quest.completed", self.contract.module_id,
                {**transition_payload, "reward": reward},
                target=actor_id, causation_id=event.event_id, correlation_id=event.correlation_id,
            ))
        elif target_state == "failed":
            events.append(EventIR(
                "quest.failed", self.contract.module_id, transition_payload,
                target=actor_id, causation_id=event.event_id, correlation_id=event.correlation_id,
            ))
        runtime.commit_reaction(self, deltas, events)

    def _apply_legacy_completion(
        self, actor_id: str, quest: dict[str, Any], event: EventIR, runtime: WorldRuntime,
    ) -> None:
        quest_id = quest["quest_id"]
        current = runtime.state.get(actor_id, "quest", quest_id, quest.get("initial_state", "available"))
        if current != "available" or not self._requirements_met(actor_id, quest.get("requirements", []), runtime):
            return
        deltas = [StateDelta(actor_id, "quest", quest_id, "set", "completed", source_module=self.contract.module_id)]
        reward = quest.get("reward") or {}
        currency = int(reward.get("currency", 0))
        if currency:
            deltas.append(StateDelta(actor_id, "wallet", "currency", "add", currency, source_module=self.contract.module_id))
        completed = EventIR(
            "quest.completed", self.contract.module_id, {"quest_id": quest_id, "title": quest["title"], "reward": reward},
            target=actor_id, causation_id=event.event_id, correlation_id=event.correlation_id,
        )
        runtime.commit_reaction(self, deltas, [completed])

    @staticmethod
    def _event_matches(event: EventIR, event_match: dict[str, Any]) -> bool:
        return all(event.payload.get(key) == value for key, value in event_match.items())

    @staticmethod
    def _requirements_met(actor_id: str, requirements: list[str], runtime: WorldRuntime) -> bool:
        for requirement in requirements:
            parts = requirement.split(":")
            if parts[0] == "deliver" and len(parts) == 3:
                _, item_id, target_id = parts
                if runtime.state.get(item_id, "inventory", "carrier") != target_id:
                    return False
            elif parts[0] == "reach" and len(parts) == 2:
                if runtime.state.get(actor_id, "position", "room") != parts[1]:
                    return False
            else:
                return False
        return True


def install_builtin_modules(runtime: WorldRuntime) -> None:
    runtime.bind_action_interrupts()
    available = {
        module.contract.module_id: module for module in [
            RoomModule(), MovementModule(), DoorModule(), InventoryModule(),
            HealthModule(), CombatModule(), MagicModule(), DialogueModule(), ExplorationModule(),
            StateMachineModule(), QuestModule(),
        ]
    }
    for module_id in runtime.package["manifest"]["modules"]:
        if module_id not in available:
            raise ValueError(f"Runtime Package 要求未知模組: {module_id}")
        runtime.register_module(available[module_id])


def _is_needed_key(item_id: str, runtime: WorldRuntime) -> bool:
    """A real playtest gave away the only key to a still-locked door with no
    recovery mechanic (no "take back from NPC"), permanently soft-locking
    that content. Guard at the point of loss rather than trying to add an
    undo path afterward."""
    for edge in runtime.package["exits"]:
        door = edge.get("door_entity", "").strip()
        if door and edge.get("key_id", "").strip() == item_id and runtime.state.get(door, "door", "locked", False):
            return True
    return False


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
