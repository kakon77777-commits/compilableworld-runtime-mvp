from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from copy import deepcopy
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

    def _disable_retry(self, package: dict | None = None) -> dict:
        selected = self.package if package is None else package
        selected["action_behaviors"][0]["phases"][1]["retry"] = None
        return selected

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
            behavior["phases"][1]["retry"],
            {"max_attempts": 2, "interval_ticks": 1, "timeout_ticks": 2},
        )
        self.assertEqual(
            behavior["phases"][0]["child_action"],
            {
                "step_id": "survey.room",
                "verb": "look",
                "module_id": "room.core",
                "target": None,
                "args": {},
            },
        )
        self.assertIsNone(behavior["phases"][1]["child_action"])
        self.assertEqual(
            self.package["manifest"]["source_schemas"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.5",
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
        tick_one = [
            event for event in self.runtime.event_log.events if event.timestamp_tick == 1
        ]
        self.assertEqual(
            [event.event_type for event in tick_one],
            [
                "action.child_started", "state.committed", "room.observed",
                "action.child_completed", "action.progressed",
            ],
        )
        child_id = tick_one[0].payload["child_action_id"]
        self.assertEqual(tick_one[2].causation_id, child_id)
        self.assertEqual(tick_one[3].payload["parent_action_id"], action.action_id)

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

    def test_phase_condition_failure_is_terminal_and_auditable(self) -> None:
        self._disable_retry()
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)

        failed = self.runtime.advance(1)
        self.assertEqual(failed[0].status, ActionStatus.FAILED)
        self.assertEqual(action.status, ActionStatus.FAILED)
        self.assertEqual(self.runtime.scheduler.queued, 0)
        self.assertIsNone(self.runtime.state.get("player.neo", "exploration", "search_count"))
        event = self.runtime.event_log.events[-1]
        self.assertEqual(event.event_type, "action.failed")
        self.assertEqual(event.payload["failure_code"], "condition_failed")
        self.assertEqual(event.timestamp_tick, 1)
        self.assertEqual(event.payload["phase_id"], "inspect")
        self.assertEqual(event.payload["condition_id"], "actor_alive")
        self.assertNotIn("action.progressed", [item.event_type for item in self.runtime.event_log.events])
        replayed = WorldRuntime(self.package)
        replayed.replay(self.runtime.event_log.events)
        self.assertEqual(replayed.scheduler.queued, 0)

    def test_bounded_retry_can_recover_then_complete(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)

        retry = self.runtime.advance(1)
        self.assertEqual(retry[0].status, ActionStatus.SCHEDULED)
        self.assertEqual(self.runtime.scheduler.entries()[0][0], 3)
        event = self.runtime.event_log.events[-1]
        self.assertEqual(event.event_type, "action.retry_scheduled")
        self.assertEqual(event.payload["attempt"], 1)
        self.assertEqual(event.payload["retry_at_tick"], 2)
        self.assertEqual(event.payload["timeout_at_tick"], 3)
        pending = self.runtime.pending_actions("player.neo")[0]
        self.assertEqual(pending["active_retries"][0]["attempts"], 1)
        self.assertEqual(pending["active_retries"][0]["max_attempts"], 2)

        self.runtime.state.seed("player.neo", "status", "alive", True)
        self.assertEqual(self.runtime.advance(1), [])
        completed = self.runtime.advance(1)
        self.assertEqual(completed[0].status, ActionStatus.COMPLETED)
        self.assertEqual(self.runtime.state.get("player.neo", "exploration", "search_count"), 1)
        lifecycle = [
            item.event_type for item in self.runtime.event_log.events
            if item.payload.get("action_id") == action.action_id
        ]
        self.assertEqual(
            lifecycle,
            [
                "action.scheduled", "action.retry_scheduled", "action.progressed",
                "action.started", "action.completed",
            ],
        )
        self.assertNotIn(action.action_id, self.runtime.action_runtime)

    def test_child_step_runs_once_across_gate_retries(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)

        self.runtime.advance(1)
        self.runtime.advance(1)
        self.runtime.advance(1)

        child_completed = [
            event for event in self.runtime.event_log.events
            if event.event_type == "action.child_completed"
            and event.payload["parent_action_id"] == action.action_id
        ]
        room_observed = [
            event for event in self.runtime.event_log.events
            if event.event_type == "room.observed"
            and event.correlation_id == action.correlation_id
        ]
        self.assertEqual(len(child_completed), 1)
        self.assertEqual(len(room_observed), 1)
        self.assertEqual(action.status, ActionStatus.FAILED)

    def test_state_changing_child_commits_before_parent_progress(self) -> None:
        package = deepcopy(self.package)
        package["action_behaviors"][0]["phases"][0]["child_action"] = {
            "step_id": "survey.take_key",
            "verb": "take",
            "module_id": "inventory.core",
            "target": {"source": "entity", "entity_id": "item.old_key"},
            "args": {},
        }
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        action = ActionIR("player.neo", "search")
        runtime.submit(action)

        self.assertEqual(runtime.advance(1), [])
        self.assertEqual(
            runtime.state.get("item.old_key", "inventory", "carrier"),
            "player.neo",
        )
        event_types = [event.event_type for event in runtime.event_log.events]
        self.assertLess(
            event_types.index("inventory.item_added"),
            event_types.index("action.progressed"),
        )

    def test_rejected_child_stops_parent_without_compensation(self) -> None:
        package = deepcopy(self.package)
        package["action_behaviors"][0]["phases"][0]["child_action"] = {
            "step_id": "survey.take_marker",
            "verb": "take",
            "module_id": "inventory.core",
            "target": {"source": "entity", "entity_id": "item.stone_marker"},
            "args": {},
        }
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        action = ActionIR("player.neo", "search")
        runtime.submit(action)

        failed = runtime.advance(1)
        self.assertEqual(failed[0].status, ActionStatus.FAILED)
        self.assertEqual(runtime.scheduler.queued, 0)
        self.assertIsNone(runtime.state.get("player.neo", "exploration", "search_count"))
        self.assertEqual(
            [event.event_type for event in runtime.event_log.events[-3:]],
            ["action.child_started", "action.child_failed", "action.failed"],
        )
        self.assertEqual(
            runtime.event_log.events[-1].payload["failure_code"],
            "child_action_failed",
        )

    def test_child_log_failure_rolls_back_state_registry_and_progress(self) -> None:
        package = deepcopy(self.package)
        package["action_behaviors"][0]["phases"][0]["child_action"] = {
            "step_id": "survey.take_key",
            "verb": "take",
            "module_id": "inventory.core",
            "target": {"source": "entity", "entity_id": "item.old_key"},
            "args": {},
        }
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        action = ActionIR("player.neo", "search")
        runtime.submit(action)
        action_ids_before = set(runtime.actions)

        with patch.object(
            runtime.event_log,
            "append_batch",
            side_effect=KernelTransactionError("child log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                runtime.advance(1)

        self.assertEqual(runtime.scheduler.tick, 0)
        self.assertEqual(set(runtime.actions), action_ids_before)
        self.assertIsNone(runtime.state.get("item.old_key", "inventory", "carrier"))
        self.assertEqual(
            runtime.action_runtime[action.action_id]["completed_steps"],
            [],
        )
        self.assertEqual(runtime.advance(1), [])
        self.assertEqual(
            runtime.state.get("item.old_key", "inventory", "carrier"),
            "player.neo",
        )
        self.assertEqual(
            len([
                event for event in runtime.event_log.events
                if event.event_type == "action.child_completed"
            ]),
            1,
        )

    def test_later_phase_retry_does_not_reemit_earlier_checkpoint(self) -> None:
        package = deepcopy(self.package)
        behavior = package["action_behaviors"][0]
        behavior["phases"].insert(1, {
            "phase_id": "approach",
            "title": "接近線索",
            "duration_ticks": 1,
            "when": [],
            "retry": None,
        })
        behavior["phases"][2]["retry"] = {
            "max_attempts": 1,
            "interval_ticks": 2,
            "timeout_ticks": 2,
        }
        behavior["duration_ticks"] = 3
        runtime = WorldRuntime(package)
        install_builtin_modules(runtime)
        action = ActionIR("player.neo", "search")
        runtime.submit(action)
        runtime.state.seed("player.neo", "status", "alive", False)

        self.assertEqual(runtime.advance(1), [])
        self.assertEqual(runtime.advance(1)[0].status, ActionStatus.SCHEDULED)
        self.assertEqual(runtime.advance(1), [])
        self.assertEqual(runtime.pending_actions()[0]["progress_ticks"], 2)
        runtime.state.seed("player.neo", "status", "alive", True)
        self.assertEqual(runtime.advance(1), [])
        self.assertEqual(runtime.advance(1)[0].status, ActionStatus.COMPLETED)
        progressed = [
            (event.payload["phase_id"], event.timestamp_tick)
            for event in runtime.event_log.events
            if event.event_type == "action.progressed"
        ]
        self.assertEqual(progressed, [("survey", 1), ("approach", 4)])

    def test_retry_exhaustion_fails_at_bounded_deadline(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)

        first = self.runtime.advance(1)
        second = self.runtime.advance(1)
        failed = self.runtime.advance(1)
        self.assertEqual(first[0].status, ActionStatus.SCHEDULED)
        self.assertEqual(second[0].status, ActionStatus.SCHEDULED)
        self.assertEqual(failed[0].status, ActionStatus.FAILED)
        self.assertEqual(self.runtime.scheduler.tick, 3)
        self.assertEqual(self.runtime.scheduler.queued, 0)
        terminal = self.runtime.event_log.events[-1]
        self.assertEqual(terminal.event_type, "action.failed")
        self.assertEqual(terminal.payload["failure_code"], "retry_exhausted")
        self.assertEqual(terminal.payload["attempt"], 3)
        self.assertEqual(terminal.payload["max_attempts"], 2)
        self.assertEqual(terminal.payload["timeout_at_tick"], 3)
        self.assertNotIn(action.action_id, self.runtime.action_runtime)

    def test_retry_log_failure_rolls_back_due_tick_and_retry_state(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)
        with patch.object(
            self.runtime.event_log,
            "append_batch",
            side_effect=KernelTransactionError("retry log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.advance(1)
        self.assertEqual(self.runtime.scheduler.tick, 0)
        self.assertEqual(self.runtime.scheduler.entries()[0][0], 2)
        self.assertEqual(
            self.runtime.action_runtime[action.action_id],
            {"retries": {}, "completed_steps": []},
        )
        self.assertEqual(action.status, ActionStatus.SCHEDULED)

        receipt = self.runtime.advance(1)[0]
        self.assertEqual(receipt.status, ActionStatus.SCHEDULED)
        retry_events = [
            event for event in self.runtime.event_log.events
            if event.event_type == "action.retry_scheduled"
        ]
        self.assertEqual(len(retry_events), 1)
        self.assertEqual(retry_events[0].payload["attempt"], 1)

    def test_snapshot_and_replay_restore_retry_attempt_and_due_tick(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)
        self.runtime.advance(1)
        snapshot = Path(self.temp.name) / "retry.snapshot.json"
        self.runtime.save_snapshot(snapshot)
        saved = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(saved["format"], "compilableworld.snapshot/v0.4")
        self.assertEqual(saved["snapshot_version"], 4)
        self.assertEqual(saved["action_runtime"][action.action_id]["retries"]["inspect"]["attempts"], 1)
        self.assertEqual(
            saved["action_runtime"][action.action_id]["completed_steps"],
            ["survey.room"],
        )

        invalid_snapshot = Path(self.temp.name) / "invalid-retry.snapshot.json"
        invalid_saved = deepcopy(saved)
        invalid_saved["action_runtime"][action.action_id]["retries"]["inspect"][
            "next_retry_tick"
        ] = invalid_saved["scheduler"]["tick"]
        invalid_snapshot.write_text(json.dumps(invalid_saved), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeErrorBase, "retry values"):
            WorldRuntime(self.package).load_snapshot(invalid_snapshot)

        restored = WorldRuntime(self.package)
        install_builtin_modules(restored)
        restored.load_snapshot(snapshot)
        self.assertEqual(restored.scheduler.entries()[0][0], 3)
        self.assertEqual(restored.pending_actions()[0]["active_retries"][0]["next_retry_tick"], 2)
        restored.state.seed("player.neo", "status", "alive", True)
        self.assertEqual(restored.advance(1), [])
        self.assertEqual(restored.advance(1)[0].status, ActionStatus.COMPLETED)

        replayed = WorldRuntime(self.package)
        install_builtin_modules(replayed)
        replayed.replay(self.runtime.event_log.events)
        self.assertEqual(replayed.scheduler.entries()[0][0], 3)
        self.assertEqual(replayed.action_runtime[action.action_id]["retries"]["inspect"]["attempts"], 1)
        self.assertEqual(
            replayed.action_runtime[action.action_id]["completed_steps"],
            ["survey.room"],
        )
        self.assertEqual(replayed.advance(1), [])
        self.assertEqual(replayed.advance(1)[0].status, ActionStatus.COMPLETED)

    def test_v03_snapshot_migrates_with_empty_child_progress(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        snapshot = Path(self.temp.name) / "v03-action.snapshot.json"
        self.runtime.save_snapshot(snapshot)
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        payload["format"] = "compilableworld.snapshot/v0.3"
        payload["snapshot_version"] = 3
        payload["action_runtime"][action.action_id].pop("completed_steps")
        snapshot.write_text(json.dumps(payload), encoding="utf-8")

        restored = WorldRuntime(self.package)
        install_builtin_modules(restored)
        restored.load_snapshot(snapshot)
        self.assertEqual(
            restored.action_runtime[action.action_id],
            {"retries": {}, "completed_steps": []},
        )

    def test_snapshot_rejects_non_prefix_child_progress(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        snapshot = Path(self.temp.name) / "invalid-child-progress.snapshot.json"
        self.runtime.save_snapshot(snapshot)
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        payload["action_runtime"][action.action_id]["completed_steps"] = ["unknown.step"]
        snapshot.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(RuntimeErrorBase, "authored prefix"):
            WorldRuntime(self.package).load_snapshot(snapshot)

    def test_v02_snapshot_migrates_pending_action_with_empty_retry_state(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        snapshot = Path(self.temp.name) / "v02-action.snapshot.json"
        self.runtime.save_snapshot(snapshot)
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        payload["format"] = "compilableworld.snapshot/v0.2"
        payload["snapshot_version"] = 2
        payload.pop("action_runtime")
        snapshot.write_text(json.dumps(payload), encoding="utf-8")

        restored = WorldRuntime(self.package)
        install_builtin_modules(restored)
        restored.load_snapshot(snapshot)
        self.assertEqual(restored.scheduler.queued, 1)
        self.assertEqual(
            restored.action_runtime[action.action_id],
            {"retries": {}, "completed_steps": []},
        )

    def test_target_numeric_condition_and_strict_boolean_equality(self) -> None:
        numeric_package = deepcopy(self.package)
        condition = numeric_package["action_behaviors"][0]["phases"][1]["when"][0]
        condition.update({
            "subject": "target",
            "namespace": "health",
            "key": "current",
            "operator": "greater_than",
            "value": 0,
        })
        numeric_runtime = WorldRuntime(numeric_package)
        install_builtin_modules(numeric_runtime)
        numeric_runtime.submit(ActionIR("player.neo", "search", "npc.guard"))
        self.assertEqual(numeric_runtime.advance(1), [])
        self.assertEqual(numeric_runtime.event_log.events[-1].event_type, "action.progressed")

        strict_package = deepcopy(self.package)
        self._disable_retry(strict_package)
        strict_package["action_behaviors"][0]["phases"][1]["when"][0]["value"] = 1
        strict_runtime = WorldRuntime(strict_package)
        install_builtin_modules(strict_runtime)
        strict_runtime.submit(ActionIR("player.neo", "search"))
        failed = strict_runtime.advance(1)
        self.assertEqual(failed[0].status, ActionStatus.FAILED)
        self.assertEqual(failed[0].message.split()[-2:], ["actor_alive", "未滿足"])

        unsafe_package = deepcopy(self.package)
        self._disable_retry(unsafe_package)
        unsafe_package["action_behaviors"][0]["phases"][1]["when"][0]["value"] = {
            "unexpected": True
        }
        unsafe_runtime = WorldRuntime(unsafe_package)
        install_builtin_modules(unsafe_runtime)
        unsafe_runtime.submit(ActionIR("player.neo", "search"))
        self.assertEqual(unsafe_runtime.advance(1)[0].status, ActionStatus.FAILED)

        missing_id_package = deepcopy(self.package)
        self._disable_retry(missing_id_package)
        missing_id_package["action_behaviors"][0]["phases"][1]["when"][0].pop(
            "condition_id"
        )
        missing_id_runtime = WorldRuntime(missing_id_package)
        install_builtin_modules(missing_id_runtime)
        missing_id_runtime.submit(ActionIR("player.neo", "search"))
        self.assertEqual(missing_id_runtime.advance(1)[0].status, ActionStatus.FAILED)
        self.assertEqual(
            missing_id_runtime.event_log.events[-1].payload["condition_id"],
            "invalid_condition",
        )

        invalid_retry_package = deepcopy(self.package)
        invalid_retry_package["action_behaviors"][0]["phases"][1]["retry"] = {
            "max_attempts": True,
            "interval_ticks": 1,
            "timeout_ticks": 1,
        }
        invalid_retry_runtime = WorldRuntime(invalid_retry_package)
        install_builtin_modules(invalid_retry_runtime)
        invalid_retry_runtime.submit(ActionIR("player.neo", "search"))
        invalid_retry_runtime.state.seed("player.neo", "status", "alive", False)
        self.assertEqual(invalid_retry_runtime.advance(1)[0].status, ActionStatus.FAILED)
        self.assertEqual(
            invalid_retry_runtime.event_log.events[-1].payload["failure_code"],
            "invalid_retry_policy",
        )

    def test_condition_failure_log_rollback_restores_tick_queue_and_status(self) -> None:
        self._disable_retry()
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.state.seed("player.neo", "status", "alive", False)
        with patch.object(
            self.runtime.event_log, "append_batch",
            side_effect=KernelTransactionError("condition log failure"),
        ):
            with self.assertRaises(KernelTransactionError):
                self.runtime.advance(1)
        self.assertEqual(self.runtime.scheduler.tick, 0)
        self.assertEqual(self.runtime.scheduler.queued, 1)
        self.assertEqual(action.status, ActionStatus.SCHEDULED)

        failed = self.runtime.advance(1)
        self.assertEqual(failed[0].status, ActionStatus.FAILED)
        self.assertEqual(
            len([event for event in self.runtime.event_log.events if event.event_type == "action.failed"]),
            1,
        )

    def test_failed_completion_emits_started_then_failed_without_effect(self) -> None:
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        self.runtime.advance(1)
        self.runtime.state.seed("player.neo", "status", "alive", False)
        receipt = self.runtime.advance(1)[0]
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

        def first_phase_condition(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][0]["when"] = [
                dict(source["behaviors"][0]["phases"][1]["when"][0])
            ]

        def first_phase_retry(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][0]["retry"] = {
                "max_attempts": 1, "interval_ticks": 1, "timeout_ticks": 1,
            }

        def retry_without_condition(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][1]["when"] = []

        def zero_retry_interval(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][1]["retry"]["interval_ticks"] = 0

        def unbounded_retry_attempts(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][1]["retry"]["max_attempts"] = 17

        def duplicate_condition(source: dict, manifest: dict) -> None:
            condition = dict(source["behaviors"][0]["phases"][1]["when"][0])
            source["behaviors"][0]["phases"][1]["when"].append(condition)

        def unknown_condition_namespace(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][1]["when"][0]["namespace"] = "secret"

        def non_numeric_ordering(source: dict, manifest: dict) -> None:
            condition = source["behaviors"][0]["phases"][1]["when"][0]
            condition["operator"] = "greater_than"
            condition["value"] = "yes"

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

        def final_phase_child(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][1]["child_action"] = deepcopy(
                source["behaviors"][0]["phases"][0]["child_action"]
            )

        def recursive_child(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][0]["child_action"]["verb"] = "search"

        def unknown_child_target(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][0]["child_action"] = {
                "step_id": "survey.take_missing",
                "verb": "take",
                "target": {"source": "entity", "entity_id": "item.missing"},
                "args": {},
            }

        def child_args_outside_whitelist(source: dict, manifest: dict) -> None:
            source["behaviors"][0]["phases"][0]["child_action"]["args"] = {
                "script": "do anything"
            }

        def missing_child_module(source: dict, manifest: dict) -> None:
            manifest["modules"].remove("room.core")

        for label, change in {
            "duration_zero": duration_zero,
            "duplicate_phase": duplicate_phase,
            "first_phase_condition": first_phase_condition,
            "first_phase_retry": first_phase_retry,
            "retry_without_condition": retry_without_condition,
            "zero_retry_interval": zero_retry_interval,
            "unbounded_retry_attempts": unbounded_retry_attempts,
            "duplicate_condition": duplicate_condition,
            "unknown_condition_namespace": unknown_condition_namespace,
            "non_numeric_ordering": non_numeric_ordering,
            "free_guard": free_guard,
            "unknown_interrupt": unknown_interrupt,
            "duplicate_verb": duplicate_verb,
            "missing_module": missing_module,
            "final_phase_child": final_phase_child,
            "recursive_child": recursive_child,
            "unknown_child_target": unknown_child_target,
            "child_args_outside_whitelist": child_args_outside_whitelist,
            "missing_child_module": missing_child_module,
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
            "compilableworld.schema/action-behaviors/v0.5",
        )

    def test_v02_sequential_authoring_remains_compilable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "action_behaviors.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["format"] = "compilableworld.action-behaviors/v0.2"
            for phase in source["behaviors"][0]["phases"]:
                phase.pop("when")
                phase.pop("retry")
                phase.pop("child_action")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_schemas"]["action_behaviors"] = (
                "compilableworld.schema/action-behaviors/v0.2"
            )
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            package_path = compile_world(world, Path(temp) / "build")
            package = json.loads(package_path.read_text(encoding="utf-8"))

        self.assertNotIn("when", package["action_behaviors"][0]["phases"][1])
        self.assertEqual(
            package["manifest"]["source_schemas"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.2",
        )
        self.assertEqual(
            package["schema_contracts"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.5",
        )

    def test_v03_condition_authoring_remains_compilable_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "action_behaviors.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["format"] = "compilableworld.action-behaviors/v0.3"
            for phase in source["behaviors"][0]["phases"]:
                phase.pop("retry")
                phase.pop("child_action")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_schemas"]["action_behaviors"] = (
                "compilableworld.schema/action-behaviors/v0.3"
            )
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            package_path = compile_world(world, Path(temp) / "build")
            package = json.loads(package_path.read_text(encoding="utf-8"))

        self.assertIn("when", package["action_behaviors"][0]["phases"][1])
        self.assertNotIn("retry", package["action_behaviors"][0]["phases"][1])
        self.assertEqual(
            package["manifest"]["source_schemas"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.3",
        )
        self.assertEqual(
            package["schema_contracts"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.5",
        )

    def test_v04_retry_authoring_remains_compilable_without_child_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            source_path = world / "action_behaviors.json"
            manifest_path = world / "manifest.json"
            source = json.loads(source_path.read_text(encoding="utf-8"))
            source["format"] = "compilableworld.action-behaviors/v0.4"
            for phase in source["behaviors"][0]["phases"]:
                phase.pop("child_action")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_schemas"]["action_behaviors"] = (
                "compilableworld.schema/action-behaviors/v0.4"
            )
            source_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            package_path = compile_world(world, Path(temp) / "build")
            package = json.loads(package_path.read_text(encoding="utf-8"))

        self.assertIn("retry", package["action_behaviors"][0]["phases"][1])
        self.assertNotIn("child_action", package["action_behaviors"][0]["phases"][0])
        self.assertEqual(
            package["manifest"]["source_schemas"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.4",
        )
        self.assertEqual(
            package["schema_contracts"]["action_behaviors"],
            "compilableworld.schema/action-behaviors/v0.5",
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

    def test_retry_checkpoint_can_drive_scoped_state_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            machines_path = world / "state_machines.json"
            source = json.loads(machines_path.read_text(encoding="utf-8"))
            source["state_machines"].append({
                "state_machine_id": "fsm.world.search_condition_failure",
                "title": "搜索條件失敗觀測",
                "owner_scope": "world",
                "owner_id": "world",
                "states": ["waiting", "completed"],
                "initial_state": "waiting",
                "persistence": "runtime",
                "visibility": "public",
                "authority": "state_machine.core",
                "transitions": [{
                    "transition_id": "fsm.world.search_condition_failure.observed",
                    "from": "waiting",
                    "on": "action.retry_scheduled",
                    "to": "completed",
                    "event_match": {
                        "condition_id": "actor_alive",
                        "attempt": 1,
                    },
                }],
            })
            machines_path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            runtime = WorldRuntime.from_package(compile_world(world, Path(temp) / "build"))
            install_builtin_modules(runtime)
            runtime.submit(ActionIR("player.neo", "search"))
            runtime.state.seed("player.neo", "status", "alive", False)
            runtime.advance(1)
            self.assertEqual(
                runtime.state.get(
                    "gray_crown_demo", "fsm", "fsm.world.search_condition_failure"
                ),
                "completed",
            )

    def test_child_completion_can_drive_scoped_state_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            shutil.copytree(GRAY_CROWN, world)
            machines_path = world / "state_machines.json"
            source = json.loads(machines_path.read_text(encoding="utf-8"))
            source["state_machines"].append({
                "state_machine_id": "fsm.world.search_child",
                "title": "搜索子步驟觀測",
                "owner_scope": "world",
                "owner_id": "world",
                "states": ["waiting", "completed"],
                "initial_state": "waiting",
                "persistence": "runtime",
                "visibility": "public",
                "authority": "state_machine.core",
                "transitions": [{
                    "transition_id": "fsm.world.search_child.observed",
                    "from": "waiting",
                    "on": "action.child_completed",
                    "to": "completed",
                    "event_match": {
                        "behavior_id": "behavior.search.careful",
                        "step_id": "survey.room",
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
                runtime.state.get("gray_crown_demo", "fsm", "fsm.world.search_child"),
                "completed",
            )

    def test_studio_projects_behavior_and_live_pending_progress(self) -> None:
        static = package_overview(self.package)
        self.assertEqual(static["action_behaviors"][0]["verb"], "search")
        self.assertEqual(
            [phase["phase_id"] for phase in static["action_behaviors"][0]["phases"]],
            ["survey", "inspect"],
        )
        self.assertEqual(
            static["action_behaviors"][0]["phases"][1]["when"][0]["condition_id"],
            "actor_alive",
        )
        self.assertEqual(
            static["action_behaviors"][0]["phases"][1]["retry"]["max_attempts"],
            2,
        )
        self.assertEqual(
            static["action_behaviors"][0]["phases"][0]["child_action"]["step_id"],
            "survey.room",
        )
        self.assertIn("action.completed", static["events"]["declared"])
        self.assertIn("action.progressed", static["events"]["declared"])
        self.assertIn("action.retry_scheduled", static["events"]["declared"])
        self.assertIn("action.child_completed", static["events"]["declared"])
        self.assertEqual(
            static["planes"]["sms"]["snapshot_format"],
            "compilableworld.snapshot/v0.4",
        )
        action = ActionIR("player.neo", "search")
        self.runtime.submit(action)
        live = runtime_overview(self.runtime)
        self.assertEqual(live["pending_actions"][0]["action_id"], action.action_id)
        self.assertEqual(live["pending_actions"][0]["remaining_ticks"], 2)
        self.assertEqual(live["pending_actions"][0]["current_phase"]["phase_id"], "survey")
        self.assertNotIn("when", live["pending_actions"][0]["current_phase"])
        self.assertTrue(
            all("when" not in phase for phase in live["pending_actions"][0]["phases"])
        )
        self.runtime.advance(1)
        live = runtime_overview(self.runtime)
        self.assertEqual(
            live["pending_actions"][0]["current_phase"]["condition_ids"],
            ["actor_alive"],
        )
        self.assertEqual(
            live["pending_actions"][0]["completed_child_steps"],
            ["survey.room"],
        )
        self.assertEqual(live["pending_actions"][0]["child_step_count"], 1)

    def test_parser_exposes_search_as_normal_action_ir(self) -> None:
        action = DeterministicIntentParser().parse("search", "player.neo", self.runtime)
        self.assertEqual(action.verb, "search")


if __name__ == "__main__":
    unittest.main()
