from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import compile_world
from compilableworld_mcp import (
    ActionReservationError,
    ActionReservationStore,
    ActionCommitJournalStore,
    BearerPrincipalResolver,
    HMACKeyRing,
    OutboxError,
    PrincipalTokenCodec,
    RequestAuthContext,
    RequestSecurityError,
    RequestSecurityPipeline,
    SecureActionMCPGateway,
    SecureReadOnlyMCPGateway,
    SessionTokenCodec,
    TransactionalOutbox,
    AuditStore,
    RuntimeDurabilityStore,
    SlidingWindowRateLimiter,
    JOURNAL_STATUS_OUTBOX_ENQUEUED,
    JOURNAL_STATUS_RUNTIME_COMMITTED,
)
from compilableworld_mcp.action_ledger import RESERVATION_STATUS_COMPLETED


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"


class ActionControlPrimitiveTests(unittest.TestCase):
    NOW = 1_800_000_000

    def test_rate_limiter_returns_retry_metadata(self) -> None:
        limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)
        self.assertTrue(limiter.consume("actor", now=self.NOW).allowed)
        self.assertTrue(limiter.consume("actor", now=self.NOW).allowed)
        blocked = limiter.consume("actor", now=self.NOW)
        self.assertFalse(blocked.allowed)
        self.assertGreaterEqual(blocked.retry_after_seconds, 1)

    def test_sqlite_rate_limiter_shares_window_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "rate-limit.sqlite3"
            first = SlidingWindowRateLimiter(limit=1, window_seconds=10, db_path=database)
            second = SlidingWindowRateLimiter(limit=1, window_seconds=10, db_path=database)
            self.assertTrue(first.consume("shared", now=self.NOW).allowed)
            self.assertFalse(second.consume("shared", now=self.NOW).allowed)

    def test_reservation_is_idempotent_and_sqlite_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "actions.sqlite3"
            store = ActionReservationStore(database)
            first = store.reserve("session-1", "key-1", "fingerprint-1", "action-1", now=self.NOW)
            completed = store.complete(
                "session-1",
                "key-1",
                "action-1",
                {"status": "completed"},
                succeeded=True,
                now=self.NOW,
            )
            self.assertEqual(first.status, "reserved")
            self.assertEqual(completed.status, RESERVATION_STATUS_COMPLETED)
            replay = ActionReservationStore(database).reserve(
                "session-1", "key-1", "fingerprint-1", "action-retry", now=self.NOW
            )
            self.assertEqual(replay.result, {"status": "completed"})
            with self.assertRaisesRegex(ActionReservationError, "different action"):
                store.reserve("session-1", "key-1", "different", "action-2", now=self.NOW)

    def test_outbox_claim_retry_and_ack_are_worker_scoped(self) -> None:
        outbox = TransactionalOutbox()
        record = outbox.enqueue("action.receipt", "session-1", {"ok": True}, now=self.NOW)
        claimed = outbox.claim("worker-a", now=self.NOW)
        self.assertEqual(claimed[0].outbox_id, record.outbox_id)
        with self.assertRaisesRegex(OutboxError, "not claimed"):
            outbox.ack(record.outbox_id, "worker-b", now=self.NOW)
        retried = outbox.retry(record.outbox_id, "worker-a", retry_after_seconds=5, now=self.NOW)
        self.assertEqual(retried.status, "pending")
        self.assertEqual(outbox.claim("worker-a", now=self.NOW + 5)[0].attempts, 2)
        self.assertEqual(outbox.ack(record.outbox_id, "worker-a", now=self.NOW + 5).status, "acked")

    def test_sqlite_commit_journal_recovers_a_runtime_commit_into_the_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = ActionCommitJournalStore(root / "journal.sqlite3")
            reservation_store = ActionReservationStore(root / "reservations.sqlite3")
            reservation_store.reserve("session-1", "key-1", "fingerprint-1", "action-1", now=self.NOW)
            prepared = journal.prepare("session-1", "key-1", "action-1", "runtime-1", now=self.NOW)
            committed = journal.record_runtime_committed(
                "session-1",
                "key-1",
                "action-1",
                {"receipt": {"action_id": "action-1", "status": "completed"}},
                now=self.NOW,
            )
            self.assertEqual(prepared.status, "prepared")
            self.assertEqual(committed.status, JOURNAL_STATUS_RUNTIME_COMMITTED)

            outbox = TransactionalOutbox(root / "outbox.sqlite3")
            recovered = ActionCommitJournalStore(root / "journal.sqlite3").recover_outbox(
                outbox,
                reservation_store=ActionReservationStore(root / "reservations.sqlite3"),
                now=self.NOW + 1,
            )
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0].status, JOURNAL_STATUS_OUTBOX_ENQUEUED)
            self.assertEqual(ActionCommitJournalStore(root / "journal.sqlite3").pending_delivery(), [])
            self.assertEqual(outbox.get(recovered[0].outbox_id).payload["receipt"]["action_id"], "action-1")
            self.assertEqual(
                ActionReservationStore(root / "reservations.sqlite3").get("session-1", "key-1").status,
                RESERVATION_STATUS_COMPLETED,
            )

    def test_shared_sqlite_commit_journal_and_outbox_handoff_is_atomic_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "commit.sqlite3"
            journal = ActionCommitJournalStore(database)
            outbox = TransactionalOutbox(database)
            journal.prepare("session-1", "key-1", "action-1", "runtime-1", now=self.NOW)

            committed, queued = journal.record_runtime_and_enqueue_outbox(
                outbox,
                "session-1",
                "key-1",
                "action-1",
                "runtime-1",
                {"receipt": {"action_id": "action-1", "status": "completed"}},
                now=self.NOW,
            )
            replayed, replayed_queue = journal.record_runtime_and_enqueue_outbox(
                outbox,
                "session-1",
                "key-1",
                "action-1",
                "runtime-1",
                {"receipt": {"action_id": "action-1", "status": "completed"}},
                now=self.NOW + 1,
            )
            claimed = TransactionalOutbox(database).claim("worker", now=self.NOW)

        self.assertEqual(committed.status, JOURNAL_STATUS_OUTBOX_ENQUEUED)
        self.assertEqual(committed.outbox_id, queued.outbox_id)
        self.assertEqual(replayed.outbox_id, queued.outbox_id)
        self.assertEqual(replayed_queue.outbox_id, queued.outbox_id)
        self.assertEqual(len(claimed), 1)

    def test_shared_sqlite_handoff_rolls_back_when_outbox_insert_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "commit.sqlite3"
            journal = ActionCommitJournalStore(database)
            outbox = TransactionalOutbox(database)
            journal.prepare("session-1", "key-1", "action-1", "runtime-1", now=self.NOW)
            with patch.object(
                outbox,
                "enqueue_in_connection",
                side_effect=OutboxError("SIMULATED_OUTBOX_FAILURE", "simulated outbox failure"),
            ):
                with self.assertRaises(OutboxError):
                    journal.record_runtime_and_enqueue_outbox(
                        outbox,
                        "session-1",
                        "key-1",
                        "action-1",
                        "runtime-1",
                        {"receipt": {"action_id": "action-1", "status": "completed"}},
                        now=self.NOW,
                    )
            state = ActionCommitJournalStore(database).get("session-1", "key-1")
            pending = TransactionalOutbox(database).claim("worker", now=self.NOW)

        self.assertEqual(state.status, "prepared")
        self.assertEqual(pending, [])


class SecureActionGatewayTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package_path = compile_world(EXAMPLE, Path(self.temp.name) / "build")
        from compilableworld_mcp import ReadOnlyWorldService

        self.service = ReadOnlyWorldService()
        self.world_id = self.service.register_package(package_path, runtime_instance_id="runtime-action")
        ring = HMACKeyRing({"k1": b"s" * 32}, active_kid="k1")
        principal_codec = PrincipalTokenCodec(ring, issuer="https://issuer.example", audience="compilableworld")
        session_codec = SessionTokenCodec(ring, issuer="https://issuer.example", audience="compilableworld")
        principal_token = principal_codec.issue(
            user_id="user-1",
            client_id="secure-client",
            roles=["player"],
            now=self.NOW,
            ttl_seconds=300,
            token_id="principal-action-1",
        )
        self.authorization = f"Bearer {principal_token}"
        pipeline = RequestSecurityPipeline(BearerPrincipalResolver(principal_codec), session_codec)
        secure_gateway = SecureReadOnlyMCPGateway(self.service, pipeline, session_codec, session_ttl_seconds=120)
        self.action_gateway = SecureActionMCPGateway(secure_gateway, rate_limit=10)
        opened = secure_gateway.open_world_session(self._context(), self.world_id, now=self.NOW)
        self.session_token = opened["session_token"]
        self.session_id = opened["session"]["session_id"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _context(self, *, session_token: str | None = None) -> RequestAuthContext:
        return RequestAuthContext(
            request_id="action-request-1",
            transport="http",
            client_id="secure-client",
            authorization=self.authorization,
            session_token=session_token,
        )

    def test_submit_action_is_actor_bound_and_replayable(self) -> None:
        context = self._context(session_token=self.session_token)
        result = self.action_gateway.submit_action(
            context,
            {"verb": "look", "args": {}},
            "idem-look-1",
            now=self.NOW,
        )
        self.assertTrue(result["world_state_changed"])
        self.assertTrue(result["outbox_enqueued"])
        self.assertEqual(result["audit"]["operation"], "action.submit")
        self.assertEqual(result["audit"]["event_ids"], result["receipt"]["event_ids"])
        self.assertEqual(
            self.action_gateway.commit_journal.get(self.session_id, "idem-look-1").status,
            JOURNAL_STATUS_OUTBOX_ENQUEUED,
        )
        replay = self.action_gateway.submit_action(
            context,
            {"verb": "look", "args": {}},
            "idem-look-1",
            now=self.NOW,
        )
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["audit"]["operation"], "action.replay")
        self.assertEqual(replay["receipt"]["action_id"], result["receipt"]["action_id"])

        with self.assertRaisesRegex(ValueError, "different action"):
            self.action_gateway.submit_action(
                context,
                {"verb": "inventory", "args": {}},
                "idem-look-1",
                now=self.NOW,
            )

    def test_gateway_uses_atomic_shared_sqlite_handoff(self) -> None:
        database = Path(self.temp.name) / "shared-commit.sqlite3"
        journal = ActionCommitJournalStore(database)
        outbox = TransactionalOutbox(database)
        gateway = SecureActionMCPGateway(
            self.action_gateway.secure_gateway,
            reservation_store=ActionReservationStore(),
            outbox=outbox,
            commit_journal=journal,
        )

        result = gateway.submit_action(
            self._context(session_token=self.session_token),
            {"verb": "look", "args": {}},
            "idem-shared-commit-1",
            now=self.NOW,
        )

        journal_record = journal.get(self.session_id, "idem-shared-commit-1")
        queued = outbox.claim("worker-shared", now=self.NOW)
        self.assertTrue(result["outbox_enqueued"])
        self.assertEqual(journal_record.status, JOURNAL_STATUS_OUTBOX_ENQUEUED)
        self.assertEqual(journal_record.outbox_id, queued[0].outbox_id)

    def test_gateway_records_restart_verifiable_runtime_projection(self) -> None:
        database = Path(self.temp.name) / "runtime-durability.sqlite3"
        durable = RuntimeDurabilityStore(database)
        gateway = SecureActionMCPGateway(
            self.action_gateway.secure_gateway,
            reservation_store=ActionReservationStore(database),
            outbox=TransactionalOutbox(database),
            commit_journal=ActionCommitJournalStore(database),
            durability_store=durable,
        )
        result = gateway.submit_action(
            self._context(session_token=self.session_token),
            {"verb": "look", "args": {}},
            "idem-runtime-durability-1",
            now=self.NOW,
        )

        metadata = result["runtime_durability"]
        self.assertTrue(metadata["persisted"])
        self.assertEqual(metadata["event_ids"], result["receipt"]["event_ids"])
        state, events = RuntimeDurabilityStore(database).load("runtime-action", result["receipt"]["action_id"])
        self.assertIsInstance(state, dict)
        self.assertEqual([event["event_id"] for event in events], result["receipt"]["event_ids"])

    def test_submit_action_rejects_actor_spoofing_and_applies_rate_limit(self) -> None:
        context = self._context(session_token=self.session_token)
        with self.assertRaisesRegex(ValueError, "actor"):
            self.action_gateway.submit_action(
                context,
                {"actor_id": "npc.foreman_laotie", "verb": "look"},
                "idem-spoof-1",
                now=self.NOW,
            )

        limited = SecureActionMCPGateway(
            self.action_gateway.secure_gateway,
            rate_limiter=SlidingWindowRateLimiter(limit=1, window_seconds=60),
            reservation_store=ActionReservationStore(),
            outbox=TransactionalOutbox(),
            rate_limit=1,
        )
        limited.submit_action(context, {"verb": "look"}, "idem-rate-1", now=self.NOW)
        with self.assertRaisesRegex(RequestSecurityError, "rate limit"):
            limited.submit_action(context, {"verb": "inventory"}, "idem-rate-2", now=self.NOW)

    def test_action_gateway_persists_submit_and_replay_audits(self) -> None:
        database = Path(self.temp.name) / "audit.sqlite3"
        audited = SecureActionMCPGateway(
            self.action_gateway.secure_gateway,
            reservation_store=ActionReservationStore(),
            audit_store=AuditStore(database),
        )
        context = self._context(session_token=self.session_token)
        audited.submit_action(context, {"verb": "look"}, "idem-audit-1", now=self.NOW)
        audited.submit_action(context, {"verb": "look"}, "idem-audit-1", now=self.NOW + 1)

        records = AuditStore(database).query(session_id=self.session_id)
        self.assertEqual({record["operation"] for record in records}, {"action.submit", "action.replay"})


if __name__ == "__main__":
    unittest.main()
