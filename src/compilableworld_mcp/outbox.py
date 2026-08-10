"""Claim/ack transactional-outbox primitive for MCP action receipts."""

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


OUTBOX_CONTRACT = "compilableworld.mcp-outbox/v0.1"
OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_CLAIMED = "claimed"
OUTBOX_STATUS_ACKED = "acked"


class OutboxError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = OUTBOX_CONTRACT
        return payload


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise OutboxError("INVALID_OUTBOX", f"{field_name} must be non-empty")
    return normalized


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    outbox_id: str
    event_type: str
    aggregate_id: str
    payload: dict[str, Any]
    status: str
    available_at: int
    created_at: int
    attempts: int = 0
    claimed_by: str | None = None
    dedupe_key: str | None = None

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "format": OUTBOX_CONTRACT,
            "outbox_id": self.outbox_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "status": self.status,
            "available_at": self.available_at,
            "created_at": self.created_at,
            "attempts": self.attempts,
            "claimed_by": self.claimed_by,
            "dedupe_key": self.dedupe_key,
        }


class TransactionalOutbox:
    """Durable outbox queue with explicit worker claim/ack transitions."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[str, OutboxRecord] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def enqueue(
        self,
        event_type: str,
        aggregate_id: str,
        payload: Mapping[str, Any],
        *,
        now: int | None = None,
        available_at: int | None = None,
        dedupe_key: str | None = None,
    ) -> OutboxRecord:
        event = _required(event_type, "event_type")
        aggregate = _required(aggregate_id, "aggregate_id")
        if not isinstance(payload, Mapping):
            raise OutboxError("INVALID_OUTBOX", "outbox payload must be an object")
        normalized_dedupe = None if dedupe_key is None else _required(dedupe_key, "dedupe_key")
        encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        current = _now(now)
        record = OutboxRecord(
            outbox_id=f"outbox_{uuid4().hex}",
            event_type=event,
            aggregate_id=aggregate,
            payload=json.loads(encoded),
            status=OUTBOX_STATUS_PENDING,
            available_at=current if available_at is None else int(available_at),
            created_at=current,
            dedupe_key=normalized_dedupe,
        )
        if self.db_path is None:
            with self._lock:
                if normalized_dedupe is not None:
                    for existing in self._local.values():
                        if existing.dedupe_key == normalized_dedupe:
                            return existing
                self._local[record.outbox_id] = record
            return record
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self.enqueue_in_connection(
                connection,
                event,
                aggregate,
                json.loads(encoded),
                now=current,
                available_at=record.available_at,
                dedupe_key=normalized_dedupe,
            )

    def enqueue_in_connection(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        aggregate_id: str,
        payload: Mapping[str, Any],
        *,
        now: int | None = None,
        available_at: int | None = None,
        dedupe_key: str | None = None,
    ) -> OutboxRecord:
        """Insert an outbox record without committing the supplied transaction."""
        if self.db_path is None:
            raise OutboxError("ATOMIC_OUTBOX_UNAVAILABLE", "connection-backed enqueue requires a SQLite outbox")
        event = _required(event_type, "event_type")
        aggregate = _required(aggregate_id, "aggregate_id")
        if not isinstance(payload, Mapping):
            raise OutboxError("INVALID_OUTBOX", "outbox payload must be an object")
        normalized_dedupe = None if dedupe_key is None else _required(dedupe_key, "dedupe_key")
        encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        current = _now(now)
        record = OutboxRecord(
            outbox_id=f"outbox_{uuid4().hex}",
            event_type=event,
            aggregate_id=aggregate,
            payload=json.loads(encoded),
            status=OUTBOX_STATUS_PENDING,
            available_at=current if available_at is None else int(available_at),
            created_at=current,
            dedupe_key=normalized_dedupe,
        )
        if normalized_dedupe is not None:
            existing = self._fetch_by_dedupe(connection, normalized_dedupe)
            if existing is not None:
                return existing
        connection.execute(
            "INSERT INTO mcp_outbox (outbox_id, event_type, aggregate_id, payload_json, status, available_at, created_at, attempts, claimed_by, dedupe_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.outbox_id,
                record.event_type,
                record.aggregate_id,
                encoded,
                record.status,
                record.available_at,
                record.created_at,
                record.attempts,
                record.claimed_by,
                record.dedupe_key,
            ),
        )
        return record

    def claim(self, worker_id: str, *, limit: int = 10, now: int | None = None) -> list[OutboxRecord]:
        worker = _required(worker_id, "worker_id")
        if isinstance(limit, bool) or int(limit) <= 0 or int(limit) > 100:
            raise OutboxError("INVALID_OUTBOX", "claim limit must be between 1 and 100")
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                candidates = sorted(
                    (
                        record for record in self._local.values()
                        if record.status == OUTBOX_STATUS_PENDING and record.available_at <= current
                    ),
                    key=lambda record: (record.created_at, record.outbox_id),
                )[: int(limit)]
                claimed = [replace(record, status=OUTBOX_STATUS_CLAIMED, attempts=record.attempts + 1, claimed_by=worker) for record in candidates]
                for record in claimed:
                    self._local[record.outbox_id] = record
                return claimed

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT * FROM mcp_outbox WHERE status = ? AND available_at <= ? ORDER BY created_at, outbox_id LIMIT ?",
                (OUTBOX_STATUS_PENDING, current, int(limit)),
            ).fetchall()
            claimed: list[OutboxRecord] = []
            for row in rows:
                record = self._row_to_record(row)
                updated = replace(record, status=OUTBOX_STATUS_CLAIMED, attempts=record.attempts + 1, claimed_by=worker)
                connection.execute(
                    "UPDATE mcp_outbox SET status = ?, attempts = ?, claimed_by = ? WHERE outbox_id = ? AND status = ?",
                    (updated.status, updated.attempts, worker, updated.outbox_id, OUTBOX_STATUS_PENDING),
                )
                claimed.append(updated)
            return claimed

    def ack(self, outbox_id: str, worker_id: str, *, now: int | None = None) -> OutboxRecord:
        return self._finish(outbox_id, worker_id, OUTBOX_STATUS_ACKED, now=now)

    def retry(
        self,
        outbox_id: str,
        worker_id: str,
        *,
        retry_after_seconds: int = 5,
        now: int | None = None,
    ) -> OutboxRecord:
        if int(retry_after_seconds) < 0:
            raise OutboxError("INVALID_OUTBOX", "retry delay cannot be negative")
        current = _now(now)
        record = self._get(_required(outbox_id, "outbox_id"))
        self._assert_claim(record, worker_id)
        updated = replace(record, status=OUTBOX_STATUS_PENDING, available_at=current + int(retry_after_seconds), claimed_by=None)
        self._write(updated)
        return updated

    def get(self, outbox_id: str) -> OutboxRecord | None:
        return self._get(_required(outbox_id, "outbox_id"))

    def _finish(self, outbox_id: str, worker_id: str, status: str, *, now: int | None) -> OutboxRecord:
        record = self._get(_required(outbox_id, "outbox_id"))
        self._assert_claim(record, worker_id)
        updated = replace(record, status=status, claimed_by=None)
        self._write(updated)
        return updated

    def _assert_claim(self, record: OutboxRecord | None, worker_id: str) -> None:
        if record is None:
            raise OutboxError("OUTBOX_MISSING", "outbox record does not exist")
        if record.status != OUTBOX_STATUS_CLAIMED or record.claimed_by != _required(worker_id, "worker_id"):
            raise OutboxError("OUTBOX_CLAIM_MISMATCH", "outbox record is not claimed by this worker")

    def _get(self, outbox_id: str) -> OutboxRecord | None:
        if self.db_path is None:
            with self._lock:
                return self._local.get(outbox_id)
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM mcp_outbox WHERE outbox_id = ?", (outbox_id,)).fetchone()
            return None if row is None else self._row_to_record(row)

    @staticmethod
    def _fetch_by_dedupe(connection: sqlite3.Connection, dedupe_key: str) -> OutboxRecord | None:
        row = connection.execute(
            "SELECT * FROM mcp_outbox WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        return None if row is None else TransactionalOutbox._row_to_record(row)

    @staticmethod
    def _fetch_by_id(connection: sqlite3.Connection, outbox_id: str) -> OutboxRecord | None:
        row = connection.execute(
            "SELECT * FROM mcp_outbox WHERE outbox_id = ?",
            (outbox_id,),
        ).fetchone()
        return None if row is None else TransactionalOutbox._row_to_record(row)

    def _write(self, record: OutboxRecord) -> None:
        if self.db_path is None:
            with self._lock:
                self._local[record.outbox_id] = record
            return
        encoded = json.dumps(record.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._connection() as connection:
            connection.execute(
                "UPDATE mcp_outbox SET status = ?, available_at = ?, attempts = ?, claimed_by = ?, payload_json = ? WHERE outbox_id = ?",
                (record.status, record.available_at, record.attempts, record.claimed_by, encoded, record.outbox_id),
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> OutboxRecord:
        return OutboxRecord(
            outbox_id=row["outbox_id"],
            event_type=row["event_type"],
            aggregate_id=row["aggregate_id"],
            payload=json.loads(row["payload_json"]),
            status=row["status"],
            available_at=int(row["available_at"]),
            created_at=int(row["created_at"]),
            attempts=int(row["attempts"]),
            claimed_by=row["claimed_by"],
            dedupe_key=row["dedupe_key"],
        )

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for outbox")
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
                "CREATE TABLE IF NOT EXISTS mcp_outbox ("
                "outbox_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, aggregate_id TEXT NOT NULL, payload_json TEXT NOT NULL, "
                "status TEXT NOT NULL, available_at INTEGER NOT NULL, created_at INTEGER NOT NULL, attempts INTEGER NOT NULL, claimed_by TEXT)"
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(mcp_outbox)").fetchall()}
            if "dedupe_key" not in columns:
                connection.execute("ALTER TABLE mcp_outbox ADD COLUMN dedupe_key TEXT")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_outbox_dedupe "
                "ON mcp_outbox (dedupe_key) WHERE dedupe_key IS NOT NULL"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_outbox_pending ON mcp_outbox (status, available_at, created_at)"
            )


__all__ = [
    "OUTBOX_CONTRACT",
    "OUTBOX_STATUS_ACKED",
    "OUTBOX_STATUS_CLAIMED",
    "OUTBOX_STATUS_PENDING",
    "OutboxError",
    "OutboxRecord",
    "TransactionalOutbox",
]
