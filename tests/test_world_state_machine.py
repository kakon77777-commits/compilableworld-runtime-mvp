from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import CompileError, compile_world
from compilableworld.kernel import KernelTransactionError, WorldRuntime
from compilableworld.models import ActionIR, EventIR
from compilableworld.modules import install_builtin_modules
from compilableworld.player_generation import generate_character


ROOT = Path(__file__).resolve().parents[1]
PEACE_CITY = ROOT / "examples" / "mingyun_zhiyu_peace_city"


def compiled_package(base: Path = PEACE_CITY) -> dict:
    with tempfile.TemporaryDirectory() as temp:
        path = compile_world(base, temp)
        return json.loads(path.read_text(encoding="utf-8"))


def runtime_with_quest(quest: dict) -> WorldRuntime:
    package = compiled_package()
    package["quests"].append(quest)
    runtime = WorldRuntime(package)
    runtime.state.seed("player.newcomer", "quest", quest["quest_id"], quest["initial_state"])
    install_builtin_modules(runtime)
    return runtime


def dialogue_event(*, topic: str = "secret") -> EventIR:
    return EventIR(
        "dialogue.responded",
        "test.dialogue",
        {
            "actor": "player.newcomer",
            "speaker_id": "npc.foreman_laotie",
            "speaker_name": "Foreman",
            "topic": topic,
            "resolved_topic": topic,
            "dialogue_id": "dialogue.test",
            "text": "test",
        },
        target="player.newcomer",
    )


