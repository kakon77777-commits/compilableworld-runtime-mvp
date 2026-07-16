from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from compilableworld.compiler import compile_world
from compilableworld.kernel import WorldRuntime
from compilableworld.models import ActionIR, ActionStatus
from compilableworld.modules import install_builtin_modules


ROOT = Path(__file__).resolve().parents[1]
PEACE_CITY = ROOT / "examples" / "mingyun_zhiyu_peace_city"


class LongSessionValidationTests(unittest.TestCase):
    def test_hundred_turn_observation_session_preserves_state_and_replays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = json.loads(compile_world(PEACE_CITY, root / "build").read_text(encoding="utf-8"))
            event_log = root / "events.jsonl"
            runtime = WorldRuntime(package, event_log)
            install_builtin_modules(runtime)
            actor_id = "player.newcomer"
            baseline = runtime.state.export()

            receipts = []
            for turn in range(100):
                for index, verb in enumerate(("look", "inventory", "status")):
                    action = ActionIR(
                        actor_id=actor_id,
                        verb=verb,
                        args={"turn": turn, "observation": index},
                        authority="scenario",
                    )
                    receipt = runtime.submit(action)
                    receipts.append(receipt)
                    self.assertEqual(receipt.status, ActionStatus.COMPLETED, receipt.message)

            self.assertEqual(runtime.state.export(), baseline)
            self.assertEqual(len(receipts), 300)
            self.assertEqual(runtime.diagnostics()["metrics"]["actions_completed"], 300)
            self.assertEqual(len(runtime.event_log.events), 600)
            event_ids = [event.event_id for event in runtime.event_log.events]
            self.assertEqual(len(event_ids), len(set(event_ids)))
            self.assertTrue(all(event.causation_id for event in runtime.event_log.events))

            snapshot = root / "snapshot.json"
            runtime.save_snapshot(snapshot)
            restored = WorldRuntime(package, event_log)
            install_builtin_modules(restored)
            restored.load_snapshot(snapshot)
            self.assertEqual(restored.state.export(), runtime.state.export())
            self.assertEqual(restored.scheduler.tick, runtime.scheduler.tick)

            replayed = WorldRuntime(package)
            replayed.replay(runtime.event_log.events)
            self.assertEqual(replayed.state.export(), runtime.state.export())


if __name__ == "__main__":
    unittest.main()
