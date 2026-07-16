from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from compilableworld_mcp import (
    HMACKeyRing,
    PrincipalTokenCodec,
    RequestSecurityError,
    SessionLifecycleStore,
    SessionTokenCodec,
)


class SessionLifecycleStoreTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        ring = HMACKeyRing({"k1": b"s" * 32}, active_kid="k1")
        self.principal_codec = PrincipalTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        self.session_codec = SessionTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        principal_token = self.principal_codec.issue(
            user_id="user-1",
            client_id="client-1",
            roles=["player"],
            now=self.NOW,
            ttl_seconds=900,
            token_id="principal-jti-raw",
        )
        self.principal = self.principal_codec.verify(principal_token, now=self.NOW)

    def _grant(
        self,
        *,
        session_id: str = "session-1",
        token_id: str = "session-jti-raw",
        world_id: str = "world-1",
        now: int | None = None,
        ttl_seconds: int = 300,
    ):
        token = self.session_codec.issue(
            principal=self.principal,
            session_id=session_id,
            world_id=world_id,
            runtime_instance_id="runtime-1",
            timeline_id="main",
            actor_id="hero",
            role="player",
            now=self.NOW if now is None else now,
            ttl_seconds=ttl_seconds,
            token_id=token_id,
        )
        return self.session_codec.verify(token, principal=self.principal, now=self.NOW if now is None else now)

    def test_process_local_store_revalidates_and_closes_sessions(self) -> None:
        grant = self._grant()
        store = SessionLifecycleStore()
        registered = store.register(grant, now=self.NOW)
        self.assertEqual(registered.safe_metadata()["status"], "active")
        self.assertNotIn("session-jti-raw", str(registered.safe_metadata()))
        store.require_active(grant, now=self.NOW)

        store.close(grant.session_id, now=self.NOW)
        with self.assertRaisesRegex(RequestSecurityError, "closed") as error:
            store.require_active(grant, now=self.NOW)
        self.assertEqual(error.exception.code, "SESSION_CLOSED")

    def test_expired_session_is_marked_and_rejected(self) -> None:
        grant = self._grant(ttl_seconds=10)
        store = SessionLifecycleStore()
        store.register(grant, now=self.NOW)

        with self.assertRaisesRegex(RequestSecurityError, "expired") as error:
            store.require_active(grant, now=self.NOW + 10)
        self.assertEqual(error.exception.code, "SESSION_EXPIRED")

    def test_sqlite_store_survives_new_store_instance_without_raw_jtis(self) -> None:
        grant = self._grant()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "sessions.sqlite3"
            SessionLifecycleStore(database).register(grant, now=self.NOW)
            SessionLifecycleStore(database).require_active(grant, now=self.NOW)
            raw_database = database.read_bytes()

        self.assertNotIn(b"principal-jti-raw", raw_database)
        self.assertNotIn(b"session-jti-raw", raw_database)

    def test_rotation_replaces_active_token_hash(self) -> None:
        old_grant = self._grant(token_id="session-old-jti")
        new_grant = self._grant(token_id="session-new-jti", now=self.NOW + 1)
        store = SessionLifecycleStore()
        store.register(old_grant, now=self.NOW)
        rotated = store.rotate(old_grant, new_grant, now=self.NOW + 1)
        self.assertEqual(rotated.revision, 1)
        store.require_active(new_grant, now=self.NOW + 1)

        with self.assertRaisesRegex(RequestSecurityError, "active token") as error:
            store.require_active(old_grant, now=self.NOW + 1)
        self.assertEqual(error.exception.code, "SESSION_ROTATED")

    def test_scope_mismatch_is_fail_closed(self) -> None:
        grant = self._grant()
        store = SessionLifecycleStore()
        store.register(grant, now=self.NOW)
        mismatched = replace(grant, world_id="world-2")

        with self.assertRaisesRegex(RequestSecurityError, "scope") as error:
            store.require_active(mismatched, now=self.NOW)
        self.assertEqual(error.exception.code, "SESSION_SCOPE_MISMATCH")

    def test_duplicate_and_missing_sessions_are_rejected(self) -> None:
        grant = self._grant()
        store = SessionLifecycleStore()
        store.register(grant, now=self.NOW)
        with self.assertRaisesRegex(RequestSecurityError, "already registered"):
            store.register(grant, now=self.NOW)
        with self.assertRaisesRegex(RequestSecurityError, "not present"):
            store.require_active(replace(grant, session_id="missing"), now=self.NOW)


if __name__ == "__main__":
    unittest.main()
