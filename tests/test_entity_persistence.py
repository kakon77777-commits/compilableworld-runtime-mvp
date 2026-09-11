from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compilableworld.compiler import compile_world
from compilableworld.entity_transaction import EntityTransactionRuntime
from compilableworld.kernel import KernelTransactionError, RuntimeErrorBase, WorldRuntime
from compilableworld.models import ActionIR, EventIR, StateDelta
from compilableworld.player_generation import generate_character
from examples.entity_lifecycle_demo import ACTOR, ITEM, KeepsakeModule, open_runtime, run_demo


ROOT = Path(__file__).resolve().parents[1]


class EntityPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiled = tempfile.TemporaryDirectory()
        cls.package = compile_world(ROOT / "examples" / "gray_crown", Path(cls.compiled.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.compiled.cleanup()

    def runtime(self, log: Path | None = None) -> EntityTransactionRuntime:
        return open_runtime(self.package, log)

    def observable(self, runtime: EntityTransactionRuntime) -> dict:
        return deepcopy({
            "entities": {entity.entity_id: asdict(entity) for entity in runtime.registry.values()},
            "state": runtime.state.export(), "dynamic": runtime.dynamic_entities,
            "profiles": runtime.player_profiles, "active_player": runtime.active_player_id,
            "scheduler": runtime.scheduler.export(), "action_runtime": runtime.action_runtime,
            "actions": {key: action.to_dict() for key, action in runtime.actions.items()},
            "halt": runtime.events.diagnostics(), "events": runtime.event_log.events,
        })

    def created(self) -> EntityTransactionRuntime:
        runtime = self.runtime()
        self.assertEqual(runtime.submit(ActionIR(ACTOR, "make_keepsake")).status.value, "completed")
        return runtime

    def test_full_offline_demo(self) -> None:
        self.assertTrue(run_demo()["ok"])

    def test_snapshot_and_replay_preserve_entity_state_recipe_and_continuation(self) -> None:
        runtime = self.created()
        runtime.advance(4)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "save.json"
            runtime.save_snapshot(snapshot)
            restored = self.runtime()
            restored.load_snapshot(snapshot)
        replayed = self.runtime()
        with patch.object(KeepsakeModule, "evaluate", side_effect=AssertionError("Replay evaluated module")):
            replayed.replay(iter(runtime.event_log.events))
        # A clock-only advance without a durable event is not part of a log.
        self.assertEqual(restored.scheduler.tick, 4)
        for recovered in (restored, replayed):
            self.assertEqual(recovered.registry.get(ITEM), runtime.registry.get(ITEM))
            self.assertEqual(recovered.dynamic_entities, runtime.dynamic_entities)
            self.assertEqual(recovered.state.export(), runtime.state.export())
            self.assertEqual(recovered.submit(ActionIR(ACTOR, "take", ITEM)).status.value, "completed")
            self.assertEqual(recovered.state.get(ITEM, "inventory", "carrier"), ACTOR)

    def test_replay_does_not_publish_or_append_and_detaches_input_records(self) -> None:
        runtime = self.created()
        records = deepcopy(runtime.event_log.events)
        replayed = self.runtime()
        observed = []
        replayed.events.subscribe("*", observed.append)
        before_records = deepcopy(records)
        replayed.replay(records)
        self.assertEqual(observed, [])
        self.assertEqual(replayed.event_log.events, [])
        self.assertEqual(records, before_records)
        entity_event = next(event for event in records if event.event_type == "entity.committed")
        entity_event.payload["applied"][0]["entity"]["metadata"]["recipe"]["creator"] = "changed"
        self.assertEqual(replayed.registry.get(ITEM).metadata["recipe"]["creator"], ACTOR)

    def test_snapshot_rewind_allows_recreation_and_replays_final_world(self) -> None:
        runtime = self.runtime()
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "before-create.json"
            runtime.save_snapshot(snapshot)
            runtime.submit(ActionIR(ACTOR, "make_keepsake"))
            runtime.submit(ActionIR(ACTOR, "take", ITEM))
            runtime.load_snapshot(snapshot)
            self.assertFalse(runtime.registry.contains(ITEM))
            runtime.submit(ActionIR(ACTOR, "make_keepsake"))
            replayed = self.runtime()
            replayed.replay(runtime.event_log.events)
            self.assertEqual(replayed.registry.get(ITEM), runtime.registry.get(ITEM))
            self.assertEqual(replayed.state.export(), runtime.state.export())
            self.assertEqual(replayed.scheduler.export(), runtime.scheduler.export())

    def test_snapshot_with_entity_rewinds_changes_and_later_creation(self) -> None:
        runtime = self.created()
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "with-entity.json"
            runtime.save_snapshot(snapshot)
            runtime.submit(ActionIR(ACTOR, "take", ITEM))
            runtime.submit(ActionIR(ACTOR, "make_keepsake", args={"item_id": "item.later"}))
            runtime.load_snapshot(snapshot)
            runtime.submit(ActionIR(ACTOR, "take", ITEM))
            replayed = self.runtime()
            replayed.replay(runtime.event_log.events)
            self.assertFalse(replayed.registry.contains("item.later"))
            self.assertEqual(replayed.state.export(), runtime.state.export())
            self.assertEqual(replayed.dynamic_entities, {ITEM})

    def test_pending_creation_resumes_once_after_snapshot_or_replay(self) -> None:
        runtime = self.runtime()
        action = ActionIR(ACTOR, "make_keepsake")
        runtime.submit(action, delay=3)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "pending.json"
            runtime.save_snapshot(snapshot)
            restored = self.runtime()
            restored.load_snapshot(snapshot)
        replayed = self.runtime()
        replayed.replay(runtime.event_log.events)
        for recovered in (restored, replayed):
            self.assertFalse(recovered.registry.contains(ITEM))
            self.assertEqual(recovered.advance(3)[0].status.value, "completed")
            self.assertEqual(recovered.advance(3), [])
            self.assertTrue(recovered.registry.contains(ITEM))
            self.assertEqual(recovered.scheduler.queued, 0)

    def test_generated_player_and_generic_item_share_snapshot_and_replay(self) -> None:
        runtime = self.runtime()
        actor = runtime.create_player(generate_character(seed=27, package=runtime.package))
        self.assertEqual(runtime.submit(ActionIR(actor, "make_keepsake")).status.value, "completed")
        self.assertEqual(runtime.submit(ActionIR(actor, "take", ITEM)).status.value, "completed")
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "mixed.json"
            runtime.save_snapshot(snapshot)
            restored = self.runtime()
            restored.load_snapshot(snapshot)
        replayed = self.runtime()
        replayed.replay(runtime.event_log.events)
        for recovered in (restored, replayed):
            self.assertEqual(recovered.dynamic_entities, {actor, ITEM})
            self.assertFalse(recovered.registry.contains(ACTOR))
            self.assertEqual(recovered.active_player_id, actor)
            self.assertEqual(recovered.state.export(), runtime.state.export())
            self.assertEqual(recovered.submit(ActionIR(actor, "drop", ITEM)).status.value, "completed")

    def test_replay_rejects_malformed_transactions_without_partial_world(self) -> None:
        records = self.created().event_log.events
        bad_cases = {}
        for label, edit in {
            "version": lambda e: setattr(e, "version", 2),
            "authority": lambda e: setattr(e, "authority", "ai"),
            "causation": lambda e: setattr(e, "causation_id", "different"),
            "operation": lambda e: e.payload["applied"][0].update(operation="remove"),
            "shape": lambda e: e.payload["applied"][0]["entity"].update(components="inventory"),
            "duplicate": lambda e: e.payload["applied"].append(deepcopy(e.payload["applied"][0])),
            "existing": lambda e: e.payload["applied"][0]["entity"].update(entity_id=ACTOR),
        }.items():
            candidate = deepcopy(records)
            edit(next(e for e in candidate if e.event_type == "entity.committed"))
            bad_cases[label] = candidate
        bad_cases["unpaired"] = [e for e in deepcopy(records) if e.event_type != "state.committed"]
        bad_cases["missing_creator"] = deepcopy(records)
        for event in bad_cases["missing_creator"]:
            event.source = "unknown.creator"
        for label, candidate in bad_cases.items():
            with self.subTest(case=label):
                recovered = self.runtime()
                recovered.submit(ActionIR(ACTOR, "make_keepsake", args={"item_id": "item.pending"}), delay=9)
                before = self.observable(recovered)
                with self.assertRaises(RuntimeErrorBase):
                    recovered.replay(candidate)
                self.assertEqual(self.observable(recovered), before)

    def test_late_replay_failure_rolls_back_valid_creation_and_clock(self) -> None:
        records = deepcopy(self.created().event_log.events)
        records.append(EventIR("unused", "test", {}, timestamp_tick=-1))
        recovered = self.runtime()
        before = self.observable(recovered)
        with self.assertRaises(RuntimeErrorBase):
            recovered.replay(records)
        self.assertEqual(self.observable(recovered), before)

    def test_failing_iterator_preserves_runtime_and_object_identity(self) -> None:
        recovered = self.runtime()
        state, scheduler = recovered.state, recovered.scheduler
        before = self.observable(recovered)

        def broken():
            yield from self.created().event_log.events
            raise OSError("interrupted log read")

        with self.assertRaises(OSError):
            recovered.replay(broken())
        self.assertIs(recovered.state, state)
        self.assertIs(recovered.scheduler, scheduler)
        self.assertEqual(self.observable(recovered), before)

    def test_legacy_snapshot_membership_and_optional_entity_fields(self) -> None:
        runtime = self.created()
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "legacy.json"
            runtime.save_snapshot(snapshot)
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            payload.pop("static_entity_ids")
            payload["dynamic_entities"][0].pop("components")
            payload["dynamic_entities"][0].pop("metadata")
            snapshot.write_text(json.dumps(payload), encoding="utf-8")
            recovered = self.runtime()
            recovered.load_snapshot(snapshot)
        self.assertTrue(recovered.registry.contains(ITEM))
        self.assertEqual(recovered.registry.get(ITEM).components, [])
        self.assertEqual(recovered.registry.get(ITEM).metadata, {})
        self.assertEqual(recovered.state.export(), runtime.state.export())

    def test_plain_runtime_rejects_unsupported_entity_log_before_state_changes(self) -> None:
        base = WorldRuntime.from_package(self.package)
        before = base.state.export()
        with self.assertRaisesRegex(RuntimeErrorBase, "EntityTransactionRuntime"):
            base.replay(self.created().event_log.events)
        self.assertEqual(base.state.export(), before)
        self.assertFalse(base.registry.contains(ITEM))

    def test_entity_replay_accepts_empty_and_parent_state_batches(self) -> None:
        for parent_change in (False, True):
            with self.subTest(parent_change=parent_change):
                runtime = self.runtime()
                action = ActionIR(ACTOR, "make_keepsake")
                result = KeepsakeModule().evaluate(action, runtime)
                result.deltas = (
                    [StateDelta(ACTOR, "lineage", "created_count", "set", 1)]
                    if parent_change else []
                )
                with patch.object(KeepsakeModule, "evaluate", return_value=result):
                    self.assertEqual(runtime.submit(action).status.value, "completed")
                recovered = self.runtime()
                recovered.replay(runtime.event_log.events)
                self.assertEqual(recovered.registry.get(ITEM), runtime.registry.get(ITEM))
                self.assertEqual(recovered.state.export(), runtime.state.export())

    def test_live_creation_rejects_non_roundtrippable_entities_before_commit(self) -> None:
        for label in ("tuple_metadata", "wrong_components", "expected_absent_type", "wrong_source"):
            with self.subTest(case=label):
                runtime = self.runtime()
                action = ActionIR(ACTOR, "make_keepsake")
                result = KeepsakeModule().evaluate(action, runtime)
                entity_delta = result.entity_deltas[0]
                if label == "tuple_metadata":
                    entity_delta.entity.metadata["bad"] = (1, 2)
                elif label == "wrong_components":
                    entity_delta.entity.components = "inventory"
                elif label == "expected_absent_type":
                    entity_delta.expected_absent = 1
                else:
                    entity_delta.source_module = "different.creator"
                before_state = runtime.state.export()
                with patch.object(KeepsakeModule, "evaluate", return_value=result):
                    self.assertEqual(runtime.submit(action).status.value, "failed")
                self.assertEqual(runtime.state.export(), before_state)
                self.assertFalse(runtime.registry.contains(ITEM))
                self.assertEqual([event.event_type for event in runtime.event_log.events], ["action.failed"])

    def test_replaced_scheduled_actor_fails_without_an_unreplayable_creation(self) -> None:
        runtime = self.runtime()
        runtime.submit(ActionIR(ACTOR, "make_keepsake"), delay=1)
        actor = runtime.create_player(generate_character(seed=28, package=runtime.package))
        receipts = runtime.advance(1)
        self.assertEqual(receipts[0].status.value, "failed")
        self.assertFalse(runtime.registry.contains(ITEM))
        self.assertFalse(runtime.registry.contains(ACTOR))
        self.assertEqual(
            [event.event_type for event in runtime.event_log.events
             if event.event_type.startswith("action.")],
            ["action.scheduled", "action.started", "action.failed"],
        )
        recovered = self.runtime()
        recovered.replay(runtime.event_log.events)
        self.assertEqual(recovered.state.export(), runtime.state.export())
        self.assertEqual(recovered.scheduler.export(), runtime.scheduler.export())
        self.assertEqual(recovered.dynamic_entities, {actor})

    def test_removed_package_ids_remain_reserved_for_live_create_and_replay(self) -> None:
        runtime = self.runtime()
        actor = runtime.create_player(generate_character(seed=29, package=runtime.package))
        self.assertFalse(runtime.registry.contains(ACTOR))
        before = runtime.state.export()
        receipt = runtime.submit(ActionIR(actor, "make_keepsake", args={"item_id": ACTOR}))
        self.assertEqual(receipt.status.value, "failed")
        self.assertEqual(runtime.state.export(), before)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "reserved.json"
            runtime.save_snapshot(snapshot)
            recovered = self.runtime()
            recovered.load_snapshot(snapshot)
            self.assertEqual(recovered.state.export(), runtime.state.export())

        runtime.submit(ActionIR(actor, "make_keepsake"))
        records = deepcopy(runtime.event_log.events)
        entity_event = next(event for event in records if event.event_type == "entity.committed")
        entity_event.payload["applied"][0]["entity"]["entity_id"] = ACTOR
        recovered = self.runtime()
        initial = self.observable(recovered)
        with self.assertRaisesRegex(RuntimeErrorBase, "reserved Package"):
            recovered.replay(records)
        self.assertEqual(self.observable(recovered), initial)

    def test_invalid_snapshot_and_append_failure_leave_live_entity_unchanged(self) -> None:
        runtime = self.created()
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / "snapshot.json"
            runtime.save_snapshot(snapshot)
            original = snapshot.read_text(encoding="utf-8")
            payload = json.loads(original)
            payload["dynamic_entities"][0]["entity_type"] = []
            snapshot.write_text(json.dumps(payload), encoding="utf-8")
            before = self.observable(runtime)
            with self.assertRaises(RuntimeErrorBase):
                runtime.load_snapshot(snapshot)
            self.assertEqual(self.observable(runtime), before)
            snapshot.write_text(original, encoding="utf-8")
            with patch.object(runtime.event_log, "append", side_effect=KernelTransactionError("disk failure")):
                with self.assertRaises(KernelTransactionError):
                    runtime.load_snapshot(snapshot)
            self.assertEqual(self.observable(runtime), before)


if __name__ == "__main__":
    unittest.main()
