from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from compilableworld_mcp.request_security import RequestSecurityError
from compilableworld_mcp.revocation import (
    PrincipalJTIRevocationStore,
    RevocationCheckingPrincipalResolver,
)
from compilableworld_mcp.security import HMACKeyRing, PrincipalTokenCodec


class RevocationTests(unittest.TestCase):
    NOW = 1_700_000_000

    def setUp(self) -> None:
        self.codec = PrincipalTokenCodec(
            HMACKeyRing({"k1": b"a" * 32}, active_kid="k1"),
            issuer="compilableworld-host",
            audience="compilableworld-mcp",
        )
        self.token = self.codec.issue(
            user_id="user-1",
            client_id="studio",
            roles=["player"],
            now=self.NOW,
            ttl_seconds=300,
        )
        self.principal = self.codec.verify(self.token, now=self.NOW + 1)

    def test_process_local_revoke_and_expiry_prune(self) -> None:
        store = PrincipalJTIRevocationStore()
        self.assertFalse(store.is_revoked(self.principal.token_id, now=self.NOW + 1))
        store.revoke(self.principal.token_id, expires_at=self.principal.expires_at, now=self.NOW + 1)
        self.assertTrue(store.is_revoked(self.principal.token_id, now=self.NOW + 2))
        self.assertFalse(store.is_revoked(self.principal.token_id, now=self.principal.expires_at))

    def test_sqlite_store_is_shared_and_does_not_store_raw_jti(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "revocation.sqlite3"
            first = PrincipalJTIRevocationStore(path)
            second = PrincipalJTIRevocationStore(path)
            first.revoke(self.principal.token_id, expires_at=self.principal.expires_at, now=self.NOW + 1)
            self.assertTrue(second.is_revoked(self.principal.token_id, now=self.NOW + 2))
            connection = sqlite3.connect(path)
            try:
                row = connection.execute("SELECT jti_hash FROM principal_jti_revocations").fetchone()
            finally:
                connection.close()
            self.assertIsNotNone(row)
            self.assertNotEqual(row[0], self.principal.token_id)
            self.assertEqual(len(row[0]), 64)

    def test_resolver_rejects_revoked_principal_after_signature_check(self) -> None:
        store = PrincipalJTIRevocationStore()
        resolver = RevocationCheckingPrincipalResolver(self.codec, store)
        store.revoke(self.principal.token_id, expires_at=self.principal.expires_at, now=self.NOW + 1)
        with self.assertRaisesRegex(RequestSecurityError, "revoked"):
            resolver.resolve(f"Bearer {self.token}", expected_client_id="studio", now=self.NOW + 2)

    def test_invalid_revocation_is_rejected(self) -> None:
        store = PrincipalJTIRevocationStore()
        with self.assertRaisesRegex(RequestSecurityError, "non-empty"):
            store.is_revoked("", now=self.NOW)
        with self.assertRaisesRegex(RequestSecurityError, "in the future"):
            store.revoke(self.principal.token_id, expires_at=self.NOW, now=self.NOW)


if __name__ == "__main__":
    unittest.main()
