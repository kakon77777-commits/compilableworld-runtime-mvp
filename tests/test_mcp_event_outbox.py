from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from compilableworld.models import EventIR
from compilableworld_mcp import RuntimeEventOutboxBridge, TransactionalOutbox


class RuntimeEventOutboxBridgeTests(unittest.TestCase):
    NOW = 1_800_000_000

    def test_event_log_replay_is_deduplicated_after_bridge_restart(self) -> None:
        events = [
            EventIR("state.committed", "module", {"index": 1}, event_id="event-1"),
            EventIR("dialogue.responded", "dialogue", {"index": 2}, event_id="event-2"),
        ]
        runtime = SimpleNamespace(event_log=SimpleNamespace(events=events))
        with tempfile.TemporaryDirectory() as directory:
            outbox = TransactionalOutbox(Path(directory) / "outbox.sqlite3")
            bridge = RuntimeEventOutboxBridge("runtime-1", outbox)
            self.assertEqual(bridge.drain(runtime, now=self.NOW), 2)
            claimed = outbox.claim("worker-1", limit=10, now=self.NOW)
            self.assertCountEqual([record.aggregate_id for record in claimed], ["event-1", "event-2"])
            for record in claimed:
                outbox.ack(record.outbox_id, "worker-1", now=self.NOW)

            restarted = RuntimeEventOutboxBridge("runtime-1", TransactionalOutbox(Path(directory) / "outbox.sqlite3"))
            self.assertEqual(restarted.drain(runtime, now=self.NOW), 2)
            self.assertEqual(restarted.outbox.claim("worker-2", now=self.NOW), [])

    def test_same_event_id_in_different_runtime_instances_is_not_collapsed(self) -> None:
        runtime = SimpleNamespace(
            event_log=SimpleNamespace(events=[EventIR("event", "source", {}, event_id="same-event")])
        )
        outbox = TransactionalOutbox()
        RuntimeEventOutboxBridge("runtime-a", outbox).drain(runtime, now=self.NOW)
        RuntimeEventOutboxBridge("runtime-b", outbox).drain(runtime, now=self.NOW)
        self.assertEqual(len(outbox.claim("worker", limit=10, now=self.NOW)), 2)


if __name__ == "__main__":
    unittest.main()
