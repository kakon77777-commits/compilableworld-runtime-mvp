"""Durable local audit sink and query index for safe MCP envelopes."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .audit import MCP_AUDIT_ENVELOPE_CONTRACT
from .contracts import MCPWorldError


AUDIT_STORE_CONTRACT = "compilableworld.mcp-audit-store/v0.1"
AUDIT_ANCHOR_CONTRACT = "compilableworld.mcp-audit-anchor/v0.1"
_FORBIDDEN_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "session_token",
    "action_args",
    "args",
    "arguments",
}


class AuditStoreError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = AUDIT_STORE_CONTRACT
        return payload


def _required(value: Any, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise AuditStoreError("INVALID_AUDIT", f"{field_name} must be non-empty")
    return normalized


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


def _hash_record(
    audit_id: str,
    occurred_at: int,
    created_at: int,
    previous_hash: str | None,
    envelope: Mapping[str, Any],
) -> str:
    payload = {
        "audit_id": audit_id,
        "occurred_at": int(occurred_at),
        "created_at": int(created_at),
        "previous_hash": previous_hash,
        "envelope": dict(envelope),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuditRecord:
    audit_id: str
    occurred_at: int
    created_at: int
    request_id: str
    operation: str
    outcome: str
    session_id: str | None
    world_id: str | None
    runtime_instance_id: str | None
    envelope: dict[str, Any]
    previous_hash: str | None
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": AUDIT_STORE_CONTRACT,
            "audit_id": self.audit_id,
            "occurred_at": self.occurred_at,
            "created_at": self.created_at,
            "request_id": self.request_id,
            "operation": self.operation,
            "outcome": self.outcome,
            "session_id": self.session_id,
            "world_id": self.world_id,
            "runtime_instance_id": self.runtime_instance_id,
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
            "envelope": deepcopy(self.envelope),
        }


@dataclass(frozen=True, slots=True)
class AuditAnchor:
    anchor_id: str
    created_at: int
    first_audit_id: str
    last_audit_id: str
    record_count: int
    chain_head: str
    anchor_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": AUDIT_ANCHOR_CONTRACT,
            "anchor_id": self.anchor_id,
            "created_at": self.created_at,
            "first_audit_id": self.first_audit_id,
            "last_audit_id": self.last_audit_id,
            "record_count": self.record_count,
            "chain_head": self.chain_head,
            "anchor_hash": self.anchor_hash,
        }


class AuditStore:
    """Process-local or SQLite-backed append/query sink for safe envelopes."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: list[AuditRecord] = []
        self._local_anchors: dict[str, AuditAnchor] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def append(self, envelope: Mapping[str, Any], *, now: int | None = None) -> AuditRecord:
        safe = self._normalize_envelope(envelope)
        current = _now(now)
        audit_id = f"audit_{uuid4().hex}"
        occurred_at = int(safe["occurred_at"])
        request_id = safe["request_id"]
        operation = safe["operation"]
        outcome = safe["outcome"]
        session_id = _optional(safe.get("session_id"))
        world_id = _optional(safe.get("world_id"))
        runtime_instance_id = _optional(safe.get("runtime_instance_id"))
        if self.db_path is None:
            with self._lock:
                self._verify_records(self._local)
                previous_hash = None if not self._local else self._local[-1].record_hash
                record = AuditRecord(
                    audit_id=audit_id,
                    occurred_at=occurred_at,
                    created_at=current,
                    request_id=request_id,
                    operation=operation,
                    outcome=outcome,
                    session_id=session_id,
                    world_id=world_id,
                    runtime_instance_id=runtime_instance_id,
                    envelope=safe,
                    previous_hash=previous_hash,
                    record_hash=_hash_record(audit_id, occurred_at, current, previous_hash, safe),
                )
                self._local.append(record)
            return record
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    "SELECT record_hash FROM mcp_audit ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                previous_hash = None if previous is None else previous["record_hash"]
                self._verify_connection(connection)
                record = AuditRecord(
                    audit_id=audit_id,
                    occurred_at=occurred_at,
                    created_at=current,
                    request_id=request_id,
                    operation=operation,
                    outcome=outcome,
                    session_id=session_id,
                    world_id=world_id,
                    runtime_instance_id=runtime_instance_id,
                    envelope=safe,
                    previous_hash=previous_hash,
                    record_hash=_hash_record(audit_id, occurred_at, current, previous_hash, safe),
                )
                connection.execute(
                    "INSERT INTO mcp_audit (audit_id, occurred_at, created_at, request_id, operation, outcome, session_id, world_id, runtime_instance_id, previous_hash, record_hash, envelope_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.audit_id,
                        record.occurred_at,
                        record.created_at,
                        record.request_id,
                        record.operation,
                        record.outcome,
                        record.session_id,
                        record.world_id,
                        record.runtime_instance_id,
                        record.previous_hash,
                        record.record_hash,
                        json.dumps(record.envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    ),
                )
        except sqlite3.Error as exc:
            raise AuditStoreError("AUDIT_SINK_UNAVAILABLE", "audit sink write failed") from exc
        return record

    def query(
        self,
        *,
        request_id: str | None = None,
        session_id: str | None = None,
        world_id: str | None = None,
        operation: str | None = None,
        outcome: str | None = None,
        after: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        size = int(limit)
        if size <= 0 or size > 1000:
            raise AuditStoreError("INVALID_AUDIT", "audit query limit must be between 1 and 1000")
        filters = {
            "request_id": _optional(request_id),
            "session_id": _optional(session_id),
            "world_id": _optional(world_id),
            "operation": _optional(operation),
            "outcome": _optional(outcome),
        }
        if self.db_path is None:
            with self._lock:
                records = [record for record in self._local if self._matches(record, filters, after)]
                records = sorted(records, key=lambda item: (item.occurred_at, item.audit_id), reverse=True)[:size]
        else:
            clauses: list[str] = []
            values: list[Any] = []
            for field, value in filters.items():
                if value is not None:
                    clauses.append(f"{field} = ?")
                    values.append(value)
            if after is not None:
                clauses.append("occurred_at > ?")
                values.append(int(after))
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            with self._connection() as connection:
                rows = connection.execute(
                    f"SELECT * FROM mcp_audit{where} ORDER BY occurred_at DESC, audit_id DESC LIMIT ?",
                    (*values, size),
                ).fetchall()
                records = [self._row_to_record(row) for row in rows]
        return [record.to_dict() for record in records]

    def verify_chain(self) -> int:
        """Verify the local hash chain and return the number of records."""
        if self.db_path is None:
            with self._lock:
                return self._verify_records(self._local)
        with self._connection() as connection:
            return self._verify_connection(connection)

    def create_anchor(self, *, now: int | None = None) -> AuditAnchor:
        """Create a checkpoint for the current append-only chain head."""
        current = _now(now)
        anchor_id = f"anchor_{uuid4().hex}"
        if self.db_path is None:
            with self._lock:
                count = self._verify_records(self._local)
                records = list(self._local)
                anchor = self._build_anchor(anchor_id, current, records)
                self._local_anchors[anchor_id] = anchor
                return anchor
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._verify_connection(connection)
                records = [
                    self._row_to_record(row)
                    for row in connection.execute("SELECT * FROM mcp_audit ORDER BY rowid").fetchall()
                ]
                anchor = self._build_anchor(anchor_id, current, records)
                connection.execute(
                    "INSERT INTO mcp_audit_anchor (anchor_id, created_at, first_audit_id, last_audit_id, record_count, chain_head, anchor_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        anchor.anchor_id,
                        anchor.created_at,
                        anchor.first_audit_id,
                        anchor.last_audit_id,
                        anchor.record_count,
                        anchor.chain_head,
                        anchor.anchor_hash,
                    ),
                )
                return anchor
        except sqlite3.Error as exc:
            raise AuditStoreError("AUDIT_ANCHOR_UNAVAILABLE", "audit anchor write failed") from exc

    def verify_anchor(self, anchor_id: str) -> AuditAnchor:
        normalized = _required(anchor_id, "anchor_id")
        if self.db_path is None:
            with self._lock:
                try:
                    anchor = self._local_anchors[normalized]
                except KeyError as exc:
                    raise AuditStoreError("AUDIT_ANCHOR_MISSING", "audit anchor does not exist") from exc
                self._verify_anchor_records(anchor, self._local)
                return anchor
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM mcp_audit_anchor WHERE anchor_id = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                raise AuditStoreError("AUDIT_ANCHOR_MISSING", "audit anchor does not exist")
            anchor = AuditAnchor(
                anchor_id=row["anchor_id"],
                created_at=int(row["created_at"]),
                first_audit_id=row["first_audit_id"],
                last_audit_id=row["last_audit_id"],
                record_count=int(row["record_count"]),
                chain_head=row["chain_head"],
                anchor_hash=row["anchor_hash"],
            )
            records = [
                self._row_to_record(row)
                for row in connection.execute("SELECT * FROM mcp_audit ORDER BY rowid LIMIT ?", (anchor.record_count,)).fetchall()
            ]
            self._verify_anchor_records(anchor, records)
            return anchor

    @staticmethod
    def _build_anchor(anchor_id: str, created_at: int, records: list[AuditRecord]) -> AuditAnchor:
        if not records:
            raise AuditStoreError("AUDIT_ANCHOR_EMPTY", "cannot anchor an empty audit chain")
        payload = {
            "anchor_id": anchor_id,
            "created_at": int(created_at),
            "first_audit_id": records[0].audit_id,
            "last_audit_id": records[-1].audit_id,
            "record_count": len(records),
            "chain_head": records[-1].record_hash,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return AuditAnchor(**payload, anchor_hash=hashlib.sha256(encoded.encode("utf-8")).hexdigest())

    @classmethod
    def _verify_anchor_records(cls, anchor: AuditAnchor, records: list[AuditRecord]) -> None:
        cls._verify_records(records)
        if not records or len(records) != anchor.record_count:
            raise AuditStoreError("AUDIT_ANCHOR_INVALID", f"audit anchor count is invalid: {anchor.anchor_id}")
        if records[0].audit_id != anchor.first_audit_id or records[-1].audit_id != anchor.last_audit_id:
            raise AuditStoreError("AUDIT_ANCHOR_INVALID", f"audit anchor range is invalid: {anchor.anchor_id}")
        if records[-1].record_hash != anchor.chain_head:
            raise AuditStoreError("AUDIT_ANCHOR_INVALID", f"audit anchor chain head is invalid: {anchor.anchor_id}")
        payload = {
            "anchor_id": anchor.anchor_id,
            "created_at": anchor.created_at,
            "first_audit_id": anchor.first_audit_id,
            "last_audit_id": anchor.last_audit_id,
            "record_count": anchor.record_count,
            "chain_head": anchor.chain_head,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if anchor.anchor_hash != expected:
            raise AuditStoreError("AUDIT_ANCHOR_INVALID", f"audit anchor hash is invalid: {anchor.anchor_id}")

    @staticmethod
    def _verify_records(records: list[AuditRecord]) -> int:
        previous_hash: str | None = None
        for record in records:
            expected = _hash_record(
                record.audit_id,
                record.occurred_at,
                record.created_at,
                previous_hash,
                record.envelope,
            )
            if record.previous_hash != previous_hash or record.record_hash != expected:
                raise AuditStoreError("AUDIT_CHAIN_INVALID", f"audit hash chain is invalid at {record.audit_id}")
            previous_hash = record.record_hash
        return len(records)

    @classmethod
    def _verify_connection(cls, connection: sqlite3.Connection) -> int:
        rows = connection.execute(
            "SELECT * FROM mcp_audit ORDER BY rowid"
        ).fetchall()
        return cls._verify_records([cls._row_to_record(row) for row in rows])

    @staticmethod
    def _normalize_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(envelope, Mapping):
            raise AuditStoreError("INVALID_AUDIT", "audit envelope must be an object")
        if envelope.get("format") != MCP_AUDIT_ENVELOPE_CONTRACT:
            raise AuditStoreError("INVALID_AUDIT", "audit envelope format is invalid")
        try:
            normalized = json.loads(json.dumps(dict(envelope), ensure_ascii=False, sort_keys=True))
        except (TypeError, ValueError) as exc:
            raise AuditStoreError("INVALID_AUDIT", "audit envelope must be JSON-compatible") from exc
        AuditStore._assert_safe(normalized)
        for field in ("request_id", "operation", "outcome"):
            _required(normalized.get(field), field)
        try:
            normalized["occurred_at"] = int(normalized["occurred_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditStoreError("INVALID_AUDIT", "audit occurred_at must be an integer") from exc
        return normalized

    @classmethod
    def _assert_safe(cls, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if str(key).strip().lower() in _FORBIDDEN_KEYS:
                    raise AuditStoreError("AUDIT_SENSITIVE_FIELD", f"audit envelope contains forbidden field: {key}")
                cls._assert_safe(nested)
        elif isinstance(value, list):
            for nested in value:
                cls._assert_safe(nested)

    @staticmethod
    def _matches(record: AuditRecord, filters: Mapping[str, str | None], after: int | None) -> bool:
        if after is not None and record.occurred_at <= int(after):
            return False
        for field, value in filters.items():
            if value is not None and getattr(record, field) != value:
                return False
        return True

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AuditRecord:
        return AuditRecord(
            audit_id=row["audit_id"],
            occurred_at=int(row["occurred_at"]),
            created_at=int(row["created_at"]),
            request_id=row["request_id"],
            operation=row["operation"],
            outcome=row["outcome"],
            session_id=row["session_id"],
            world_id=row["world_id"],
            runtime_instance_id=row["runtime_instance_id"],
            envelope=json.loads(row["envelope_json"]),
            previous_hash=row["previous_hash"],
            record_hash=row["record_hash"],
        )

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for audit store")
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
                "CREATE TABLE IF NOT EXISTS mcp_audit ("
                "audit_id TEXT PRIMARY KEY, occurred_at INTEGER NOT NULL, created_at INTEGER NOT NULL, "
                "request_id TEXT NOT NULL, operation TEXT NOT NULL, outcome TEXT NOT NULL, "
                "session_id TEXT, world_id TEXT, runtime_instance_id TEXT, previous_hash TEXT, "
                "record_hash TEXT NOT NULL, envelope_json TEXT NOT NULL)"
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(mcp_audit)").fetchall()}
            if "previous_hash" not in columns:
                connection.execute("ALTER TABLE mcp_audit ADD COLUMN previous_hash TEXT")
            if "record_hash" not in columns:
                connection.execute("ALTER TABLE mcp_audit ADD COLUMN record_hash TEXT")
            self._migrate_or_verify_chain(connection)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mcp_audit_anchor ("
                "anchor_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, first_audit_id TEXT NOT NULL, "
                "last_audit_id TEXT NOT NULL, record_count INTEGER NOT NULL, chain_head TEXT NOT NULL, anchor_hash TEXT NOT NULL)"
            )
            for name, columns in {
                "occurred_at": "(occurred_at, audit_id)",
                "session": "(session_id, occurred_at, audit_id)",
                "world": "(world_id, occurred_at, audit_id)",
                "operation": "(operation, occurred_at, audit_id)",
            }.items():
                connection.execute(f"CREATE INDEX IF NOT EXISTS idx_mcp_audit_{name} ON mcp_audit {columns}")

    @classmethod
    def _migrate_or_verify_chain(cls, connection: sqlite3.Connection) -> None:
        rows = connection.execute("SELECT * FROM mcp_audit ORDER BY rowid").fetchall()
        if not rows:
            return
        has_hashes = [row["record_hash"] is not None for row in rows]
        if any(has_hashes) and not all(has_hashes):
            raise AuditStoreError("AUDIT_CHAIN_INVALID", "audit hash chain has incomplete legacy hashes")
        if all(has_hashes):
            cls._verify_connection(connection)
            return
        previous_hash: str | None = None
        for row in rows:
            record = cls._row_to_record(row)
            record_hash = _hash_record(
                record.audit_id,
                record.occurred_at,
                record.created_at,
                previous_hash,
                record.envelope,
            )
            connection.execute(
                "UPDATE mcp_audit SET previous_hash = ?, record_hash = ? WHERE audit_id = ?",
                (previous_hash, record_hash, record.audit_id),
            )
            previous_hash = record_hash


__all__ = [
    "AUDIT_ANCHOR_CONTRACT",
    "AUDIT_STORE_CONTRACT",
    "AuditAnchor",
    "AuditRecord",
    "AuditStore",
    "AuditStoreError",
]
