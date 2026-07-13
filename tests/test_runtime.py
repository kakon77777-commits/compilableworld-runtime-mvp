from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import CompileError, compile_world, validate_world
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


if __name__ == "__main__":
    unittest.main()
