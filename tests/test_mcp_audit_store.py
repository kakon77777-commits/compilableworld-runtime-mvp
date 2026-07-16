from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from compilableworld_mcp import AuditStore, AuditStoreError, MCP_AUDIT_ENVELOPE_CONTRACT


def envelope(*, request_id: str, operation: str, occurred_at: int, world_id: str = "world-1") -> dict[str, object]:
    return {
        "format": MCP_AUDIT_ENVELOPE_CONTRACT,
        "request_id": request_id,
        "operation": operation,
        "outcome": "success",
        "occurred_at": occurred_at,
        "transport": "http",
        "client_id": "client-1",
        "principal_user_id": "user-1",
        "principal_token_id": "principal-1",
        "session_id": "session-1",
        "world_id": world_id,
        "runtime_instance_id": "runtime-1",
        "actor_id": "player-1",
        "role": "player",
        "world_state_changed": False,
        "event_ids": [],
        "idempotency_key": None,
        "error_code": None,
        "delivery_pending": False,
        "replayed": False,
    }


class AuditStoreTests(unittest.TestCase):
    NOW = 1_800_000_000

    def test_process_local_sink_appends_and_filters_newest_first(self) -> None:
        store = AuditStore()
        store.append(envelope(request_id="request-1", operation="world.status", occurred_at=self.NOW), now=self.NOW)
        store.append(envelope(request_id="request-2", operation="action.submit", occurred_at=self.NOW + 1), now=self.NOW + 1)

        records = store.query(world_id="world-1", operation="action.submit")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["request_id"], "request-2")
        self.assertEqual(records[0]["envelope"]["principal_user_id"], "user-1")

    def test_sqlite_sink_survives_restart_and_supports_after_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "audit.sqlite3"
            AuditStore(database).append(
                envelope(request_id="request-1", operation="world.status", occurred_at=self.NOW),
                now=self.NOW,
            )
            AuditStore(database).append(
                envelope(request_id="request-2", operation="world.scene", occurred_at=self.NOW + 2),
                now=self.NOW + 2,
            )
            records = AuditStore(database).query(after=self.NOW)

        self.assertEqual([record["request_id"] for record in records], ["request-2"])

    def test_sink_rejects_invalid_or_sensitive_envelopes(self) -> None:
        store = AuditStore()
        with self.assertRaisesRegex(AuditStoreError, "forbidden field"):
            store.append({**envelope(request_id="request-1", operation="world.status", occurred_at=self.NOW), "session_token": "secret"})
        with self.assertRaisesRegex(AuditStoreError, "format"):
            store.append({**envelope(request_id="request-2", operation="world.status", occurred_at=self.NOW), "format": "wrong"})
        with self.assertRaisesRegex(AuditStoreError, "limit"):
            store.query(limit=0)

    def test_sqlite_hash_chain_detects_direct_record_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "audit.sqlite3"
            store = AuditStore(database)
            first = store.append(envelope(request_id="request-1", operation="world.status", occurred_at=self.NOW), now=self.NOW)
            second = store.append(envelope(request_id="request-2", operation="world.scene", occurred_at=self.NOW + 1), now=self.NOW + 1)
            self.assertEqual(store.verify_chain(), 2)
            self.assertEqual(second.previous_hash, first.record_hash)
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "UPDATE mcp_audit SET envelope_json = ? WHERE audit_id = ?",
                    ('{"tampered":true}', first.audit_id),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(AuditStoreError, "hash chain"):
                AuditStore(database)

    def test_sqlite_anchor_survives_restart_and_verifies_chain_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "audit.sqlite3"
            store = AuditStore(database)
            store.append(envelope(request_id="request-1", operation="world.status", occurred_at=self.NOW), now=self.NOW)
            store.append(envelope(request_id="request-2", operation="world.scene", occurred_at=self.NOW + 1), now=self.NOW + 1)
            anchor = store.create_anchor(now=self.NOW + 2)
            verified = AuditStore(database).verify_anchor(anchor.anchor_id)

        self.assertEqual(verified.anchor_id, anchor.anchor_id)
        self.assertEqual(verified.record_count, 2)
        self.assertEqual(verified.chain_head, anchor.chain_head)


if __name__ == "__main__":
    unittest.main()
