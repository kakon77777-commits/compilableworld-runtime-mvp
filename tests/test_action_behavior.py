from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import CompileError, compile_world
from compilableworld.gateway import DeterministicIntentParser
from compilableworld.kernel import KernelTransactionError, RuntimeErrorBase, WorldRuntime
from compilableworld.models import ActionIR, ActionStatus
from compilableworld.modules import install_builtin_modules
from compilableworld.studio import package_overview, runtime_overview


ROOT = Path(__file__).resolve().parents[1]
GRAY_CROWN = ROOT / "examples" / "gray_crown"


class ActionBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.package_path = compile_world(GRAY_CROWN, Path(self.temp.name) / "build")
        self.package = json.loads(self.package_path.read_text(encoding="utf-8"))
        self.runtime = WorldRuntime(self.package)
        install_builtin_modules(self.runtime)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_compiler_packages_bounded_search_behavior(self) -> None:
        self.assertEqual(len(self.package["action_behaviors"]), 1)
        behavior = self.package["action_behaviors"][0]
        self.assertEqual(behavior["behavior_id"], "behavior.search.careful")
        self.assertEqual(behavior["duration_ticks"], 2)
        self.assertEqual(
            [phase["phase_id"] for phase in behavior["phases"]],
            ["survey", "inspect"],
        )
        self.assertEqual(behavior["completion_module"], "exploration.core")
        self.assertEqual(behavior["concurrency"], "one_per_actor")
        self.assertIn("combat.damage_applied", behavior["interrupt_on"])
        self.assertEqual(
            self.package["manifest"]["source_schemas"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.2",
        )

    def test_search_runs_scheduled_started_completed_lifecycle(self) -> None:
        action = ActionIR("player.neo", "search")
        receipt = self.runtime.submit(action)

        self.assertEqual(receipt.status, ActionStatus.SCHEDULED)
        self.assertEqual(self.runtime.state.get("player.neo", "exploration", "search_count"), None)
        self.assertEqual(self.runtime.pending_actions("player.neo")[0]["progress_ticks"], 0)
        self.assertEqual(self.runtime.advance(1), [])
        self.assertEqual(self.runtime.pending_actions("player.neo")[0]["progress_ticks"], 1)

        completed = self.runtime.advance(1)
        self.assertEqual(completed[0].status, ActionStatus.COMPLETED)
        self.assertEqual(self.runtime.state.get("player.neo", "exploration", "search_count"), 1)
        self.assertEqual(self.runtime.pending_actions("player.neo"), [])
        lifecycle = [
            event for event in self.runtime.event_log.events
            if event.payload.get("action_id") == action.action_id
        ]
        self.assertEqual(
            [event.event_type for event in lifecycle],
            ["action.scheduled", "action.progressed", "action.started", "action.completed"],
        )
        self.assertTrue(all(event.visibility == "private" for event in lifecycle))
        self.assertTrue(all(event.causation_id == action.action_id for event in lifecycle))
        progressed = lifecycle[1]
        self.assertEqual(progressed.timestamp_tick, 1)
        self.assertEqual(progressed.payload["phase_id"], "survey")
        self.assertEqual(progressed.payload["next_phase_id"], "inspect")
        self.assertIn(
            "exploration.searched",
            [event.event_type for event in self.runtime.event_log.events],
        )

    def test_manual_cancel_is_owner_scoped_and_prevents_completion(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        with self.assertRaisesRegex(RuntimeErrorBase, "其他 actor"):
            self.runtime.cancel_action("npc.guard", action.action_id)
        self.assertEqual(self.runtime.scheduler.queued, 1)

        receipt = self.runtime.cancel_action("player.neo", action.action_id)
        self.assertEqual(receipt.status, ActionStatus.CANCELLED)
        self.assertEqual(self.runtime.scheduler.queued, 0)
        self.assertEqual(self.runtime.advance(5), [])
        event = self.runtime.event_log.events[-1]
        self.assertEqual(event.event_type, "action.cancelled")
        self.assertEqual(event.payload["action_id"], action.action_id)

    def test_normal_movement_event_interrupts_search_with_direct_causation(self) -> None:
        search = ActionIR("player.neo", "search")
        self.runtime.submit(search)
        move = self.runtime.submit(ActionIR("player.neo", "move", args={"direction": "north"}))
        self.assertEqual(move.status, ActionStatus.COMPLETED)
        self.assertEqual(search.status, ActionStatus.INTERRUPTED)
        self.assertEqual(self.runtime.scheduler.queued, 0)
        movement = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "movement.actor_moved"
        )
        interrupted = self.runtime.event_log.events[-1]
        self.assertEqual(interrupted.event_type, "action.interrupted")
        self.assertEqual(interrupted.causation_id, movement.event_id)
        self.assertEqual(interrupted.payload["reason"], "被 movement.actor_moved 中斷")

    def test_normal_damage_event_interrupts_search(self) -> None:
        search = ActionIR("player.neo", "search")
        self.runtime.submit(search)
        with patch("compilableworld.modules.random.random", return_value=0.0):
            attack = self.runtime.submit(ActionIR("npc.guard", "attack", "player.neo"))
        self.assertEqual(attack.status, ActionStatus.COMPLETED)
        self.assertEqual(search.status, ActionStatus.INTERRUPTED)
        damage = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "combat.damage_applied" and event.target == "player.neo"
        )
        interrupted = next(
            event for event in self.runtime.event_log.events
            if event.event_type == "action.interrupted"
        )
        self.assertEqual(interrupted.causation_id, damage.event_id)

    def test_one_authored_long_action_per_actor(self) -> None:
        first = ActionIR("player.neo", "search")
        second = ActionIR("player.neo", "search")
        self.runtime.submit(first)
        rejected = self.runtime.submit(second)
        self.assertEqual(rejected.status, ActionStatus.FAILED)
        self.assertEqual(first.status, ActionStatus.SCHEDULED)
        self.assertEqual(self.runtime.scheduler.queued, 1)

        other = ActionIR("npc.guard", "search")
        accepted = self.runtime.submit(other)
        self.assertEqual(accepted.status, ActionStatus.SCHEDULED)
        self.assertEqual(self.runtime.scheduler.queued, 2)

    def test_snapshot_restores_pending_progress_then_completes(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.advance(1)
        snapshot = Path(self.temp.name) / "action.snapshot.json"
        self.runtime.save_snapshot(snapshot)

        restored = WorldRuntime(self.package)
        install_builtin_modules(restored)
        restored.load_snapshot(snapshot)
        pending = restored.pending_actions("player.neo")
        self.assertEqual(pending[0]["progress_ticks"], 1)
        self.assertEqual(pending[0]["remaining_ticks"], 1)
        self.assertEqual(pending[0]["completed_phase_count"], 1)
        self.assertEqual(pending[0]["current_phase"]["phase_id"], "inspect")
        result = restored.advance(1)
        self.assertEqual(result[0].status, ActionStatus.COMPLETED)
        self.assertEqual(restored.state.get("player.neo", "exploration", "search_count"), 1)
        self.assertNotIn(
            "action.progressed",
            [event.event_type for event in restored.event_log.events],
        )

    def test_replay_preserves_completed_search_state(self) -> None:
        self.runtime.submit(ActionIR("player.neo", "search"))
        self.runtime.advance(2)
        replayed = WorldRuntime(self.package)
        replayed.replay(self.runtime.event_log.events)
        self.assertEqual(replayed.state.get("player.neo", "exploration", "search_count"), 1)

    def test_multi_tick_advance_keeps_phase_checkpoint_at_exact_tick(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        completed = self.runtime.advance(2)
        self.assertEqual(completed[0].status, ActionStatus.COMPLETED)
        lifecycle = [
            event for event in self.runtime.event_log.events
            if event.payload.get("action_id") == action.action_id
        ]
        self.assertEqual(
            [(event.event_type, event.timestamp_tick) for event in lifecycle],
            [
                ("action.scheduled", 0),
                ("action.progressed", 1),
                ("action.started", 2),
                ("action.completed", 2),
            ],
        )

    def test_replay_restores_pending_action_from_private_lifecycle_event(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.advance(1)
        replayed = WorldRuntime(self.package)
        install_builtin_modules(replayed)
        replayed.replay(self.runtime.event_log.events)
        self.assertEqual(replayed.scheduler.queued, 1)
        self.assertEqual(replayed.pending_actions("player.neo")[0]["action_id"], action.action_id)
        self.assertEqual(replayed.pending_actions("player.neo")[0]["current_phase"]["phase_id"], "inspect")
        self.assertEqual(replayed.advance(1)[0].status, ActionStatus.COMPLETED)

    def test_schedule_and_cancel_log_failures_restore_scheduler_atomically(self) -> None:
        action = ActionIR("player.neo", "search")
        with patch.object(
            self.runtime.event_log, "append",
            side_effect=KernelTransactionError("schedule log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.submit(action)
        self.assertEqual(self.runtime.scheduler.queued, 0)
        self.assertNotIn(action.action_id, self.runtime.actions)

        self.runtime.submit(action)
        with patch.object(
            self.runtime.event_log, "append",
            side_effect=KernelTransactionError("cancel log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.cancel_action("player.neo", action.action_id)
        self.assertEqual(self.runtime.scheduler.queued, 1)
        self.assertEqual(action.status, ActionStatus.SCHEDULED)

    def test_progress_log_failure_restores_tick_and_retries_once(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        with patch.object(
            self.runtime.event_log, "append_batch",
            side_effect=KernelTransactionError("progress log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.advance(1)
        self.assertEqual(self.runtime.scheduler.tick, 0)
        self.assertEqual(self.runtime.scheduler.queued, 1)

        self.assertEqual(self.runtime.advance(1), [])
        progressed = [
            event for event in self.runtime.event_log.events
            if event.event_type == "action.progressed" and event.payload["action_id"] == action.action_id
        ]
        self.assertEqual(len(progressed), 1)
        self.assertEqual(progressed[0].timestamp_tick, 1)

    def test_failed_completion_emits_started_then_failed_without_effect(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)
        receipt = self.runtime.advance(2)[0]
        self.assertEqual(receipt.status, ActionStatus.FAILED)
        self.assertEqual(self.runtime.state.get("player.neo", "exploration", "search_count"), None)
        self.assertEqual(
            [
                event.event_type for event in self.runtime.event_log.events
                if event.payload.get("action_id") == action.action_id
            ],
            ["action.scheduled", "action.progressed", "action.started", "action.failed"],
        )

    def test_compiler_rejects_unbounded_or_unauthorized_behaviors(self) -> None:
        def duration_zero(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][0]["duration_ticks"] = 0

        def duplicate_phase(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][1]["phase_id"] = "survey"

        def free_guard(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["guard"] = "actor.focus > 10"

        def unknown_interrupt(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["interrupt_on"] = ["anything.happened"]

        def duplicate_verb(source: dict, manifest: dict) -> None:
            duplicate = dict(source["behaviors"][0])
            duplicate["behavior_id"] = "behavior.search.duplicate"
            source["behaviors"].append(duplicate)

        def missing_module(source: dict, manifest: dict) -> None:
            manifest["modules"].remove("exploration.core")

        for label, change in {
            "duration_zero": duration_zero,
            "duplicate_phase": duplicate_phase,
            "free_guard": free_guard,
            "unknown_interrupt": unknown_interrupt,
            "duplicate_verb": duplicate_verb,
            "missing_module": missing_module,
        }.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                world = Path(temp) / "world"
                shutil.copytree(GRAY_CROWN, world)
                source_path = world / "action_behaviors.json"
                manifest_path = world / "manifest.json"
                source = json.loads(source_path.read_text(encoding="utf-8"))
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                change(source, manifest)
                source_path.write_text(
                    json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                with self.assertRaises(CompileError):
                    compile_world(world, Path(temp) / "build")

    def test_v01_single_phase_authoring_remains_compilable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "action_behaviors.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["format"] = "compilableworld.action-behaviors/v0.1"
            behavior = source["behaviors"][0]
            behavior["duration_ticks"] = sum(
                phase["duration_ticks"] for phase in behavior.pop("phases")
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_schemas"]["action_behaviors"] = (
                "compilableworld.schema/action-behaviors/v0.1"
            )
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            package_path = compile_world(world, Path(temp) / "build")
            package = json.loads(package_path.read_text(encoding="utf-8"))

        self.assertNotIn("phases", package["action_behaviors"][0])
        self.assertEqual(package["action_behaviors"][0]["duration_ticks"], 2)
        self.assertEqual(
            package["manifest"]["source_schemas"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.1",
        )
        self.assertEqual(
            package["schema_contracts"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.2",
        )

    def test_action_completed_event_can_drive_scoped_state_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            machines_path = world / "state_machines.json"
            source = json.loads(machines_path.read_text(encoding="utf-8"))
            source["state_machines"].append({
                "state_machine_id": "fsm.world.first_search",
                "title": "首次搜索完成",
                "owner_scope": "world",
                "owner_id": "world",
                "states": ["waiting", "completed"],
                "initial_state": "waiting",
                "persistence": "runtime",
                "visibility": "public",
                "authority": "state_machine.core",
                "transitions": [{
                    "transition_id": "fsm.world.first_search.completed",
                    "from": "waiting",
                    "on": "action.completed",
                    "to": "completed",
                    "event_match": {"behavior_id": "behavior.search.careful"},
                }],
            })
            machines_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            runtime = WorldRuntime.from_package(compile_world(world, Path(temp) / "build"))
            install_builtin_modules(runtime)
            runtime.submit(ActionIR("player.neo", "search"))
            runtime.advance(2)
            self.assertEqual(
                runtime.state.get("gray_crown_demo", "fsm", "fsm.world.first_search"),
                "completed",
            )

    def test_action_progressed_checkpoint_can_drive_scoped_state_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            machines_path = world / "state_machines.json"
            source = json.loads(machines_path.read_text(encoding="utf-8"))
            source["state_machines"].append({
                "state_machine_id": "fsm.world.search_checkpoint",
                "title": "搜索階段觀測",
                "owner_scope": "world",
                "owner_id": "world",
                "states": ["waiting", "completed"],
                "initial_state": "waiting",
                "persistence": "runtime",
                "visibility": "public",
                "authority": "state_machine.core",
                "transitions": [{
                    "transition_id": "fsm.world.search_checkpoint.surveyed",
                    "from": "waiting",
                    "on": "action.progressed",
                    "to": "completed",
                    "event_match": {
                        "behavior_id": "behavior.search.careful",
                        "phase_id": "survey",
                    },
                }],
            })
            machines_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            runtime = WorldRuntime.from_package(compile_world(world, Path(temp) / "build"))
            install_builtin_modules(runtime)
            runtime.submit(ActionIR("player.neo", "search"))
            runtime.advance(1)
            self.assertEqual(
                runtime.state.get("gray_crown_demo", "fsm", "fsm.world.search_checkpoint"),
                "completed",
            )
            self.assertIsNone(
                runtime.state.get("player.neo", "exploration", "search_count")
            )

    def test_studio_projects_behavior_and_live_pending_progress(self) -> None:
        static = package_overview(self.package)
        self.assertEqual(static["action_behaviors"][0]["verb"], "search")
        self.assertEqual(
            [phase["phase_id"] for phase in static["action_behaviors"][0]["phases"]],
            ["survey", "inspect"],
        )
        self.assertIn("action.completed", static["events"]["declared"])
        self.assertIn("action.progressed", static["events"]["declared"])
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        live = runtime_overview(self.runtime)
        self.assertEqual(live["pending_actions"][0]["action_id"], action.action_id)
        self.assertEqual(live["pending_actions"][0]["remaining_ticks"], 2)
        self.assertEqual(live["pending_actions"][0]["current_phase"]["phase_id"], "survey")

    def test_parser_exposes_search_as_normal_action_ir(self) -> None:
        action = DeterministicIntentParser().parse("search", "player.neo", self.runtime)
        self.assertEqual(action.verb, "search")


if __name__ == "__main__":
    unittest.main()
