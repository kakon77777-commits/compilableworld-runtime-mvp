from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import compile_world
from compilableworld.kernel import WorldRuntime
from compilableworld.models import EventIR
from compilableworld.kernel import RuntimeErrorBase
from compilableworld_mcp import (
    ReadOnlyWorldService,
    RuntimeBindingRecord,
    RuntimeBindingStore,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"


class RuntimeBindingTests(unittest.TestCase):
    def test_event_log_is_loaded_for_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = compile_world(EXAMPLE, Path(directory) / "build")
            event_log = Path(directory) / "events.jsonl"
            runtime = WorldRuntime.from_package(package, event_log)
            runtime.event_log.append(EventIR("world.restartable", "test", {"value": 1}, event_id="event-restart-1"))

            restarted = WorldRuntime.from_package(package, event_log)

        self.assertEqual([event.event_id for event in restarted.event_log.events], ["event-restart-1"])
        self.assertEqual(restarted.event_log.events[0].payload["value"], 1)

    def test_event_log_rejects_duplicate_ids_instead_of_silently_dropping_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = compile_world(EXAMPLE, Path(directory) / "build")
            event_log = Path(directory) / "events.jsonl"
            event = EventIR("world.duplicate", "test", {}, event_id="event-duplicate")
            encoded = json.dumps(event.to_dict(), ensure_ascii=False)
            event_log.write_text(f"{encoded}\n{encoded}\n", encoding="utf-8")

            with self.assertRaises(RuntimeErrorBase):
                WorldRuntime.from_package(package, event_log)

    def test_event_log_rejects_duplicate_ids_before_append(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = compile_world(EXAMPLE, Path(directory) / "build")
            event_log = Path(directory) / "events.jsonl"
            runtime = WorldRuntime.from_package(package, event_log)
            event = EventIR("world.duplicate", "test", {}, event_id="event-duplicate")
            runtime.event_log.append(event)
            before = event_log.read_text(encoding="utf-8")

            with self.assertRaises(RuntimeErrorBase):
                runtime.event_log.append(event)

            self.assertEqual([item.event_id for item in runtime.event_log.events], ["event-duplicate"])
            self.assertEqual(event_log.read_text(encoding="utf-8"), before)

    def test_sqlite_binding_store_rehydrates_package_snapshot_and_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = compile_world(EXAMPLE, root / "build")
            manifest = json.loads(package.read_text(encoding="utf-8"))["manifest"]
            event_log = root / "events.jsonl"
            snapshot = root / "world.snapshot.json"
            runtime = WorldRuntime.from_package(package, event_log)
            runtime.event_log.append(EventIR("world.restartable", "test", {"value": 2}, event_id="event-restart-2"))
            runtime.save_snapshot(snapshot)

            database = root / "bindings.sqlite3"
            RuntimeBindingStore(database).register(
                RuntimeBindingRecord(
                    world_id=manifest["world_id"],
                    runtime_instance_id="runtime-binding-1",
                    package_path=str(package),
                    event_log_path=str(event_log),
                    snapshot_path=str(snapshot),
                )
            )
            service = ReadOnlyWorldService()
            result = service.rehydrate_from_binding_store(RuntimeBindingStore(database))
            restored = service.runtime_for_testing(manifest["world_id"])

        self.assertEqual(result["restored"], 1)
        self.assertEqual(restored.event_log.events[0].event_id, "event-restart-2")
        self.assertEqual(restored.event_log.events[0].payload["value"], 2)
        self.assertEqual(restored.scheduler.tick, 0)


if __name__ == "__main__":
    unittest.main()
