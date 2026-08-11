from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from compilableworld.compiler import compile_world
from compilableworld.kernel import EventBus, RuntimeErrorBase, WorldRuntime
from compilableworld.models import EventIR


ROOT = Path(__file__).resolve().parents[1]
GRAY_CROWN = ROOT / "examples" / "gray_crown"


class EventBusTests(unittest.TestCase):
    def test_reentrant_events_follow_committed_fifo_batch_order(self) -> None:
        with self.assertRaises(ValueError):
            EventBus(max_events_per_cascade=0)
        bus = EventBus(max_events_per_cascade=16)
        with self.assertRaises(ValueError):
            bus.max_events_per_cascade = True
        observed: list[str] = []

        def first_root_callback(event: EventIR) -> None:
            observed.append("root:first")
            bus.publish(EventIR("child", "test", {"parent": event.event_id}))

        bus.subscribe("root", first_root_callback)
        bus.subscribe("root", lambda event: observed.append("root:second"))
        bus.subscribe("sibling", lambda event: observed.append("sibling"))
        bus.subscribe("child", lambda event: observed.append("child"))

        bus.publish_batch([
            EventIR("root", "test", {}),
            EventIR("sibling", "test", {}),
        ])

        self.assertEqual(observed, ["root:first", "root:second", "sibling", "child"])
        self.assertEqual(bus.diagnostics()["last_cascade"]["dispatched_events"], 3)
        self.assertFalse(bus.diagnostics()["last_cascade"]["halted"])

    def test_cascade_limit_halts_without_recursion_and_is_replay_observable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = json.loads(
                compile_world(GRAY_CROWN, Path(temp) / "build").read_text(encoding="utf-8")
            )
        runtime = WorldRuntime(package)
        runtime.events.max_events_per_cascade = 3
        observed: list[str] = []

        def repeat(event: EventIR) -> None:
            observed.append(event.event_type)
            index = int(event.event_type.rsplit(".", 1)[1])
            runtime.events.publish(EventIR(f"loop.{index + 1}", "test.loop", {}))

        runtime.events.subscribe("loop.*", repeat)
        runtime.events.publish(EventIR("loop.0", "test.loop", {}))

        self.assertEqual(observed, ["loop.0", "loop.1", "loop.2"])
        diagnostic = runtime.diagnostics()["event_dispatch"]
        self.assertEqual(diagnostic["halt_count"], 1)
        self.assertEqual(diagnostic["queued_events"], 0)
        self.assertTrue(diagnostic["last_cascade"]["halted"])
        self.assertEqual(diagnostic["last_cascade"]["undispatched_events"], 1)
        halt_event = runtime.event_log.events[-1]
        self.assertEqual(halt_event.event_type, "runtime.reaction_halted")
        self.assertEqual(halt_event.visibility, "audit")

        replayed = WorldRuntime(deepcopy(package))
        replayed.replay(runtime.event_log.events)
        self.assertEqual(replayed.events.halt_count, 1)
        self.assertEqual(
            replayed.events.last_cascade["root_event_id"],
            diagnostic["last_cascade"]["root_event_id"],
        )

        tampered = deepcopy(runtime.event_log.events)
        tampered[-1].payload["dispatched_events"] = 2
        with self.assertRaisesRegex(RuntimeErrorBase, "event cascade boundary"):
            WorldRuntime(deepcopy(package)).replay(tampered)


if __name__ == "__main__":
    unittest.main()
