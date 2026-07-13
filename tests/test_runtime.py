from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import CompileError, compile_world, validate_world
from compilableworld.gateway import DeterministicIntentParser
from compilableworld.kernel import StateStore, WorldRuntime
from compilableworld.models import ActionIR, StateDelta
from compilableworld.modules import install_builtin_modules


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"
PEACE_CITY = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class CompilerTests(unittest.TestCase):
    def test_validate_example(self) -> None:
        result = validate_world(EXAMPLE)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rooms"], 3)

    def test_hierarchical_state_and_quest_are_compiled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = json.loads(compile_world(EXAMPLE, tmp).read_text(encoding="utf-8"))
            states = {(x["owner"], x["namespace"], x["key"]): x["value"] for x in package["initial_state"]}
            self.assertEqual(states[("gray_crown_demo", "fsm", "state")], "stable")
            self.assertEqual(states[("region.gray_crown", "fsm", "state")], "watchful")
            self.assertEqual(states[("player.neo", "quest", "quest.black_tide_omen")], "available")

    def test_path_escape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = json.loads((EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
            manifest["sources"]["world"] = "../outside.json"
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(CompileError):
                compile_world(root, root / "out")


class StateTests(unittest.TestCase):
    def test_commit_is_atomic_on_permission_failure(self) -> None:
        state = StateStore()
        state.seed("actor", "health", "current", 10)
        with self.assertRaises(Exception):
            state.commit([
                StateDelta("actor", "health", "current", "subtract", 3),
                StateDelta("actor", "admin", "role", "set", "root"),
            ], ["health.*"])
        self.assertEqual(state.get("actor", "health", "current"), 10)


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package = compile_world(EXAMPLE, self.temp.name)
        self.runtime = WorldRuntime.from_package(package)
        install_builtin_modules(self.runtime)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_movement_inventory_door_and_replay(self) -> None:
        take = self.runtime.submit(ActionIR("player.neo", "take", "item.old_key"))
        self.assertEqual(take.status.value, "completed")
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"}))
        locked = self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "down"}))
        self.assertEqual(locked.status.value, "failed")
        self.runtime.submit(ActionIR("player.neo", "unlock", "door.old_vault"))
        self.runtime.submit(ActionIR("player.neo", "open", "door.old_vault"))
        moved = self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "down"}))
        self.assertEqual(moved.status.value, "completed")
        self.assertEqual(self.runtime.state.get("player.neo", "position", "room"), "room.vault")

        package = Path(self.temp.name) / "world.package.json"
        replayed = WorldRuntime.from_package(package)
        replayed.replay(self.runtime.event_log.events)
        self.assertEqual(replayed.state.get("player.neo", "position", "room"), "room.vault")

    def test_snapshot_round_trip(self) -> None:
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"}))
        snapshot = Path(self.temp.name) / "save.json"
        self.runtime.save_snapshot(snapshot)
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "south"}))
        self.runtime.load_snapshot(snapshot)
        self.assertEqual(self.runtime.state.get("player.neo", "position", "room"), "room.market")

    def test_scheduler_delays_execution(self) -> None:
        action = ActionIR("player.neo", "move", args={"direction": "north"})
        receipt = self.runtime.submit(action, delay=2)
        self.assertEqual(receipt.status.value, "scheduled")
        self.assertEqual(self.runtime.state.get("player.neo", "position", "room"), "room.south_gate")
        self.assertEqual(self.runtime.advance(1), [])
        receipts = self.runtime.advance(1)
        self.assertEqual(receipts[0].status.value, "completed")
        self.assertEqual(self.runtime.state.get("player.neo", "position", "room"), "room.market")

    def test_reach_quest_completes_and_pays_reward_on_arrival(self) -> None:
        self.assertEqual(self.runtime.state.get("player.neo", "quest", "quest.black_tide_omen"), "available")
        self.assertEqual(self.runtime.state.get("player.neo", "wallet", "currency"), 0)
        self.runtime.submit(ActionIR("player.neo", "take", "item.old_key"))
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"}))
        self.runtime.submit(ActionIR("player.neo", "unlock", "door.old_vault"))
        self.runtime.submit(ActionIR("player.neo", "open", "door.old_vault"))
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "down"}))
        self.assertEqual(self.runtime.state.get("player.neo", "quest", "quest.black_tide_omen"), "completed")
        self.assertEqual(self.runtime.state.get("player.neo", "wallet", "currency"), 20)
        completed_events = [e for e in self.runtime.event_log.events if e.event_type == "quest.completed"]
        self.assertEqual(len(completed_events), 1)
        self.assertEqual(completed_events[0].payload["quest_id"], "quest.black_tide_omen")

    def test_reach_quest_does_not_complete_before_arrival(self) -> None:
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"}))
        self.assertEqual(self.runtime.state.get("player.neo", "quest", "quest.black_tide_omen"), "available")

    def test_bare_direction_word_parses_as_move(self) -> None:
        action = DeterministicIntentParser().parse("north", "player.neo", self.runtime)
        self.assertEqual(action.verb, "move")
        self.assertEqual(action.args["direction"], "north")
        receipt = self.runtime.submit(action)
        self.assertEqual(receipt.status.value, "completed")

    def test_unlock_rejects_non_door_target(self) -> None:
        result = self.runtime.submit(ActionIR("player.neo", "unlock", "npc.guard"))
        self.assertEqual(result.status.value, "failed")
        self.assertIn("不是", result.message)

    def test_attack_retaliates_and_kill_message_differs_from_hit_message(self) -> None:
        # random.random() always 0.0 satisfies both "attacker hits" (not > HIT_CHANCE)
        # and "counter hits" (<= COUNTER_HIT_CHANCE); randint fixed to 5 dmg / 2 counter.
        with patch("compilableworld.modules.random.random", return_value=0.0), \
             patch("compilableworld.modules.random.randint", side_effect=[5, 2, 5, 2, 5, 2, 5]):
            hit = self.runtime.submit(ActionIR("player.neo", "attack", "npc.guard"))
            self.assertEqual(hit.status.value, "completed")
            self.assertIn("反擊", hit.message)
            self.assertEqual(self.runtime.state.get("npc.guard", "health", "current"), 15)
            self.assertEqual(self.runtime.state.get("player.neo", "health", "current"), 28)

            self.runtime.submit(ActionIR("player.neo", "attack", "npc.guard"))
            self.runtime.submit(ActionIR("player.neo", "attack", "npc.guard"))
            kill = self.runtime.submit(ActionIR("player.neo", "attack", "npc.guard"))
        self.assertEqual(self.runtime.state.get("npc.guard", "health", "current"), 0)
        self.assertIn("倒下了", kill.message)
        self.assertNotIn("反擊", kill.message)

    def test_attack_can_miss_outright(self) -> None:
        with patch("compilableworld.modules.random.random", return_value=1.0):
            missed = self.runtime.submit(ActionIR("player.neo", "attack", "npc.guard"))
        self.assertEqual(missed.status.value, "completed")
        self.assertIn("閃開", missed.message)
        self.assertEqual(self.runtime.state.get("npc.guard", "health", "current"), 20)

    def test_counter_attack_can_miss(self) -> None:
        with patch("compilableworld.modules.random.random", side_effect=[0.0, 1.0]), \
             patch("compilableworld.modules.random.randint", return_value=5):
            hit = self.runtime.submit(ActionIR("player.neo", "attack", "npc.guard"))
        self.assertIn("反擊", hit.message)
        self.assertIn("撲了空", hit.message)
        self.assertEqual(self.runtime.state.get("npc.guard", "health", "current"), 15)
        self.assertEqual(self.runtime.state.get("player.neo", "health", "current"), 30)


