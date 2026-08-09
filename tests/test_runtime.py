from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import CompileError, compile_world, validate_world
from compilableworld.gateway import DeterministicIntentParser
from compilableworld.kernel import KernelTransactionError, StateStore, WorldRuntime
from compilableworld.models import ActionIR, StateDelta
from compilableworld.modules import CombatModule, install_builtin_modules
from compilableworld.player_generation import generate_character


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

    def test_narrative_overlay_is_compiled_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = json.loads(compile_world(EXAMPLE, tmp).read_text(encoding="utf-8"))
            overlay = package["narrative"]["room_overlays"][0]
            self.assertEqual(overlay["room_id"], "room.south_gate")
            self.assertEqual(overlay["when"][0]["owner"], "npc.guard")

        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "world"
            shutil.copytree(EXAMPLE, world)
            narrative_path = world / "narrative.json"
            narrative = json.loads(narrative_path.read_text(encoding="utf-8"))
            narrative["room_overlays"][0]["room_id"] = "room.not_real"
            narrative_path.write_text(json.dumps(narrative), encoding="utf-8")
            with self.assertRaisesRegex(CompileError, "引用不存在房間"):
                compile_world(world, Path(tmp) / "out")

    def test_dialogue_script_is_compiled_and_speaker_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = json.loads(compile_world(PEACE_CITY, tmp).read_text(encoding="utf-8"))
            line = next(x for x in package["dialogues"]["dialogues"] if x["dialogue_id"] == "dialogue.foreman_laotie.work.available")
            self.assertEqual(line["speaker_id"], "npc.foreman_laotie")
            self.assertEqual(line["when"][0]["owner"], "$actor")

        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "world"
            shutil.copytree(PEACE_CITY, world)
            dialogues_path = world / "dialogues.json"
            dialogues = json.loads(dialogues_path.read_text(encoding="utf-8"))
            dialogues["dialogues"][0]["speaker_id"] = "npc.not_real"
            dialogues_path.write_text(json.dumps(dialogues), encoding="utf-8")
            with self.assertRaisesRegex(CompileError, "引用不存在說話者"):
                compile_world(world, Path(tmp) / "out")

    def test_quest_transitions_are_compiled_and_reject_ambiguous_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package = json.loads(compile_world(PEACE_CITY, tmp).read_text(encoding="utf-8"))
            quest = next(q for q in package["quests"] if q["quest_id"] == "quest.find_work")
            self.assertEqual(quest["initial_state"], "unstarted")
            self.assertEqual(quest["transitions"][0]["on"], "dialogue.responded")
            self.assertEqual(quest["transitions"][1]["reward"]["currency"], 15)

        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "world"
            shutil.copytree(PEACE_CITY, world)
            quests_path = world / "quests.json"
            quests = json.loads(quests_path.read_text(encoding="utf-8"))
            duplicate = dict(quests[0]["transitions"][0])
            duplicate["transition_id"] = "transition.find_work.ambiguous"
            duplicate["to"] = "failed"
            quests[0]["transitions"].append(duplicate)
            quests_path.write_text(json.dumps(quests), encoding="utf-8")
            with self.assertRaisesRegex(CompileError, "from/on/priority 不可重複"):
                compile_world(world, Path(tmp) / "out")


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

    def test_action_state_rolls_back_when_event_log_commit_fails(self) -> None:
        before_state = self.runtime.state.export()
        action = ActionIR("player.neo", "move", args={"direction": "north"})
        with patch.object(
            self.runtime.event_log,
            "append_batch",
            side_effect=KernelTransactionError("simulated durable log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.submit(action)

        self.assertEqual(self.runtime.state.export(), before_state)
        self.assertEqual(self.runtime.event_log.events, [])
        self.assertEqual(action.status.value, "failed")

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
        saved = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(saved["format"], "compilableworld.snapshot/v0.3")
        self.assertEqual(saved["snapshot_version"], 3)
        self.assertEqual(saved["action_runtime"], {})
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "south"}))
        self.runtime.load_snapshot(snapshot)
        self.assertEqual(self.runtime.state.get("player.neo", "position", "room"), "room.market")

    def test_snapshot_reconciles_dynamic_entities_and_rejects_invalid_atomically(self) -> None:
        actor = self.runtime.create_player(generate_character(seed=1, name="First"))
        snapshot = Path(self.temp.name) / "generated-save.json"
        self.runtime.save_snapshot(snapshot)

        ghost = self.runtime.create_player(
            generate_character(seed=2, name="Ghost"),
            replace_default=False,
        )
        self.assertIn(ghost, self.runtime.dynamic_entities)
        self.runtime.load_snapshot(snapshot)
        self.assertTrue(self.runtime.registry.contains(actor))
        self.assertFalse(self.runtime.registry.contains(ghost))
        self.assertEqual(self.runtime.dynamic_entities, {actor})
        self.assertEqual(set(self.runtime.player_profiles), {actor})
        self.assertEqual(self.runtime.active_player_id, actor)

        invalid = Path(self.temp.name) / "invalid-scheduler-save.json"
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        payload["scheduler"] = {"tick": "bad", "counter": 0, "queue": []}
        invalid.write_text(json.dumps(payload), encoding="utf-8")
        self.runtime.state.seed("sentinel", "test", "value", 1)
        before_state = self.runtime.state.export()
        before_entities = {entity.entity_id for entity in self.runtime.registry.values()}
        before_dynamic = set(self.runtime.dynamic_entities)
        before_profiles = {key: dict(value) for key, value in self.runtime.player_profiles.items()}
        before_active = self.runtime.active_player_id
        before_scheduler = self.runtime.scheduler.export()

        with self.assertRaisesRegex(RuntimeError, "scheduler"):
            self.runtime.load_snapshot(invalid)

        self.assertEqual(self.runtime.state.export(), before_state)
        self.assertEqual(
            {entity.entity_id for entity in self.runtime.registry.values()},
            before_entities,
        )
        self.assertEqual(self.runtime.dynamic_entities, before_dynamic)
        self.assertEqual(self.runtime.player_profiles, before_profiles)
        self.assertEqual(self.runtime.active_player_id, before_active)
        self.assertEqual(self.runtime.scheduler.export(), before_scheduler)

    def test_snapshot_restores_scheduled_action(self) -> None:
        package = Path(self.temp.name) / "world.package.json"
        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"}), delay=2)
        snapshot = Path(self.temp.name) / "scheduled-save.json"
        self.runtime.save_snapshot(snapshot)

        restored = WorldRuntime.from_package(package)
        install_builtin_modules(restored)
        restored.load_snapshot(snapshot)
        self.assertEqual(restored.scheduler.queued, 1)
        self.assertEqual(restored.advance(1), [])
        receipts = restored.advance(1)
        self.assertEqual(receipts[0].status.value, "completed")
        self.assertEqual(restored.state.get("player.neo", "position", "room"), "room.market")

    def test_legacy_snapshot_migrates_without_scheduled_queue(self) -> None:
        snapshot = Path(self.temp.name) / "legacy-save.json"
        self.runtime.save_snapshot(snapshot)
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        payload["format"] = "compilableworld.snapshot/v0.1"
        payload.pop("snapshot_version", None)
        payload.pop("scheduler", None)
        payload.pop("action_runtime", None)
        snapshot.write_text(json.dumps(payload), encoding="utf-8")

        self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"}))
        self.runtime.load_snapshot(snapshot)
        self.assertEqual(self.runtime.scheduler.tick, 0)
        self.assertEqual(self.runtime.scheduler.queued, 0)
        self.assertEqual(self.runtime.state.get("player.neo", "position", "room"), "room.south_gate")

    def test_snapshot_rejects_unknown_version(self) -> None:
        snapshot = Path(self.temp.name) / "future-save.json"
        self.runtime.save_snapshot(snapshot)
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        payload["snapshot_version"] = 99
        snapshot.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "不支援的 Snapshot 版本"):
            self.runtime.load_snapshot(snapshot)

        payload["snapshot_version"] = 2
        snapshot.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "format 與 snapshot_version 不一致"):
            self.runtime.load_snapshot(snapshot)

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

    def test_look_projects_state_aware_room_overlay(self) -> None:
        self.runtime.state.seed("npc.guard", "status", "alive", False)
        receipt = self.runtime.submit(ActionIR("player.neo", "look"))
        self.assertEqual(receipt.status.value, "completed")
        self.assertIn("南門只剩風", receipt.message)
        observed = [event for event in self.runtime.event_log.events if event.event_type == "room.observed"][-1]
        self.assertEqual(observed.payload["description"], receipt.message)

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
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "unstarted")
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))  # -> labor_yard
        accept = self.runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
        self.assertEqual(accept.status.value, "completed")
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "available")
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "east"}))  # -> slum_alley
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
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "unstarted")

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

    def test_dialogue_offer_transitions_quest_via_event_reaction(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))
        action = DeterministicIntentParser().parse("talk 老鐵 work", actor, self.runtime)
        self.assertEqual(action.verb, "talk")
        self.assertEqual(action.target_id, "npc.foreman_laotie")
        before = self.runtime.submit(action)
        self.assertEqual(before.status.value, "completed")
        self.assertIn("一捆柴薪", before.message)
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "available")
        self.assertEqual(self.runtime.state.get(actor, "wallet", "currency"), 0)
        response = [e for e in self.runtime.event_log.events if e.event_type == "dialogue.responded"][-1]
        self.assertEqual(response.payload["dialogue_id"], "dialogue.foreman_laotie.work.offer")
        transition = [e for e in self.runtime.event_log.events if e.event_type == "quest.transitioned"][-1]
        self.assertEqual(transition.source, "quest.core")
        self.assertEqual(transition.payload["transition_id"], "transition.find_work.accept")
        self.assertEqual(transition.causation_id, response.event_id)

        repeated = self.runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
        self.assertIn("柴薪還在巷子裡", repeated.message)
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "available")

        self.runtime.submit(ActionIR(actor, "move", args={"direction": "east"}))
        self.runtime.submit(ActionIR(actor, "take", "item.firewood_bundle"))
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))
        self.runtime.submit(ActionIR(actor, "give", "item.firewood_bundle", args={"recipient": "npc.foreman_laotie"}))
        after = self.runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
        self.assertEqual(after.status.value, "completed")
        self.assertIn("工錢", after.message)
        response = [e for e in self.runtime.event_log.events if e.event_type == "dialogue.responded"][-1]
        self.assertEqual(response.payload["dialogue_id"], "dialogue.foreman_laotie.work.completed")

    def test_dialogue_without_matching_transition_does_not_change_quest(self) -> None:
        actor = "player.newcomer"
        reply = self.runtime.submit(ActionIR(actor, "talk", "npc.registration_clerk", args={"topic": "default"}))
        self.assertEqual(reply.status.value, "completed")
        self.assertEqual(self.runtime.state.get(actor, "quest", "quest.find_work"), "unstarted")
        self.assertFalse([e for e in self.runtime.event_log.events if e.event_type == "quest.transitioned"])

    def test_higher_priority_branch_can_fail_a_quest_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp) / "world"
            shutil.copytree(PEACE_CITY, world)
            quests_path = world / "quests.json"
            quests = json.loads(quests_path.read_text(encoding="utf-8"))
            quests[0]["transitions"].append({
                "transition_id": "transition.find_work.decline",
                "from": "unstarted",
                "on": "dialogue.responded",
                "event_match": {"dialogue_id": "dialogue.foreman_laotie.work.offer"},
                "to": "failed",
                "priority": 10,
            })
            quests_path.write_text(json.dumps(quests), encoding="utf-8")
            package = compile_world(world, Path(tmp) / "out")
            runtime = WorldRuntime.from_package(package)
            install_builtin_modules(runtime)
            actor = "player.newcomer"
            runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))
            runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))
            runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
            self.assertEqual(runtime.state.get(actor, "quest", "quest.find_work"), "failed")
            failed = [e for e in runtime.event_log.events if e.event_type == "quest.failed"][-1]
            self.assertEqual(failed.payload["transition_id"], "transition.find_work.decline")

    def test_talk_falls_back_to_default_topic_and_requires_presence(self) -> None:
        actor = "player.newcomer"
        missing = self.runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
        self.assertEqual(missing.status.value, "failed")
        self.assertIn("不在目前場景", missing.message)
        fallback = self.runtime.submit(ActionIR(actor, "talk", "npc.registration_clerk", args={"topic": "unknown"}))
        self.assertEqual(fallback.status.value, "completed")
        self.assertIn("名字先記在冊上", fallback.message)

    def test_give_resolves_display_names_for_item_and_recipient(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))  # -> slum_alley
        self.runtime.submit(ActionIR(actor, "take", "item.firewood_bundle"))
        self.runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))  # -> labor_yard
        action = DeterministicIntentParser().parse("give 柴薪捆 老鐵", actor, self.runtime)
        self.assertEqual(action.target_id, "item.firewood_bundle")
        self.assertEqual(action.args["recipient"], "npc.foreman_laotie")
        self.assertEqual(self.runtime.submit(action).status.value, "completed")

    def test_floor_level_newcomer_cannot_effectively_touch_tier1_woerkan(self) -> None:
        """npc.woerkan carries his real combat_resolution_system.json stats
        (tier1); player.newcomer sits at the design's own floor-attribute
        baseline (tier0). The tier gate should make this a near-impossible
        fight, not a normal one -- this is the formula path actually live
        in playable content, not just the synthetic FormulaCombatIntegrationTests."""
        actor = "player.newcomer"
        self.assertEqual(self.runtime.state.get("npc.woerkan", "health", "current"), 7272)
        self.assertEqual(self.runtime.state.get(actor, "health", "current"), 80)
        self.runtime.state.seed(actor, "position", "room", "room.north_garrison")  # skip the traversal, already covered elsewhere
        with patch("compilableworld.modules.random.random", return_value=0.05):
            missed = self.runtime.submit(ActionIR(actor, "attack", "npc.woerkan"))
        self.assertEqual(missed.status.value, "completed")
        self.assertIn("閃開", missed.message)
        self.assertEqual(self.runtime.state.get("npc.woerkan", "health", "current"), 7272)