class WorldStateMachineExecutionTests(unittest.TestCase):
    def test_highest_priority_matching_transition_wins(self) -> None:
        runtime = runtime_with_quest({
            "quest_id": "quest.priority_probe",
            "title": "Priority probe",
            "initial_state": "start",
            "transitions": [
                {
                    "transition_id": "priority.low",
                    "from": "start",
                    "on": "dialogue.responded",
                    "event_match": {},
                    "requirements": [],
                    "to": "fallback",
                    "priority": 0,
                },
                {
                    "transition_id": "priority.high",
                    "from": "start",
                    "on": "dialogue.responded",
                    "event_match": {"topic": "secret"},
                    "requirements": [],
                    "to": "preferred",
                    "priority": 5,
                },
            ],
        })

        runtime.events.publish(dialogue_event(topic="secret"))

        self.assertEqual(runtime.state.get("player.newcomer", "quest", "quest.priority_probe"), "preferred")
        transition = next(event for event in reversed(runtime.event_log.events) if event.event_type == "quest.transitioned")
        self.assertEqual(transition.payload["transition_id"], "priority.high")

    def test_event_match_mismatch_leaves_state_unchanged(self) -> None:
        runtime = runtime_with_quest({
            "quest_id": "quest.match_probe",
            "title": "Match probe",
            "initial_state": "start",
            "transitions": [{
                "transition_id": "match.secret",
                "from": "start",
                "on": "dialogue.responded",
                "event_match": {"topic": "secret"},
                "requirements": [],
                "to": "matched",
                "priority": 0,
            }],
        })

        runtime.events.publish(dialogue_event(topic="public"))

        self.assertEqual(runtime.state.get("player.newcomer", "quest", "quest.match_probe"), "start")
        self.assertFalse(any(event.event_type == "quest.transitioned" for event in runtime.event_log.events))

    def test_reach_requirement_blocks_then_allows_transition(self) -> None:
        runtime = runtime_with_quest({
            "quest_id": "quest.requirement_probe",
            "title": "Requirement probe",
            "initial_state": "start",
            "transitions": [{
                "transition_id": "requirement.reach",
                "from": "start",
                "on": "movement.actor_moved",
                "event_match": {"to": "room.market"},
                "requirements": ["reach:room.market"],
                "to": "arrived",
                "priority": 0,
            }],
        })
        runtime.state.seed("player.newcomer", "position", "room", "room.registration_office")
        event = EventIR(
            "movement.actor_moved",
            "test.movement",
            {"actor": "player.newcomer", "from": "room.registration_office", "to": "room.market", "direction": "north"},
            target="player.newcomer",
        )

        runtime.events.publish(event)
        self.assertEqual(runtime.state.get("player.newcomer", "quest", "quest.requirement_probe"), "start")

        runtime.state.seed("player.newcomer", "position", "room", "room.market")
        runtime.events.publish(event)
        self.assertEqual(runtime.state.get("player.newcomer", "quest", "quest.requirement_probe"), "arrived")

    def test_normal_action_event_order_preserves_causation(self) -> None:
        package = compiled_package()
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        runtime.submit(ActionIR("player.newcomer", "move", args={"direction": "north"}))
        runtime.submit(ActionIR("player.newcomer", "move", args={"direction": "west"}))
        runtime.submit(ActionIR(
            "player.newcomer", "talk", "npc.foreman_laotie", args={"topic": "work"}
        ))

        tail = runtime.event_log.events[-4:]
        self.assertEqual([event.event_type for event in tail], [
            "state.committed", "dialogue.responded", "state.committed", "quest.transitioned",
        ])
        self.assertEqual(tail[3].causation_id, tail[1].event_id)
        self.assertEqual(tail[3].payload["from"], "unstarted")
        self.assertEqual(tail[3].payload["to"], "available")

    def test_door_event_uses_action_causation_actor_not_event_target(self) -> None:
        runtime = runtime_with_quest({
            "quest_id": "quest.unlock_probe",
            "title": "Unlock probe",
            "initial_state": "locked",
            "transitions": [{
                "transition_id": "unlock.checkpoint",
                "from": "locked",
                "on": "door.unlocked",
                "event_match": {"door": "door.checkpoint_gate"},
                "requirements": [],
                "to": "opened",
                "priority": 0,
            }],
        })
        actor = "player.newcomer"

        runtime.submit(ActionIR(actor, "take", "item.provisional_id_tag"))
        runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))
        runtime.submit(ActionIR(actor, "unlock", "door.checkpoint_gate"))

        self.assertEqual(runtime.state.get(actor, "quest", "quest.unlock_probe"), "opened")
        self.assertIsNone(runtime.state.get("door.checkpoint_gate", "quest", "quest.unlock_probe"))
        unlocked = next(event for event in runtime.event_log.events if event.event_type == "door.unlocked")
        transitioned = next(
            event for event in runtime.event_log.events
            if event.event_type == "quest.transitioned" and event.payload["quest_id"] == "quest.unlock_probe"
        )
        self.assertEqual(transitioned.target, actor)
        self.assertEqual(transitioned.causation_id, unlocked.event_id)

    def test_terminal_quest_event_can_chain_another_state_machine(self) -> None:
        package = compiled_package()
        listener = {
            "quest_id": "quest.work_aftermath",
            "title": "Work aftermath",
            "initial_state": "waiting",
            "transitions": [{
                "transition_id": "aftermath.work_completed",
                "from": "waiting",
                "on": "quest.completed",
                "event_match": {"quest_id": "quest.find_work"},
                "requirements": [],
                "to": "unlocked",
                "priority": 0,
            }],
        }
        package["quests"].append(listener)
        runtime = WorldRuntime(package)
        runtime.state.seed("player.newcomer", "quest", listener["quest_id"], listener["initial_state"])
        install_builtin_modules(runtime)
        actor = "player.newcomer"

        runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))
        runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))
        runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
        runtime.submit(ActionIR(actor, "move", args={"direction": "east"}))
        runtime.submit(ActionIR(actor, "take", "item.firewood_bundle"))
        runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))
        runtime.submit(ActionIR(
            actor, "give", "item.firewood_bundle", args={"recipient": "npc.foreman_laotie"}
        ))

        self.assertEqual(runtime.state.get(actor, "quest", "quest.find_work"), "completed")
        self.assertEqual(runtime.state.get(actor, "quest", listener["quest_id"]), "unlocked")
        source = next(
            event for event in runtime.event_log.events
            if event.event_type == "quest.completed" and event.payload["quest_id"] == "quest.find_work"
        )
        chained = next(
            event for event in runtime.event_log.events
            if event.event_type == "quest.transitioned" and event.payload["quest_id"] == listener["quest_id"]
        )
        self.assertEqual(chained.causation_id, source.event_id)

    def test_generated_players_advance_state_machines_independently(self) -> None:
        package = compiled_package()
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        generated = runtime.create_player(
            generate_character(seed=77, name="Second Player"),
            actor_id="player.second",
            replace_default=False,
        )

        runtime.submit(ActionIR(generated, "move", args={"direction": "north"}))
        runtime.submit(ActionIR(generated, "move", args={"direction": "west"}))
        runtime.submit(ActionIR(generated, "talk", "npc.foreman_laotie", args={"topic": "work"}))

        self.assertEqual(runtime.state.get(generated, "quest", "quest.find_work"), "available")
        self.assertEqual(
            runtime.state.get("player.newcomer", "quest", "quest.find_work"),
            "unstarted",
        )

    def test_snapshot_and_replay_preserve_transition_and_single_reward(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_path = compile_world(PEACE_CITY, root / "build")
            event_log_path = root / "events.jsonl"
            runtime = WorldRuntime.from_package(package_path, event_log_path)
            install_builtin_modules(runtime)
            actor = "player.newcomer"
            runtime.submit(ActionIR(actor, "move", args={"direction": "north"}))
            runtime.submit(ActionIR(actor, "move", args={"direction": "west"}))
            runtime.submit(ActionIR(actor, "talk", "npc.foreman_laotie", args={"topic": "work"}))
            snapshot = root / "accepted.snapshot.json"
            runtime.save_snapshot(snapshot)

            restored = WorldRuntime.from_package(package_path, event_log_path)
            install_builtin_modules(restored)
            restored.load_snapshot(snapshot)
            self.assertEqual(restored.state.get(actor, "quest", "quest.find_work"), "available")
            restored.submit(ActionIR(actor, "move", args={"direction": "east"}))
            restored.submit(ActionIR(actor, "take", "item.firewood_bundle"))
            restored.submit(ActionIR(actor, "move", args={"direction": "west"}))
            restored.submit(ActionIR(
                actor, "give", "item.firewood_bundle", args={"recipient": "npc.foreman_laotie"}
            ))

            self.assertEqual(restored.state.get(actor, "quest", "quest.find_work"), "completed")
            self.assertEqual(restored.state.get(actor, "wallet", "currency"), 15)
            completion_count = sum(
                event.event_type == "quest.completed"
                and event.payload["quest_id"] == "quest.find_work"
                for event in restored.event_log.events
            )
            self.assertEqual(completion_count, 1)

            # Re-emitting the same terminal trigger cannot reopen the machine or
            # pay the reward again.
            restored.events.publish(EventIR(
                "inventory.item_given",
                "test.repeated_delivery",
                {"item": "item.firewood_bundle", "actor": actor, "recipient": "npc.foreman_laotie"},
                target=actor,
            ))
            self.assertEqual(restored.state.get(actor, "wallet", "currency"), 15)

            replayed = WorldRuntime.from_package(package_path)
            replayed.replay(restored.event_log.events)
            self.assertEqual(replayed.state.get(actor, "quest", "quest.find_work"), "completed")
            self.assertEqual(replayed.state.get(actor, "wallet", "currency"), 15)
            self.assertEqual(
                replayed.state.get("item.firewood_bundle", "inventory", "carrier"),
                "npc.foreman_laotie",
            )

    def test_reaction_commit_rolls_back_when_event_log_append_fails(self) -> None:
        runtime = runtime_with_quest({
            "quest_id": "quest.rollback_probe",
            "title": "Rollback probe",
            "initial_state": "start",
            "transitions": [{
                "transition_id": "rollback.secret",
                "from": "start",
                "on": "dialogue.responded",
                "event_match": {"topic": "secret"},
                "requirements": [],
                "to": "completed",
                "priority": 0,
                "reward": {"currency": 9},
            }],
        })
        before = runtime.state.export()

        with patch.object(
            runtime.event_log,
            "append_batch",
            side_effect=KernelTransactionError("simulated reaction log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                runtime.events.publish(dialogue_event())

        self.assertEqual(runtime.state.export(), before)
        self.assertEqual(runtime.event_log.events, [])

    def test_compiler_rejects_transition_from_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(PEACE_CITY, world)
            quests_path = world / "quests.json"
            quests = json.loads(quests_path.read_text(encoding="utf-8"))
            quests.append({
                "quest_id": "quest.invalid_terminal",
                "title": "Invalid terminal transition",
                "initial_state": "completed",
                "transitions": [{
                    "transition_id": "terminal.reopen",
                    "from": "completed",
                    "on": "dialogue.responded",
                    "to": "reopened",
                    "priority": 0,
                }],
            })
            quests_path.write_text(json.dumps(quests, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaisesRegex(CompileError, "不可從終態"):
                compile_world(world, Path(temp) / "out")

    def test_compiler_rejects_same_priority_branch_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(PEACE_CITY, world)
            quests_path = world / "quests.json"
            quests = json.loads(quests_path.read_text(encoding="utf-8"))
            quests.append({
                "quest_id": "quest.invalid_priority_conflict",
                "title": "Invalid priority conflict",
                "initial_state": "start",
                "transitions": [
                    {
                        "transition_id": "priority.active",
                        "from": "start",
                        "on": "dialogue.responded",
                        "to": "active",
                        "priority": 2,
                    },
                    {
                        "transition_id": "priority.failed",
                        "from": "start",
                        "on": "dialogue.responded",
                        "to": "failed",
                        "priority": 2,
                    },
                ],
            })
            quests_path.write_text(json.dumps(quests, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(CompileError):
                compile_world(world, Path(temp) / "out")

    def test_compiler_accepts_extended_builtin_event_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(PEACE_CITY, world)
            quests_path = world / "quests.json"
            quests = json.loads(quests_path.read_text(encoding="utf-8"))
            quests.append({
                "quest_id": "quest.unlock_compiled",
                "title": "Compiled unlock trigger",
                "initial_state": "locked",
                "transitions": [{
                    "transition_id": "unlock.compiled",
                    "from": "locked",
                    "on": "door.unlocked",
                    "event_match": {"door": "door.checkpoint_gate"},
                    "to": "completed",
                }],
            })
            quests_path.write_text(json.dumps(quests, ensure_ascii=False, indent=2), encoding="utf-8")

            package = json.loads(
                compile_world(world, Path(temp) / "out").read_text(encoding="utf-8")
            )
            compiled = next(item for item in package["quests"] if item["quest_id"] == "quest.unlock_compiled")
            self.assertEqual(compiled["transitions"][0]["on"], "door.unlocked")

    def test_compiler_rejects_unreachable_transition_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(PEACE_CITY, world)
            quests_path = world / "quests.json"
            quests = json.loads(quests_path.read_text(encoding="utf-8"))
            quests.append({
                "quest_id": "quest.unreachable",
                "title": "Unreachable branch",
                "initial_state": "start",
                "transitions": [{
                    "transition_id": "unreachable.branch",
                    "from": "orphan",
                    "on": "dialogue.responded",
                    "to": "completed",
                }],
            })
            quests_path.write_text(json.dumps(quests, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaisesRegex(CompileError, "不可達"):
                compile_world(world, Path(temp) / "out")

    def test_compiler_enforces_bounded_transition_values(self) -> None:
        invalid_changes = {
            "priority": lambda transition: transition.update(priority=1_000_001),
            "event_match": lambda transition: transition.update(
                event_match={f"field_{index}": index for index in range(17)}
            ),
            "requirements": lambda transition: transition.update(
                requirements=["reach:room.market"] * 33
            ),
            "reward": lambda transition: transition.update(
                to="completed", reward={"currency": -1}
            ),
        }
        for label, change in invalid_changes.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                world = Path(temp) / "world"
                shutil.copytree(PEACE_CITY, world)
                quests_path = world / "quests.json"
                quests = json.loads(quests_path.read_text(encoding="utf-8"))
                transition = quests[0]["transitions"][0]
                change(transition)
                quests_path.write_text(
                    json.dumps(quests, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                with self.assertRaises(CompileError):
                    compile_world(world, Path(temp) / "out")


if __name__ == "__main__":
    unittest.main()
