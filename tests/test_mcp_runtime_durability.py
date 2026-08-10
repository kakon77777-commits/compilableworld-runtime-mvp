from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from compilableworld_mcp import RuntimeDurabilityError, RuntimeDurabilityStore


class RuntimeDurabilityStoreTests(unittest.TestCase):
    NOW = 1_800_000_000

    def test_sqlite_projection_survives_restart_and_is_idempotent(self) -> None:
        events = [
            {"event_id": "event-1", "event_type": "state.committed", "payload": {"ok": True}},
            {"event_id": "event-2", "event_type": "look.completed", "payload": {}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "durability.sqlite3"
            store = RuntimeDurabilityStore(database)
            first = store.record_runtime_commit(
                "runtime-1",
                "action-1",
                {"state::cell": {"value": 1, "version": 1}},
                events,
                now=self.NOW,
            )
            duplicate = RuntimeDurabilityStore(database).record_runtime_commit(
                "runtime-1",
                "action-1",
                {"state::cell": {"value": 1, "version": 1}},
                events,
                now=self.NOW + 1,
            )
            state, loaded_events = RuntimeDurabilityStore(database).load("runtime-1", "action-1")

        self.assertEqual(first.commit_id, duplicate.commit_id)
        self.assertEqual(first.event_ids, ("event-1", "event-2"))
        self.assertEqual(state["state::cell"]["value"], 1)
        self.assertEqual([item["event_id"] for item in loaded_events], ["event-1", "event-2"])

    def test_projection_conflict_and_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "durability.sqlite3"
            store = RuntimeDurabilityStore(database)
            store.record_runtime_commit(
                "runtime-1",
                "action-1",
                {"value": 1},
                [{"event_id": "event-1"}],
                now=self.NOW,
            )
            with self.assertRaisesRegex(RuntimeDurabilityError, "different projection"):
                store.record_runtime_commit(
                    "runtime-1",
                    "action-1",
                    {"value": 2},
                    [{"event_id": "event-1"}],
                    now=self.NOW,
                )
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "UPDATE mcp_runtime_commit_projection SET state_json = ?",
                    ('{"value":999}',),
                )
                connection.commit()
            finally:
                connection.close()
            with self.assertRaisesRegex(RuntimeDurabilityError, "hash"):
                store.load("runtime-1", "action-1")


if __name__ == "__main__":
    unittest.main()
