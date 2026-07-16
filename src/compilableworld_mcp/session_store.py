"""Server-side Session lifecycle and rotation store for the M12 slice."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .request_security import RequestSecurityError
from .security import SessionGrant


SESSION_STATUS_ACTIVE = "active"
SESSION_STATUS_CLOSED = "closed"
SESSION_STATUS_REVOKED = "revoked"
SESSION_STATUS_EXPIRED = "expired"
SESSION_STATUS_ROTATED = "rotated"


def _hash_identifier(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise RequestSecurityError("INVALID_SESSION_STORE", "session identifiers must be non-empty")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now(value: int | None) -> int:
    import time

    return int(time.time()) if value is None else int(value)


@dataclass(frozen=True, slots=True)
class SessionLifecycleRecord:
    session_id: str
    principal_token_id_hash: str
    session_token_id_hash: str
    user_id: str
    client_id: str
    world_id: str
    runtime_instance_id: str
    timeline_id: str
    actor_id: str
    role: str
    issued_at: int
    expires_at: int
    status: str = SESSION_STATUS_ACTIVE
    revision: int = 0
    model_id: str | None = None

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "client_id": self.client_id,
            "world_id": self.world_id,
            "runtime_instance_id": self.runtime_instance_id,
            "timeline_id": self.timeline_id,
            "actor_id": self.actor_id,
            "role": self.role,
            "model_id": self.model_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "revision": self.revision,
        }


class SessionLifecycleStore:
    """Process-local or SQLite-backed store for live Session state.

    Raw Principal or Session JTIs are never persisted. SQLite stores only
    SHA-256 hashes and the server-side session scope needed for revalidation.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[str, SessionLifecycleRecord] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def register(
        self,
        grant: SessionGrant,
        *,
        model_id: str | None = None,
        now: int | None = None,
    ) -> SessionLifecycleRecord:
        current = _now(now)
        if grant.expires_at <= current or grant.expires_at <= grant.issued_at:
            raise RequestSecurityError("SESSION_EXPIRED", "cannot register an expired session")
        record = self._record_from_grant(grant, model_id=model_id)
        if self.db_path is None:
            with self._lock:
                if record.session_id in self._local:
                    raise RequestSecurityError("SESSION_STORE_CONFLICT", "session id is already registered")
                self._local[record.session_id] = record
            return record
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO mcp_session_lifecycle ("
                    "session_id, principal_token_id_hash, session_token_id_hash, user_id, client_id, "
                    "world_id, runtime_instance_id, timeline_id, actor_id, role, model_id, issued_at, expires_at, status, revision"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._values(record),
                )
            except sqlite3.IntegrityError as exc:
                raise RequestSecurityError("SESSION_STORE_CONFLICT", "session id is already registered") from exc
        return record

    def require_active(self, grant: SessionGrant, *, now: int | None = None) -> SessionLifecycleRecord:
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                record = self._local.get(grant.session_id)
                if record is None:
                    raise RequestSecurityError("SESSION_STORE_MISSING", "session is not present in the lifecycle store")
                if record.status == SESSION_STATUS_ACTIVE and record.expires_at <= current:
                    record = self._replace_status(record, SESSION_STATUS_EXPIRED)
                    self._local[record.session_id] = record
        else:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM mcp_session_lifecycle WHERE session_id = ?",
                    (grant.session_id,),
                ).fetchone()
                if row is None:
                    raise RequestSecurityError("SESSION_STORE_MISSING", "session is not present in the lifecycle store")
                record = self._row_to_record(row)
                if record.status == SESSION_STATUS_ACTIVE and record.expires_at <= current:
                    connection.execute(
                        "UPDATE mcp_session_lifecycle SET status = ? WHERE session_id = ? AND status = ?",
                        (SESSION_STATUS_EXPIRED, grant.session_id, SESSION_STATUS_ACTIVE),
                    )
                    record = self._replace_status(record, SESSION_STATUS_EXPIRED)
        self._raise_for_status(record)
        self._assert_grant_matches(record, grant)
        return record

    def active_records(self, *, now: int | None = None) -> list[SessionLifecycleRecord]:
        """Return active session metadata for an explicit service rehydration."""
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                active: list[SessionLifecycleRecord] = []
                for session_id, record in list(self._local.items()):
                    if record.status == SESSION_STATUS_ACTIVE and record.expires_at <= current:
                        record = self._replace_status(record, SESSION_STATUS_EXPIRED)
                        self._local[session_id] = record
                    if record.status == SESSION_STATUS_ACTIVE:
                        active.append(record)
                return sorted(active, key=lambda item: item.session_id)
        with self._connection() as connection:
            connection.execute(
                "UPDATE mcp_session_lifecycle SET status = ?, revision = revision + 1 "
                "WHERE status = ? AND expires_at <= ?",
                (SESSION_STATUS_EXPIRED, SESSION_STATUS_ACTIVE, current),
            )
            rows = connection.execute(
                "SELECT * FROM mcp_session_lifecycle WHERE status = ? ORDER BY session_id",
                (SESSION_STATUS_ACTIVE,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    list_active = active_records

    def close(self, session_id: str, *, now: int | None = None) -> SessionLifecycleRecord:
        return self._transition(session_id, SESSION_STATUS_CLOSED, now=now)

    def revoke(self, session_id: str, *, now: int | None = None) -> SessionLifecycleRecord:
        return self._transition(session_id, SESSION_STATUS_REVOKED, now=now)

    def rotate(
        self,
        old_grant: SessionGrant,
        new_grant: SessionGrant,
        *,
        now: int | None = None,
    ) -> SessionLifecycleRecord:
        current = _now(now)
        if old_grant.session_id != new_grant.session_id:
            raise RequestSecurityError("SESSION_ROTATION_CONFLICT", "rotation must retain the server session id")
        if new_grant.expires_at <= current:
            raise RequestSecurityError("SESSION_EXPIRED", "cannot rotate to an expired session token")
        if self.db_path is None:
            with self._lock:
                record = self._local.get(old_grant.session_id)
                self._assert_rotatable(record, old_grant)
                updated = self._replace_token(record, new_grant)
                self._local[updated.session_id] = updated
                return updated
        old_hash = _hash_identifier(old_grant.token_id)
        new_hash = _hash_identifier(new_grant.token_id)
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE mcp_session_lifecycle SET session_token_id_hash = ?, issued_at = ?, expires_at = ?, revision = revision + 1 "
                "WHERE session_id = ? AND status = ? AND session_token_id_hash = ?",
                (
                    new_hash,
                    new_grant.issued_at,
                    new_grant.expires_at,
                    old_grant.session_id,
                    SESSION_STATUS_ACTIVE,
                    old_hash,
                ),
            )
            if cursor.rowcount != 1:
                record = self._fetch_sqlite(connection, old_grant.session_id)
                self._assert_rotatable(record, old_grant)
                raise RequestSecurityError("SESSION_ROTATION_CONFLICT", "session rotation lost a concurrent update")
            return self._fetch_sqlite(connection, new_grant.session_id)

    def prune(self, *, before: int | None = None) -> int:
        cutoff = _now(before)
        if self.db_path is None:
            with self._lock:
                expired = [
                    key for key, record in self._local.items()
                    if record.status == SESSION_STATUS_EXPIRED and record.expires_at <= cutoff
                ]
                for key in expired:
                    del self._local[key]
                return len(expired)
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM mcp_session_lifecycle WHERE status = ? AND expires_at <= ?",
                (SESSION_STATUS_EXPIRED, cutoff),
            )
            return int(cursor.rowcount)

    def _transition(self, session_id: str, status: str, *, now: int | None = None) -> SessionLifecycleRecord:
        normalized = str(session_id).strip()
        if not normalized:
            raise RequestSecurityError("INVALID_SESSION_STORE", "session_id must be non-empty")
        if self.db_path is None:
            with self._lock:
                record = self._local.get(normalized)
                if record is None:
                    raise RequestSecurityError("SESSION_STORE_MISSING", "session is not present in the lifecycle store")
                self._raise_for_status(record, allow_terminal=True)
                updated = self._replace_status(record, status)
                self._local[normalized] = updated
                return updated
        with self._connection() as connection:
            record = self._fetch_sqlite(connection, normalized)
            if record is None:
                raise RequestSecurityError("SESSION_STORE_MISSING", "session is not present in the lifecycle store")
            self._raise_for_status(record, allow_terminal=True)
            connection.execute(
                "UPDATE mcp_session_lifecycle SET status = ?, revision = revision + 1 WHERE session_id = ? AND status = ?",
                (status, normalized, SESSION_STATUS_ACTIVE),
            )
            return self._fetch_sqlite(connection, normalized)

    def _assert_rotatable(self, record: SessionLifecycleRecord | None, old_grant: SessionGrant) -> None:
        if record is None:
            raise RequestSecurityError("SESSION_STORE_MISSING", "session is not present in the lifecycle store")
        self._raise_for_status(record)
        if record.session_token_id_hash != _hash_identifier(old_grant.token_id):
            raise RequestSecurityError("SESSION_ROTATION_CONFLICT", "session token has already been rotated")

    def _assert_grant_matches(self, record: SessionLifecycleRecord, grant: SessionGrant) -> None:
        if record.session_token_id_hash != _hash_identifier(grant.token_id):
            raise RequestSecurityError("SESSION_ROTATED", "session token is no longer the active token")
        expected = {
            "principal_token_id_hash": _hash_identifier(grant.principal_token_id),
            "user_id": grant.user_id,
            "client_id": grant.client_id,
            "world_id": grant.world_id,
            "runtime_instance_id": grant.runtime_instance_id,
            "timeline_id": grant.timeline_id,
            "actor_id": grant.actor_id,
            "role": grant.role,
        }
        actual = {key: getattr(record, key) for key in expected}
        if actual != expected:
            raise RequestSecurityError("SESSION_SCOPE_MISMATCH", "session token does not match lifecycle scope")

    def _raise_for_status(self, record: SessionLifecycleRecord | None, *, allow_terminal: bool = False) -> None:
        if record is None:
            return
        if record.status == SESSION_STATUS_ACTIVE:
            return
        if allow_terminal and record.status in {SESSION_STATUS_CLOSED, SESSION_STATUS_REVOKED, SESSION_STATUS_EXPIRED}:
            return
        code = {
            SESSION_STATUS_CLOSED: "SESSION_CLOSED",
            SESSION_STATUS_REVOKED: "SESSION_REVOKED",
            SESSION_STATUS_EXPIRED: "SESSION_EXPIRED",
            SESSION_STATUS_ROTATED: "SESSION_ROTATED",
        }.get(record.status, "SESSION_INVALID")
        raise RequestSecurityError(code, f"session lifecycle status is {record.status}")

    @staticmethod
    def _record_from_grant(grant: SessionGrant, *, model_id: str | None = None) -> SessionLifecycleRecord:
        return SessionLifecycleRecord(
            session_id=grant.session_id,
            principal_token_id_hash=_hash_identifier(grant.principal_token_id),
            session_token_id_hash=_hash_identifier(grant.token_id),
            user_id=grant.user_id,
            client_id=grant.client_id,
            world_id=grant.world_id,
            runtime_instance_id=grant.runtime_instance_id,
            timeline_id=grant.timeline_id,
            actor_id=grant.actor_id,
            role=grant.role,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
            model_id=None if model_id is None else str(model_id),
        )

    @staticmethod
    def _replace_status(record: SessionLifecycleRecord, status: str) -> SessionLifecycleRecord:
        return replace(record, status=status, revision=record.revision + 1)

    @staticmethod
    def _replace_token(record: SessionLifecycleRecord, grant: SessionGrant) -> SessionLifecycleRecord:
        return replace(
            record,
            session_token_id_hash=_hash_identifier(grant.token_id),
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
            revision=record.revision + 1,
        )

    @staticmethod
    def _values(record: SessionLifecycleRecord) -> tuple[Any, ...]:
        return (
            record.session_id,
            record.principal_token_id_hash,
            record.session_token_id_hash,
            record.user_id,
            record.client_id,
            record.world_id,
            record.runtime_instance_id,
            record.timeline_id,
            record.actor_id,
            record.role,
            record.model_id,
            record.issued_at,
            record.expires_at,
            record.status,
            record.revision,
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row | tuple[Any, ...]) -> SessionLifecycleRecord:
        if not isinstance(row, sqlite3.Row):
            raise RequestSecurityError("SESSION_STORE_ERROR", "SQLite session row has an invalid shape")
        return SessionLifecycleRecord(
            session_id=row["session_id"],
            principal_token_id_hash=row["principal_token_id_hash"],
            session_token_id_hash=row["session_token_id_hash"],
            user_id=row["user_id"],
            client_id=row["client_id"],
            world_id=row["world_id"],
            runtime_instance_id=row["runtime_instance_id"],
            timeline_id=row["timeline_id"],
            actor_id=row["actor_id"],
            role=row["role"],
            model_id=row["model_id"],
            issued_at=int(row["issued_at"]),
            expires_at=int(row["expires_at"]),
            status=row["status"],
            revision=int(row["revision"]),
        )

    def _fetch_sqlite(self, connection: sqlite3.Connection, session_id: str) -> SessionLifecycleRecord | None:
        row = connection.execute(
            "SELECT * FROM mcp_session_lifecycle WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return None if row is None else self._row_to_record(row)

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for local session store")
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
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
                "CREATE TABLE IF NOT EXISTS mcp_session_lifecycle ("
                "session_id TEXT PRIMARY KEY, principal_token_id_hash TEXT NOT NULL, session_token_id_hash TEXT NOT NULL, "
                "user_id TEXT NOT NULL, client_id TEXT NOT NULL, world_id TEXT NOT NULL, runtime_instance_id TEXT NOT NULL, "
                "timeline_id TEXT NOT NULL, actor_id TEXT NOT NULL, role TEXT NOT NULL, model_id TEXT, issued_at INTEGER NOT NULL, "
                "expires_at INTEGER NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL)"
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(mcp_session_lifecycle)").fetchall()
            }
            if "model_id" not in columns:
                connection.execute("ALTER TABLE mcp_session_lifecycle ADD COLUMN model_id TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_session_lifecycle_status_expiry "
                "ON mcp_session_lifecycle (status, expires_at)"
            )


__all__ = [
    "SESSION_STATUS_ACTIVE",
    "SESSION_STATUS_CLOSED",
    "SESSION_STATUS_EXPIRED",
    "SESSION_STATUS_REVOKED",
    "SESSION_STATUS_ROTATED",
    "SessionLifecycleRecord",
    "SessionLifecycleStore",
]
