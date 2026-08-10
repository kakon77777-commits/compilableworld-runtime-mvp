"""Durable recovery journal for the Runtime-to-outbox action boundary."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .contracts import MCPWorldError
from .outbox import OutboxRecord, TransactionalOutbox


ACTION_COMMIT_JOURNAL_CONTRACT = "compilableworld.mcp-action-commit-journal/v0.1"
JOURNAL_STATUS_PREPARED = "prepared"
JOURNAL_STATUS_RUNTIME_COMMITTED = "runtime_committed"
JOURNAL_STATUS_OUTBOX_ENQUEUED = "outbox_enqueued"
JOURNAL_STATUS_FAILED = "failed"


class ActionCommitJournalError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = ACTION_COMMIT_JOURNAL_CONTRACT
        return payload


def _required(value: str, field_name: str, *, max_length: int | None = None) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ActionCommitJournalError("INVALID_ACTION_JOURNAL", f"{field_name} must be non-empty")
    if max_length is not None and len(normalized) > max_length:
        raise ActionCommitJournalError("INVALID_ACTION_JOURNAL", f"{field_name} is too long")
    return normalized


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


@dataclass(frozen=True, slots=True)
class ActionCommitJournalRecord:
    commit_id: str
    session_id: str
    idempotency_key: str
    action_id: str
    runtime_instance_id: str
    status: str
    result: dict[str, Any] | None
    outbox_id: str | None
    created_at: int
    updated_at: int
    error_code: str | None = None

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "format": ACTION_COMMIT_JOURNAL_CONTRACT,
            "commit_id": self.commit_id,
            "session_id": self.session_id,
            "idempotency_key": self.idempotency_key,
            "action_id": self.action_id,
            "runtime_instance_id": self.runtime_instance_id,
            "status": self.status,
            "outbox_id_present": self.outbox_id is not None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error_code": self.error_code,
        }


class ActionCommitJournalStore:
    """Process-local or SQLite recovery journal for action delivery."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[tuple[str, str], ActionCommitJournalRecord] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def prepare(
        self,
        session_id: str,
        idempotency_key: str,
        action_id: str,
        runtime_instance_id: str,
        *,
        now: int | None = None,
    ) -> ActionCommitJournalRecord:
        session = _required(session_id, "session_id")
        key = _required(idempotency_key, "idempotency_key", max_length=160)
        action = _required(action_id, "action_id")
        runtime = _required(runtime_instance_id, "runtime_instance_id")
        current = _now(now)
        candidate = ActionCommitJournalRecord(
            commit_id=f"commit_{uuid4().hex}",
            session_id=session,
            idempotency_key=key,
            action_id=action,
            runtime_instance_id=runtime,
            status=JOURNAL_STATUS_PREPARED,
            result=None,
            outbox_id=None,
            created_at=current,
            updated_at=current,
        )
        if self.db_path is None:
            with self._lock:
                existing = self._local.get((session, key))
                if existing is not None:
                    self._assert_identity(existing, action, runtime)
                    return existing
                self._local[(session, key)] = candidate
                return candidate
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._fetch(connection, session, key)
            if existing is not None:
                self._assert_identity(existing, action, runtime)
                return existing
            connection.execute(
                "INSERT INTO mcp_action_commit_journal (commit_id, session_id, idempotency_key, action_id, runtime_instance_id, status, result_json, outbox_id, created_at, updated_at, error_code) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self._values(candidate),
            )
            return candidate

    def record_runtime_committed(
        self,
        session_id: str,
        idempotency_key: str,
        action_id: str,
        result: Mapping[str, Any],
        *,
        now: int | None = None,
    ) -> ActionCommitJournalRecord:
        if not isinstance(result, Mapping):
            raise ActionCommitJournalError("INVALID_ACTION_JOURNAL", "runtime result must be an object")
        session, key, action = self._identity(session_id, idempotency_key, action_id)
        encoded = json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                record = self._local.get((session, key))
                self._assert_transition(record, action, JOURNAL_STATUS_RUNTIME_COMMITTED)
                updated = replace(record, status=JOURNAL_STATUS_RUNTIME_COMMITTED, result=json.loads(encoded), updated_at=current)
                self._local[(session, key)] = updated
                return updated
        with self._connection() as connection:
            record = self._fetch(connection, session, key)
            self._assert_transition(record, action, JOURNAL_STATUS_RUNTIME_COMMITTED)
            connection.execute(
                "UPDATE mcp_action_commit_journal SET status = ?, result_json = ?, updated_at = ? WHERE session_id = ? AND idempotency_key = ?",
                (JOURNAL_STATUS_RUNTIME_COMMITTED, encoded, current, session, key),
            )
            return self._fetch(connection, session, key)  # type: ignore[return-value]

    def record_runtime_and_enqueue_outbox(
        self,
        outbox: TransactionalOutbox,
        session_id: str,
        idempotency_key: str,
        action_id: str,
        runtime_instance_id: str,
        result: Mapping[str, Any],
        *,
        event_type: str = "mcp.action.receipt",
        aggregate_id: str | None = None,
        dedupe_key: str | None = None,
        now: int | None = None,
    ) -> tuple[ActionCommitJournalRecord, OutboxRecord]:
        """Atomically persist a runtime result and its outbox handoff.

        This boundary is available only when the journal and outbox point to
        the same SQLite database.  The Kernel's in-memory state and EventLog
        commit must already have completed before this method is called.
        """
        if not isinstance(outbox, TransactionalOutbox):
            raise ActionCommitJournalError("ATOMIC_HANDOFF_UNAVAILABLE", "atomic handoff requires a TransactionalOutbox")
        if self.db_path is None or outbox.db_path != self.db_path:
            raise ActionCommitJournalError(
                "ATOMIC_HANDOFF_UNAVAILABLE",
                "atomic handoff requires journal and outbox to share one SQLite database",
            )
        if not isinstance(result, Mapping):
            raise ActionCommitJournalError("INVALID_ACTION_JOURNAL", "runtime result must be an object")
        session, key, action = self._identity(session_id, idempotency_key, action_id)
        runtime = _required(runtime_instance_id, "runtime_instance_id")
        encoded_result = json.dumps(dict(result), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        aggregate = session if aggregate_id is None else _required(aggregate_id, "aggregate_id")
        dedupe = f"action:{action}" if dedupe_key is None else _required(dedupe_key, "dedupe_key")
        current = _now(now)

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            record = self._fetch(connection, session, key)
            if record is None:
                raise ActionCommitJournalError("ACTION_JOURNAL_MISSING", "action commit journal record does not exist")
            self._assert_identity(record, action, runtime)
            if record.status == JOURNAL_STATUS_OUTBOX_ENQUEUED:
                if record.outbox_id is None:
                    raise ActionCommitJournalError("ATOMIC_HANDOFF_INCONSISTENT", "journal has no outbox id")
                queued = outbox._fetch_by_id(connection, record.outbox_id)
                if queued is None:
                    raise ActionCommitJournalError("ATOMIC_HANDOFF_INCONSISTENT", "journal outbox row is missing")
                return record, queued
            self._assert_transition(record, action, JOURNAL_STATUS_RUNTIME_COMMITTED)
            connection.execute(
                "UPDATE mcp_action_commit_journal SET status = ?, result_json = ?, updated_at = ? WHERE session_id = ? AND idempotency_key = ?",
                (JOURNAL_STATUS_RUNTIME_COMMITTED, encoded_result, current, session, key),
            )
            queued = outbox.enqueue_in_connection(
                connection,
                event_type,
                aggregate,
                json.loads(encoded_result),
                now=current,
                dedupe_key=dedupe,
            )
            connection.execute(
                "UPDATE mcp_action_commit_journal SET status = ?, outbox_id = ?, updated_at = ? WHERE session_id = ? AND idempotency_key = ?",
                (JOURNAL_STATUS_OUTBOX_ENQUEUED, queued.outbox_id, current, session, key),
            )
            updated = self._fetch(connection, session, key)
            if updated is None:  # pragma: no cover - guarded by the update above
                raise ActionCommitJournalError("ATOMIC_HANDOFF_INCONSISTENT", "journal update disappeared")
            return updated, queued

    def mark_outbox_enqueued(
        self,
        session_id: str,
        idempotency_key: str,
        action_id: str,
        outbox_id: str,
        *,
        now: int | None = None,
    ) -> ActionCommitJournalRecord:
        session, key, action = self._identity(session_id, idempotency_key, action_id)
        outbox = _required(outbox_id, "outbox_id")
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                record = self._local.get((session, key))
                self._assert_transition(record, action, JOURNAL_STATUS_OUTBOX_ENQUEUED)
                updated = replace(record, status=JOURNAL_STATUS_OUTBOX_ENQUEUED, outbox_id=outbox, updated_at=current)
                self._local[(session, key)] = updated
                return updated
        with self._connection() as connection:
            record = self._fetch(connection, session, key)
            self._assert_transition(record, action, JOURNAL_STATUS_OUTBOX_ENQUEUED)
            connection.execute(
                "UPDATE mcp_action_commit_journal SET status = ?, outbox_id = ?, updated_at = ? WHERE session_id = ? AND idempotency_key = ?",
                (JOURNAL_STATUS_OUTBOX_ENQUEUED, outbox, current, session, key),
            )
            return self._fetch(connection, session, key)  # type: ignore[return-value]

    def mark_failed(
        self,
        session_id: str,
        idempotency_key: str,
        action_id: str,
        error_code: str,
        *,
        now: int | None = None,
    ) -> ActionCommitJournalRecord:
        session, key, action = self._identity(session_id, idempotency_key, action_id)
        error = _required(error_code, "error_code")
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                record = self._local.get((session, key))
                self._assert_transition(record, action, JOURNAL_STATUS_FAILED)
                updated = replace(record, status=JOURNAL_STATUS_FAILED, error_code=error, updated_at=current)
                self._local[(session, key)] = updated
                return updated
        with self._connection() as connection:
            record = self._fetch(connection, session, key)
            self._assert_transition(record, action, JOURNAL_STATUS_FAILED)
            connection.execute(
                "UPDATE mcp_action_commit_journal SET status = ?, error_code = ?, updated_at = ? WHERE session_id = ? AND idempotency_key = ?",
                (JOURNAL_STATUS_FAILED, error, current, session, key),
            )
            return self._fetch(connection, session, key)  # type: ignore[return-value]

    def get(self, session_id: str, idempotency_key: str) -> ActionCommitJournalRecord | None:
        session, key = _required(session_id, "session_id"), _required(idempotency_key, "idempotency_key", max_length=160)
        if self.db_path is None:
            with self._lock:
                return self._local.get((session, key))
        with self._connection() as connection:
            return self._fetch(connection, session, key)

    def pending_delivery(self) -> list[ActionCommitJournalRecord]:
        if self.db_path is None:
            with self._lock:
                return sorted(
                    (record for record in self._local.values() if record.status == JOURNAL_STATUS_RUNTIME_COMMITTED),
                    key=lambda item: (item.created_at, item.commit_id),
                )
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM mcp_action_commit_journal WHERE status = ? ORDER BY created_at, commit_id",
                (JOURNAL_STATUS_RUNTIME_COMMITTED,),
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def recover_outbox(
        self,
        outbox: Any,
        *,
        reservation_store: Any | None = None,
        now: int | None = None,
    ) -> list[ActionCommitJournalRecord]:
        """Replay committed entries and optionally finalize reserved actions."""
        recovered: list[ActionCommitJournalRecord] = []
        for record in self.pending_delivery():
            if record.result is None:
                raise ActionCommitJournalError("ACTION_JOURNAL_RESULT_MISSING", "runtime commit has no result")
            queued = outbox.enqueue(
                "mcp.action.receipt",
                record.session_id,
                record.result,
                now=now,
                dedupe_key=f"action:{record.action_id}",
            )
            if reservation_store is not None:
                reservation = reservation_store.get(record.session_id, record.idempotency_key)
                if reservation is not None and reservation.status == "reserved":
                    succeeded = bool(
                        isinstance(record.result.get("receipt"), Mapping)
                        and record.result["receipt"].get("status") == "completed"
                    )
                    reservation_store.complete(
                        record.session_id,
                        record.idempotency_key,
                        record.action_id,
                        record.result,
                        succeeded=succeeded,
                        now=now,
                    )
            recovered.append(
                self.mark_outbox_enqueued(
                    record.session_id,
                    record.idempotency_key,
                    record.action_id,
                    queued.outbox_id,
                    now=now,
                )
            )
        return recovered

    @staticmethod
    def _identity(session_id: str, idempotency_key: str, action_id: str) -> tuple[str, str, str]:
        return (
            _required(session_id, "session_id"),
            _required(idempotency_key, "idempotency_key", max_length=160),
            _required(action_id, "action_id"),
        )

    @staticmethod
    def _assert_identity(record: ActionCommitJournalRecord, action_id: str, runtime_instance_id: str) -> None:
        if record.action_id != action_id or record.runtime_instance_id != runtime_instance_id:
            raise ActionCommitJournalError("ACTION_JOURNAL_CONFLICT", "action commit identity does not match")

    @staticmethod
    def _assert_transition(
        record: ActionCommitJournalRecord | None,
        action_id: str,
        target_status: str,
    ) -> None:
        if record is None:
            raise ActionCommitJournalError("ACTION_JOURNAL_MISSING", "action commit journal record does not exist")
        if record.action_id != action_id:
            raise ActionCommitJournalError("ACTION_JOURNAL_CONFLICT", "action id does not match journal")
        if target_status == JOURNAL_STATUS_RUNTIME_COMMITTED and record.status in {
            JOURNAL_STATUS_RUNTIME_COMMITTED,
            JOURNAL_STATUS_OUTBOX_ENQUEUED,
        }:
            return
        if target_status == JOURNAL_STATUS_OUTBOX_ENQUEUED and record.status == JOURNAL_STATUS_OUTBOX_ENQUEUED:
            return
        if target_status == JOURNAL_STATUS_FAILED and record.status == JOURNAL_STATUS_FAILED:
            return
        expected = JOURNAL_STATUS_PREPARED if target_status in {JOURNAL_STATUS_RUNTIME_COMMITTED, JOURNAL_STATUS_FAILED} else JOURNAL_STATUS_RUNTIME_COMMITTED
        if record.status != expected:
            raise ActionCommitJournalError("ACTION_JOURNAL_TRANSITION", f"journal status must be {expected}")

    @staticmethod
    def _values(record: ActionCommitJournalRecord) -> tuple[Any, ...]:
        return (
            record.commit_id,
            record.session_id,
            record.idempotency_key,
            record.action_id,
            record.runtime_instance_id,
            record.status,
            None if record.result is None else json.dumps(record.result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            record.outbox_id,
            record.created_at,
            record.updated_at,
            record.error_code,
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ActionCommitJournalRecord:
        return ActionCommitJournalRecord(
            commit_id=row["commit_id"],
            session_id=row["session_id"],
            idempotency_key=row["idempotency_key"],
            action_id=row["action_id"],
            runtime_instance_id=row["runtime_instance_id"],
            status=row["status"],
            result=None if row["result_json"] is None else json.loads(row["result_json"]),
            outbox_id=row["outbox_id"],
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            error_code=row["error_code"],
        )

    def _fetch(self, connection: sqlite3.Connection, session_id: str, key: str) -> ActionCommitJournalRecord | None:
        row = connection.execute(
            "SELECT * FROM mcp_action_commit_journal WHERE session_id = ? AND idempotency_key = ?",
            (session_id, key),
        ).fetchone()
        return None if row is None else self._row_to_record(row)

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for action journal")
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
                "CREATE TABLE IF NOT EXISTS mcp_action_commit_journal ("
                "commit_id TEXT NOT NULL UNIQUE, session_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
                "action_id TEXT NOT NULL, runtime_instance_id TEXT NOT NULL, status TEXT NOT NULL, result_json TEXT, "
                "outbox_id TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, error_code TEXT, "
                "PRIMARY KEY (session_id, idempotency_key))"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_action_commit_journal_status "
                "ON mcp_action_commit_journal (status, created_at)"
            )


__all__ = [
    "ACTION_COMMIT_JOURNAL_CONTRACT",
    "ActionCommitJournalError",
    "ActionCommitJournalRecord",
    "ActionCommitJournalStore",
    "JOURNAL_STATUS_FAILED",
    "JOURNAL_STATUS_OUTBOX_ENQUEUED",
    "JOURNAL_STATUS_PREPARED",
    "JOURNAL_STATUS_RUNTIME_COMMITTED",
]
