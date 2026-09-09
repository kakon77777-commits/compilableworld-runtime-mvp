from __future__ import annotations

import unittest
from unittest.mock import patch

from compilableworld.entity_transaction import ENTITY_TRANSACTION_CAPABILITY, EntityTransactionRuntime
from compilableworld.kernel import KernelTransactionError
from compilableworld.models import (
    ActionIR,
    Entity,
    EntityDelta,
    EventIR,
    ModuleContract,
    StateDelta,
    TransitionResult,
)


def minimal_package() -> dict:
    return {
        "format": "compilableworld.runtime-package/v0.1",
        "world": {"world_id": "entity-transaction.test"},
        "entities": [
            {
                "entity_id": "parent.001",
                "entity_type": "creature",
                "name": "Parent",
                "components": ["biology", "position"],
                "metadata": {},
            }
        ],
        "initial_state": [
            {"owner": "parent.001", "namespace": "biology", "key": "energy", "value": 5, "version": 0},
            {"owner": "parent.001", "namespace": "position", "key": "room", "value": "room.spawn", "version": 0},
        ],
        "functions": [],
    }


class SpawnModule:
    contract = ModuleContract(
        module_id="test.spawn",
        version="0.1.0",
        layer="runtime",
        actions=["spawn"],
        events=["test.entity_spawned"],
        read=["biology.*", "position.*"],
        write=["biology.*", "position.*", "lineage.*"],
        requires_kernel=[ENTITY_TRANSACTION_CAPABILITY],
    )

    def evaluate(self, action: ActionIR, runtime: EntityTransactionRuntime) -> TransitionResult:
        child = Entity(
            entity_id="child.001",
            entity_type="creature",
            name="Child",
            components=["position", "lineage"],
            metadata={"provenance": "test"},
        )
        return TransitionResult(
            accepted=True,
            deltas=[
                StateDelta("parent.001", "biology", "energy", "subtract", 1),
                StateDelta("child.001", "position", "room", "set", "room.spawn"),
                StateDelta("child.001", "lineage", "stage", "set", "newborn"),
            ],
            events=[EventIR("test.entity_spawned", self.contract.module_id, {"entity_id": child.entity_id})],
            message="spawned",
            entity_deltas=[EntityDelta(operation="create", entity=child, expected_absent=True)],
        )


class UndeclaredSpawnModule(SpawnModule):
    contract = ModuleContract(
        module_id="test.spawn.undeclared",
        version="0.1.0",
        layer="runtime",
        actions=["spawn"],
        events=["test.entity_spawned"],
        read=["biology.*", "position.*"],
        write=["biology.*", "position.*", "lineage.*"],
        requires_kernel=[],
    )


class EntityTransactionTests(unittest.TestCase):
    def runtime(self, module=None) -> EntityTransactionRuntime:
        runtime = EntityTransactionRuntime(minimal_package())
        runtime.register_module(module or SpawnModule())
        return runtime

    def test_transition_result_keeps_positional_compatibility(self) -> None:
        legacy = TransitionResult(True, [], [], "legacy")
        self.assertEqual(legacy.message, "legacy")
        self.assertEqual(legacy.entity_deltas, [])

    def test_create_commits_entity_state_and_events_together(self) -> None:
        runtime = self.runtime()
        receipt = runtime.submit(ActionIR("parent.001", "spawn"))
        self.assertEqual(receipt.status.value, "completed")
        self.assertTrue(runtime.registry.contains("child.001"))
        self.assertIn("child.001", runtime.dynamic_entities)
        self.assertEqual(runtime.state.get("parent.001", "biology", "energy"), 4)
        self.assertEqual(runtime.state.get("child.001", "lineage", "stage"), "newborn")
        self.assertEqual(receipt.changed_entities, ["child.001"])
        event_types = [event.event_type for event in runtime.event_log.events]
        self.assertIn("entity.committed", event_types)
        self.assertIn("test.entity_spawned", event_types)

    def test_duplicate_create_rolls_back_state_and_entity_changes(self) -> None:
        runtime = self.runtime()
        first = runtime.submit(ActionIR("parent.001", "spawn"))
        self.assertEqual(first.status.value, "completed")
        before_state = runtime.state.export()
        before_entities = {entity.entity_id for entity in runtime.registry.values()}

        second = runtime.submit(ActionIR("parent.001", "spawn"))
        self.assertEqual(second.status.value, "failed")
        self.assertEqual(runtime.state.export(), before_state)
        self.assertEqual({entity.entity_id for entity in runtime.registry.values()}, before_entities)

    def test_event_log_failure_rolls_back_entity_and_state(self) -> None:
        runtime = self.runtime()
        before_state = runtime.state.export()
        with patch.object(runtime.event_log, "append_batch", side_effect=KernelTransactionError("simulated durable failure")):
            with self.assertRaises(KernelTransactionError):
                runtime.submit(ActionIR("parent.001", "spawn"))
        self.assertEqual(runtime.state.export(), before_state)
        self.assertFalse(runtime.registry.contains("child.001"))
        self.assertNotIn("child.001", runtime.dynamic_entities)
        self.assertEqual(runtime.event_log.events, [])

    def test_entity_delta_requires_declared_kernel_capability(self) -> None:
        runtime = self.runtime(UndeclaredSpawnModule())
        receipt = runtime.submit(ActionIR("parent.001", "spawn"))
        self.assertEqual(receipt.status.value, "failed")
        self.assertFalse(runtime.registry.contains("child.001"))
        self.assertEqual(runtime.state.get("parent.001", "biology", "energy"), 5)


if __name__ == "__main__":
    unittest.main()