class MagicModuleTests(unittest.TestCase):
    """Real content, real numbers: player.newcomer's MAG=10 floor attribute
    gives MP_max=50/FP_max=40; 護盾術 costs MP40/FP25 -- affordable exactly
    once, which is itself a real, intended resource-tension check."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package = compile_world(PEACE_CITY, self.temp.name)
        self.runtime = WorldRuntime.from_package(package)
        install_builtin_modules(self.runtime)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_cast_shield_grants_temp_hp_and_spends_resources(self) -> None:
        actor = "player.newcomer"
        self.assertEqual(self.runtime.state.get(actor, "magic", "mp_current"), 50)
        self.assertEqual(self.runtime.state.get(actor, "magic", "fp_current"), 40)
        receipt = self.runtime.submit(ActionIR(actor, "cast", args={"spell": "護盾術"}))
        self.assertEqual(receipt.status.value, "completed")
        self.assertEqual(self.runtime.state.get(actor, "combat", "temp_hp"), 20)  # MAG(10) x 2
        self.assertEqual(self.runtime.state.get(actor, "magic", "mp_current"), 10)
        self.assertEqual(self.runtime.state.get(actor, "magic", "fp_current"), 15)

    def test_second_cast_fails_on_insufficient_resources(self) -> None:
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "cast", args={"spell": "護盾術"}))
        second = self.runtime.submit(ActionIR(actor, "cast", args={"spell": "護盾術"}))
        self.assertEqual(second.status.value, "failed")
        self.assertIn("不足", second.message)

    def test_unknown_spell_rejected(self) -> None:
        result = self.runtime.submit(ActionIR("player.newcomer", "cast", args={"spell": "根本不存在的法術"}))
        self.assertEqual(result.status.value, "failed")

    def test_caster_without_attributes_cannot_cast(self) -> None:
        result = self.runtime.submit(ActionIR("npc.foreman_laotie", "cast", args={"spell": "護盾術"}))
        self.assertEqual(result.status.value, "failed")
        self.assertIn("覺醒", result.message)

    def test_shield_absorbs_before_real_health_in_a_real_exchange(self) -> None:
        """Pure-function absorb/spillover math is already regression-tested
        against the source file's own constants in test_combat_formulas.py;
        this proves the mechanic is actually wired into a real Kernel.submit()
        combat exchange, not just correct in isolation. Woerkan's real counter
        damage (113) exceeds the 20-point shield, so this is the spillover
        case: exactly 20 comes off temp_hp, the remaining 93 hits real health
        -- not the full 113, proving the shield did something even though it
        can't fully save a floor-level newcomer from a tier-1 commander."""
        actor = "player.newcomer"
        self.runtime.submit(ActionIR(actor, "cast", args={"spell": "護盾術"}))
        self.assertEqual(self.runtime.state.get(actor, "combat", "temp_hp"), 20)
        self.runtime.state.seed(actor, "position", "room", "room.north_garrison")
        with patch("compilableworld.modules.random.random", return_value=0.0):
            self.runtime.submit(ActionIR(actor, "attack", "npc.woerkan"))
        self.assertEqual(self.runtime.state.get(actor, "combat", "temp_hp"), 0)
        self.assertEqual(self.runtime.state.get(actor, "health", "current"), 0)  # 80 - (113 - 20) clamped at 0


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

    def test_fast_attacker_gets_multiple_actions_per_exchange(self) -> None:
        """IV ratio 450/75=6 (clamped to 4) for the attacker; 75/450=0.17 (clamped
        to 1) for the defender -- a real, non-trivial Exchange, not the
        actions=1 case every other test happens to land on."""
        package = {
            "format": "compilableworld.runtime-package/v0.1",
            "manifest": {"world_id": "exchange_check", "world_version": "0.1.0", "schema_version": 1, "namespace": "test", "runtime_version": "0.1.0", "modules": ["combat.basic"]},
            "world": {}, "rooms": [], "exits": [], "quests": [],
            "entities": [
                {"entity_id": "npc.swift", "entity_type": "character", "name": "疾風", "components": ["combatant"], "metadata": {}},
                {"entity_id": "npc.tank", "entity_type": "character", "name": "重甲", "components": ["combatant"], "metadata": {}},
            ],
            "initial_state": [
                {"owner": "npc.swift", "namespace": "position", "key": "room", "value": "room.arena", "version": 0},
                {"owner": "npc.tank", "namespace": "position", "key": "room", "value": "room.arena", "version": 0},
                {"owner": "npc.swift", "namespace": "health", "key": "current", "value": 800, "version": 0},
                {"owner": "npc.swift", "namespace": "health", "key": "max", "value": 800, "version": 0},
                {"owner": "npc.tank", "namespace": "health", "key": "current", "value": 1600, "version": 0},
                {"owner": "npc.tank", "namespace": "health", "key": "max", "value": 1600, "version": 0},
                *self._attribute_states("npc.swift", {"str": 100, "con": 100, "mag": 10, "agi": 300, "dex": 300, "phase_tier": 0}),
                *self._attribute_states("npc.tank", {"str": 10, "con": 200, "mag": 10, "agi": 50, "dex": 50, "phase_tier": 0}),
            ],
            "source_checksums": {},
        }
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        with patch("compilableworld.modules.random.random", return_value=0.0):
            receipt = runtime.submit(ActionIR("npc.swift", "attack", "npc.tank"))
        self.assertEqual(receipt.status.value, "completed")
        self.assertIn("連續攻擊 4 次", receipt.message)
        self.assertIn("命中 4 次", receipt.message)
        self.assertIn("共造成 32 點傷害", receipt.message)  # 4 hits x 8 damage/hit
        self.assertEqual(runtime.state.get("npc.tank", "health", "current"), 1600 - 32)
        self.assertEqual(runtime.state.get("npc.swift", "health", "current"), 800 - 1)  # defender: 1 action, 1 dmg

    def test_haste_status_pushes_action_count_across_the_threshold(self) -> None:
        """IV ratio 100/70=1.43 -> 1 action without haste; x1.5 haste makes it
        150/70=2.14 -> 2 actions. Proves attacker_haste actually reaches the
        action_economy() call inside a real Exchange, not just the pure
        combat_formulas functions in isolation."""
        package = {
            "format": "compilableworld.runtime-package/v0.1",
            "manifest": {"world_id": "haste_check", "world_version": "0.1.0", "schema_version": 1, "namespace": "test", "runtime_version": "0.1.0", "modules": ["combat.basic"]},
            "world": {}, "rooms": [], "exits": [], "quests": [],
            "entities": [
                {"entity_id": "npc.a", "entity_type": "character", "name": "甲", "components": ["combatant"], "metadata": {}},
                {"entity_id": "npc.b", "entity_type": "character", "name": "乙", "components": ["combatant"], "metadata": {}},
            ],
            "initial_state": [
                {"owner": "npc.a", "namespace": "position", "key": "room", "value": "room.arena", "version": 0},
                {"owner": "npc.b", "namespace": "position", "key": "room", "value": "room.arena", "version": 0},
                {"owner": "npc.a", "namespace": "health", "key": "current", "value": 800, "version": 0},
                {"owner": "npc.a", "namespace": "health", "key": "max", "value": 800, "version": 0},
                {"owner": "npc.b", "namespace": "health", "key": "current", "value": 800, "version": 0},
                {"owner": "npc.b", "namespace": "health", "key": "max", "value": 800, "version": 0},
                {"owner": "npc.a", "namespace": "combat", "key": "status_effects", "value": [{"id": "haste_疾風", "exchanges_remaining": 3}], "version": 0},
                *self._attribute_states("npc.a", {"str": 50, "con": 50, "mag": 10, "agi": 100, "dex": 0, "phase_tier": 0}),
                *self._attribute_states("npc.b", {"str": 50, "con": 50, "mag": 10, "agi": 70, "dex": 0, "phase_tier": 0}),
            ],
            "source_checksums": {},
        }
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        with patch("compilableworld.modules.random.random", return_value=0.0):
            receipt = runtime.submit(ActionIR("npc.a", "attack", "npc.b"))
        self.assertIn("連續攻擊 2 次", receipt.message)
        self.assertEqual(runtime.state.get("npc.a", "combat", "status_effects"), [{"id": "haste_疾風", "exchanges_remaining": 2}])


if __name__ == "__main__":
    unittest.main()
