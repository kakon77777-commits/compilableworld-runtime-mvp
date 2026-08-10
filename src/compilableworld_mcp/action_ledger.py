"""Session-scoped idempotency reservations for MCP actions."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .contracts import MCPWorldError


ACTION_RESERVATION_CONTRACT = "compilableworld.mcp-action-reservation/v0.1"
RESERVATION_STATUS_RESERVED = "reserved"
RESERVATION_STATUS_COMPLETED = "completed"
RESERVATION_STATUS_FAILED = "failed"


class ActionReservationError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = ACTION_RESERVATION_CONTRACT
        return payload


def _required(value: str, field_name: str, *, max_length: int | None = None) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ActionReservationError("INVALID_ACTION_RESERVATION", f"{field_name} must be non-empty")
    if max_length is not None and len(normalized) > max_length:
        raise ActionReservationError("INVALID_ACTION_RESERVATION", f"{field_name} is too long")
    return normalized


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


@dataclass(frozen=True, slots=True)
class ActionReservationRecord:
    session_id: str
    idempotency_key: str
    fingerprint: str
    action_id: str
    status: str
    result: dict[str, Any] | None
    created_at: int
    updated_at: int

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "format": ACTION_RESERVATION_CONTRACT,
            "session_id": self.session_id,
            "idempotency_key": self.idempotency_key,
            "fingerprint": self.fingerprint,
            "action_id": self.action_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ActionReservationStore:
    """Process-local or SQLite-backed idempotency ledger."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[tuple[str, str], ActionReservationRecord] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def reserve(
        self,
        session_id: str,
        idempotency_key: str,
        fingerprint: str,
        action_id: str,
        *,
        now: int | None = None,
    ) -> ActionReservationRecord:
        session = _required(session_id, "session_id")
        key = _required(idempotency_key, "idempotency_key", max_length=160)
        digest = _required(fingerprint, "fingerprint", max_length=128)
        action = _required(action_id, "action_id")
        current = _now(now)
        candidate = ActionReservationRecord(
            session, key, digest, action, RESERVATION_STATUS_RESERVED, None, current, current
        )
        if self.db_path is None:
            with self._lock:
                existing = self._local.get((session, key))
                if existing is None:
                    self._local[(session, key)] = candidate
                    return candidate
                return self._resolve_existing(existing, digest)

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._fetch(connection, session, key)
            if existing is None:
                connection.execute(
                    "INSERT INTO mcp_action_reservations (session_id, idempotency_key, fingerprint, action_id, status, result_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (session, key, digest, action, RESERVATION_STATUS_RESERVED, None, current, current),
                )
                return candidate
            return self._resolve_existing(existing, digest)

    def complete(
        self,
        session_id: str,
        idempotency_key: str,
        action_id: str,
        result: Mapping[str, Any],
        *,
        succeeded: bool,
        now: int | None = None,
    ) -> ActionReservationRecord:
        session = _required(session_id, "session_id")
        key = _required(idempotency_key, "idempotency_key", max_length=160)
        action = _required(action_id, "action_id")
        if not isinstance(result, Mapping):
            raise ActionReservationError("INVALID_ACTION_RESERVATION", "action result must be an object")
        encoded = json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        status = RESERVATION_STATUS_COMPLETED if succeeded else RESERVATION_STATUS_FAILED
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                record = self._local.get((session, key))
                self._assert_completable(record, action)
                updated = replace(record, status=status, result=json.loads(encoded), updated_at=current)
                self._local[(session, key)] = updated
                return updated

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = self._fetch(connection, session, key)
            self._assert_completable(record, action)
            connection.execute(
                "UPDATE mcp_action_reservations SET status = ?, result_json = ?, updated_at = ? WHERE session_id = ? AND idempotency_key = ? AND status = ?",
                (status, encoded, current, session, key, RESERVATION_STATUS_RESERVED),
            )
            updated = replace(record, status=status, result=json.loads(encoded), updated_at=current)
            return updated

    def get(self, session_id: str, idempotency_key: str) -> ActionReservationRecord | None:
        session = _required(session_id, "session_id")
        key = _required(idempotency_key, "idempotency_key", max_length=160)
        if self.db_path is None:
            with self._lock:
                return self._local.get((session, key))
        with self._connection() as connection:
            return self._fetch(connection, session, key)

    def _resolve_existing(self, existing: ActionReservationRecord, fingerprint: str) -> ActionReservationRecord:
        if existing.fingerprint != fingerprint:
            raise ActionReservationError(
                "IDEMPOTENCY_CONFLICT",
                "idempotency key was already used for a different action",
            )
        if existing.status == RESERVATION_STATUS_RESERVED:
            raise ActionReservationError(
                "ACTION_IN_FLIGHT",
                "an action with this idempotency key is still in flight",
                retryable=True,
            )
        return existing

    def _assert_completable(self, record: ActionReservationRecord | None, action_id: str) -> None:
        if record is None:
            raise ActionReservationError("ACTION_RESERVATION_MISSING", "action reservation does not exist")
        if record.action_id != action_id:
            raise ActionReservationError("ACTION_RESERVATION_MISMATCH", "action id does not match reservation")
        if record.status != RESERVATION_STATUS_RESERVED:
            raise ActionReservationError("ACTION_RESERVATION_FINAL", "action reservation is already finalized")

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ActionReservationRecord:
        return ActionReservationRecord(
            session_id=row["session_id"],
            idempotency_key=row["idempotency_key"],
            fingerprint=row["fingerprint"],
            action_id=row["action_id"],
            status=row["status"],
            result=None if row["result_json"] is None else json.loads(row["result_json"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )

    def _fetch(self, connection: sqlite3.Connection, session_id: str, key: str) -> ActionReservationRecord | None:
        row = connection.execute(
            "SELECT * FROM mcp_action_reservations WHERE session_id = ? AND idempotency_key = ?",
            (session_id, key),
        ).fetchone()
        return None if row is None else self._row_to_record(row)

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for action ledger")
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
                "CREATE TABLE IF NOT EXISTS mcp_action_reservations ("
                "session_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, fingerprint TEXT NOT NULL, action_id TEXT NOT NULL, "
                "status TEXT NOT NULL, result_json TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, "
                "PRIMARY KEY (session_id, idempotency_key))"
            )


__all__ = [
    "ACTION_RESERVATION_CONTRACT",
    "ActionReservationError",
    "ActionReservationRecord",
    "ActionReservationStore",
    "RESERVATION_STATUS_COMPLETED",
    "RESERVATION_STATUS_FAILED",
    "RESERVATION_STATUS_RESERVED",
]
