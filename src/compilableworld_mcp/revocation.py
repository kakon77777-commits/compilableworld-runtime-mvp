"""Principal JTI revocation for the local M11 security slice."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .request_security import RequestSecurityError
from .security import BearerPrincipalResolver, PrincipalTokenCodec, TrustedPrincipal


def _now_seconds(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


def _jti_hash(jti: str) -> str:
    normalized = str(jti).strip()
    if not normalized:
        raise RequestSecurityError("INVALID_REVOCATION", "principal JTI must be non-empty")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class PrincipalJTIRevocationStore:
    """Process-local or SQLite-backed denylist that never stores raw JTIs."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[str, int] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def revoke(self, jti: str, *, expires_at: int, now: int | None = None) -> None:
        digest = _jti_hash(jti)
        current = _now_seconds(now)
        expiry = int(expires_at)
        if expiry <= current:
            raise RequestSecurityError("INVALID_REVOCATION", "revocation expiry must be in the future")
        if self.db_path is None:
            with self._lock:
                self._prune_local(current)
                self._local[digest] = expiry
            return
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO principal_jti_revocations (jti_hash, expires_at) VALUES (?, ?) "
                "ON CONFLICT(jti_hash) DO UPDATE SET expires_at = excluded.expires_at",
                (digest, expiry),
            )

    def is_revoked(self, jti: str, *, now: int | None = None) -> bool:
        digest = _jti_hash(jti)
        current = _now_seconds(now)
        if self.db_path is None:
            with self._lock:
                self._prune_local(current)
                return digest in self._local
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM principal_jti_revocations WHERE expires_at <= ?",
                (current,),
            )
            row = connection.execute(
                "SELECT 1 FROM principal_jti_revocations WHERE jti_hash = ? AND expires_at > ?",
                (digest, current),
            ).fetchone()
        return row is not None

    def prune(self, *, now: int | None = None) -> int:
        current = _now_seconds(now)
        if self.db_path is None:
            with self._lock:
                before = len(self._local)
                self._prune_local(current)
                return before - len(self._local)
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM principal_jti_revocations WHERE expires_at <= ?",
                (current,),
            )
            return int(cursor.rowcount)

    def _prune_local(self, now: int) -> None:
        expired = [digest for digest, expires_at in self._local.items() if expires_at <= now]
        for digest in expired:
            del self._local[digest]

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for local revocation store")
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize_db(self) -> None:
        path = Path(self.db_path or "")
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS principal_jti_revocations ("
                "jti_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_principal_jti_revocations_expiry "
                "ON principal_jti_revocations (expires_at)"
            )


class RevocationCheckingPrincipalResolver:
    """Bearer resolver that checks JTI revocation after signature validation."""

    def __init__(self, codec: PrincipalTokenCodec, store: PrincipalJTIRevocationStore) -> None:
        self._resolver = BearerPrincipalResolver(codec)
        self._store = store

    def resolve(
        self,
        authorization: str,
        *,
        expected_client_id: str | None = None,
        now: int | None = None,
    ) -> TrustedPrincipal:
        principal = self._resolver.resolve(
            authorization,
            expected_client_id=expected_client_id,
            now=now,
        )
        if self._store.is_revoked(principal.token_id, now=now):
            raise RequestSecurityError(
                "PRINCIPAL_REVOKED",
                "principal token has been revoked",
            )
        return principal


__all__ = ["PrincipalJTIRevocationStore", "RevocationCheckingPrincipalResolver"]
