from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from compilableworld_mcp import RuntimeQuorumError, RuntimeQuorumGate


class RuntimeQuorumGateTests(unittest.TestCase):
    NOW = 1_800_000_000

    def test_majority_gate_rejects_single_host_and_accepts_distinct_member_votes(self) -> None:
        gate = RuntimeQuorumGate(["host-a", "host-b", "host-c"])
        term = gate.open_term("host-a", now=self.NOW)

        with self.assertRaisesRegex(RuntimeQuorumError, "requires 2 votes"):
            gate.require_quorum(term.term)
        gate.record_vote(term.term, "host-a", now=self.NOW)
        duplicate = gate.record_vote(term.term, "host-a", now=self.NOW + 1)
        self.assertEqual(duplicate.votes, ("host-a",))
        quorum = gate.record_vote(term.term, "host-b", now=self.NOW + 2)

        self.assertTrue(quorum.quorum_reached)
        self.assertEqual(gate.require_quorum(term.term).votes, ("host-a", "host-b"))
        with self.assertRaisesRegex(RuntimeQuorumError, "configured quorum member"):
            gate.record_vote(term.term, "host-x")

    def test_sqlite_quorum_survives_restart_and_rejects_membership_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "quorum.sqlite3"
            gate = RuntimeQuorumGate(["host-a", "host-b", "host-c"], db_path=database)
            term = gate.open_term("host-a", now=self.NOW)
            gate.record_vote(term.term, "host-a", now=self.NOW)
            gate.record_vote(term.term, "host-b", now=self.NOW + 1)
            restarted = RuntimeQuorumGate(["host-a", "host-b", "host-c"], db_path=database)
            status = restarted.require_quorum(term.term)
            next_term = restarted.open_term("host-c", now=self.NOW + 2)
            self.assertEqual(status.term, term.term)
            self.assertEqual(next_term.term, term.term + 1)

            with self.assertRaisesRegex(RuntimeQuorumError, "membership"):
                RuntimeQuorumGate(["host-a", "host-b"], db_path=database)


if __name__ == "__main__":
    unittest.main()