class PeaceCityQuestTests(unittest.TestCase):
    """Real content, not a toy fixture — see examples/mingyun_zhiyu_peace_city."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package = compile_world(PEACE_CITY, self.temp.name)
        self.runtime = WorldRuntime.from_package(package)
        install_builtin_modules(self.runtime)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_delivering_firewood_completes_quest_and_pays_reward(self) -> None:
        actor = "player.newcomer"
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "available")
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        take = self.runtime.submit(ActionIR(actor, "take", "item.firewood_bundle"))
        self.assertEqual(take.status.value, "completed")
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))  # -> labor_yard
        give = self.runtime.submit(ActionIR(actor, "give", "item.firewood_bundle", args={"recipient": "npc.foreman_laotie"}))
        self.assertEqual(give.status.value, "completed")
        self.assertEqual(self.runtime.state.get("item.firewood_bundle", "inventory", "carrier"), "npc.foreman_laotie")
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "completed")
        self.assertEqual(self.runtime.state.get(actor, "wallet", "currency"), 15)

    def test_give_rejected_when_recipient_is_not_a_character(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        self.runtime.submit(ActionIR(actor, "take", "item.firewood_bundle"))
        give = self.runtime.submit(ActionIR(actor, "give", "item.firewood_bundle", args={"recipient": "door.checkpoint_gate"}))
        self.assertEqual(give.status.value, "failed")
        self.assertEqual(self.runtime.state.get("item.firewood_bundle", "inventory", "carrier"), actor)

    def test_give_rejected_when_recipient_not_in_room(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        self.runtime.submit(ActionIR(actor, "take", "item.firewood_bundle"))
        give = self.runtime.submit(ActionIR(actor, "give", "item.firewood_bundle", args={"recipient": "npc.foreman_laotie"}))
        self.assertEqual(give.status.value, "failed")
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "available")

    def test_give_rejected_for_still_needed_key(self) -> None:
        """A real playtest gave away the checkpoint's only key and could never get it
        back. This must fail, not silently succeed."""
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "take", "item.provisional_id_tag"))
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))  # -> labor_yard
        give = self.runtime.submit(ActionIR(actor, "give", "item.provisional_id_tag", args={"recipient": "npc.foreman_laotie"}))
        self.assertEqual(give.status.value, "failed")
        self.assertEqual(self.runtime.state.get("item.provisional_id_tag", "inventory", "carrier"), actor)

    def test_give_allowed_once_key_has_already_been_used(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "take", "item.provisional_id_tag"))
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        unlock = self.runtime.submit(ActionIR(actor, "unlock", "door.checkpoint_gate"))
        self.assertEqual(unlock.status.value, "completed")
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))  # -> labor_yard
        give = self.runtime.submit(ActionIR(actor, "give", "item.provisional_id_tag", args={"recipient": "npc.foreman_laotie"}))
        self.assertEqual(give.status.value, "completed")

    def test_command_target_resolves_display_name_to_id(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        action = DeterministicIntentParser().parse("take 柴薪捆", actor, self.runtime)
        self.assertEqual(action.target_id, "item.firewood_bundle")
        self.assertEqual(self.runtime.submit(action).status.value, "completed")

    def test_give_resolves_display_names_for_item_and_recipient(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        self.runtime.submit(ActionIR(actor, "take", "item.firewood_bundle"))
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))  # -> labor_yard
        action = DeterministicIntentParser().parse("give 柴薪捆 老鐵", actor, self.runtime)
        self.assertEqual(action.target_id, "item.firewood_bundle")
        self.assertEqual(action.args["recipient"], "npc.foreman_laotie")
        self.assertEqual(self.runtime.submit(action).status.value, "completed")


class FormulaCombatIntegrationTests(unittest.TestCase):
    """Proves combat_formulas.py's canon math is actually reachable through
    Kernel -> CombatModule -> submit(), not just correct in isolation
    (see tests/test_combat_formulas.py for the pure-function fidelity tests)."""

    @staticmethod
    def _attribute_states(owner: str, attrs: dict) -> list[dict]:
        return [{"owner": owner, "namespace": "combat", "key": k, "value": v, "version": 0} for k, v in attrs.items()]

    def _make_runtime(self) -> WorldRuntime:
        package = {
            "format": "compilableworld.runtime-package/v0.1",
            "manifest": {"world_id": "formula_check", "world_version": "0.1.0", "schema_version": 1, "namespace": "test", "runtime_version": "0.1.0", "modules": ["combat.basic"]},
            "world": {}, "rooms": [], "exits": [], "quests": [],
            "entities": [
                {"entity_id": "npc.luftiya", "entity_type": "character", "name": "露芙緹雅", "components": ["combatant"], "metadata": {}},
                {"entity_id": "npc.geluosen", "entity_type": "character", "name": "格洛森", "components": ["combatant"], "metadata": {}},
            ],
            "initial_state": [
                {"owner": "npc.luftiya", "namespace": "position", "key": "room", "value": "room.arena", "version": 0},
                {"owner": "npc.geluosen", "namespace": "position", "key": "room", "value": "room.arena", "version": 0},
                {"owner": "npc.luftiya", "namespace": "health", "key": "current", "value": 7248, "version": 0},
                {"owner": "npc.luftiya", "namespace": "health", "key": "max", "value": 7248, "version": 0},
                {"owner": "npc.geluosen", "namespace": "health", "key": "current", "value": 5440, "version": 0},
                {"owner": "npc.geluosen", "namespace": "health", "key": "max", "value": 5440, "version": 0},
                *self._attribute_states("npc.luftiya", {"str": 906, "con": 906, "mag": 408, "agi": 408, "dex": 408, "phase_tier": 2}),
                *self._attribute_states("npc.geluosen", {"str": 1106, "con": 680, "mag": 436, "agi": 436, "dex": 436, "phase_tier": 1}),
            ],
            "source_checksums": {},
        }
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        return runtime

    def test_formula_path_matches_canon_worked_example(self) -> None:
        runtime = self._make_runtime()
        with patch("compilableworld.modules.random.random", return_value=0.0):
            receipt = runtime.submit(ActionIR("npc.luftiya", "attack", "npc.geluosen"))
        self.assertEqual(receipt.status.value, "completed")
        self.assertEqual(receipt.message, "攻擊造成 83 點傷害，格洛森 反擊造成 7 點傷害。")
        self.assertEqual(runtime.state.get("npc.geluosen", "health", "current"), 5440 - 83)
        self.assertEqual(runtime.state.get("npc.luftiya", "health", "current"), 7248 - 7)


if __name__ == "__main__":
    unittest.main()
