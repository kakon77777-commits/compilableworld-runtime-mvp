"""Durable projection of a committed Runtime state and event batch."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .contracts import MCPWorldError


RUNTIME_DURABILITY_CONTRACT = "compilableworld.mcp-runtime-durability/v0.1"


class RuntimeDurabilityError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = RUNTIME_DURABILITY_CONTRACT
        return payload


def _required(value: Any, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise RuntimeDurabilityError("INVALID_RUNTIME_DURABILITY", f"{field_name} must be non-empty")
    return normalized


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


def _encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class RuntimeCommitProjection:
    commit_id: str
    runtime_instance_id: str
    action_id: str
    state_hash: str
    event_ids: tuple[str, ...]
    event_count: int
    created_at: int

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "format": RUNTIME_DURABILITY_CONTRACT,
            "commit_id": self.commit_id,
            "runtime_instance_id": self.runtime_instance_id,
            "action_id": self.action_id,
            "state_hash": self.state_hash,
            "event_ids": list(self.event_ids),
            "event_count": self.event_count,
            "created_at": self.created_at,
        }


class RuntimeDurabilityStore:
    """Persist a restart-verifiable Runtime state/event projection.

    This is a durable mirror and recovery input. It does not replace the
    Kernel's in-memory authority or make the file-backed EventLog and outbox a
    single database transaction.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[tuple[str, str], tuple[RuntimeCommitProjection, str, str]] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def record_runtime_commit(
        self,
        runtime_instance_id: str,
        action_id: str,
        state: Mapping[str, Any],
        events: Iterable[Any],
        *,
        now: int | None = None,
    ) -> RuntimeCommitProjection:
        runtime = _required(runtime_instance_id, "runtime_instance_id")
        action = _required(action_id, "action_id")
        if not isinstance(state, Mapping):
            raise RuntimeDurabilityError("INVALID_RUNTIME_DURABILITY", "runtime state must be an object")
        try:
            state_payload = json.loads(_encoded(dict(state)))
            event_payload = [self._event_payload(event) for event in events]
            event_payload = json.loads(_encoded(event_payload))
        except (TypeError, ValueError) as exc:
            raise RuntimeDurabilityError("INVALID_RUNTIME_DURABILITY", "state and events must be JSON-compatible") from exc
        state_json = _encoded(state_payload)
        events_json = _encoded(event_payload)
        state_hash = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
        event_ids = tuple(_required(item["event_id"], "event_id") for item in event_payload)
        current = _now(now)
        projection = RuntimeCommitProjection(
            commit_id=f"runtime_commit_{uuid4().hex}",
            runtime_instance_id=runtime,
            action_id=action,
            state_hash=state_hash,
            event_ids=event_ids,
            event_count=len(event_payload),
            created_at=current,
        )
        if self.db_path is None:
            with self._lock:
                existing = self._local.get((runtime, action))
                if existing is not None:
                    self._assert_same(existing[0], projection)
                    return existing[0]
                self._local[(runtime, action)] = (projection, state_json, events_json)
                return projection
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._fetch(connection, runtime, action)
            if existing is not None:
                self._assert_same(existing[0], projection)
                return existing[0]
            connection.execute(
                "INSERT INTO mcp_runtime_commit_projection "
                "(commit_id, runtime_instance_id, action_id, state_json, events_json, state_hash, event_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    projection.commit_id,
                    projection.runtime_instance_id,
                    projection.action_id,
                    state_json,
                    events_json,
                    projection.state_hash,
                    projection.event_count,
                    projection.created_at,
                ),
            )
            return projection

    def get(self, runtime_instance_id: str, action_id: str) -> RuntimeCommitProjection | None:
        runtime = _required(runtime_instance_id, "runtime_instance_id")
        action = _required(action_id, "action_id")
        if self.db_path is None:
            with self._lock:
                record = self._local.get((runtime, action))
                return None if record is None else record[0]
        with self._connection() as connection:
            record = self._fetch(connection, runtime, action)
            return None if record is None else record[0]

    def load(self, runtime_instance_id: str, action_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        runtime = _required(runtime_instance_id, "runtime_instance_id")
        action = _required(action_id, "action_id")
        if self.db_path is None:
            with self._lock:
                record = self._local.get((runtime, action))
                if record is None:
                    raise RuntimeDurabilityError("RUNTIME_COMMIT_MISSING", "runtime commit projection does not exist")
                projection, state_json, events_json = record
        else:
            with self._connection() as connection:
                record = self._fetch(connection, runtime, action)
                if record is None:
                    raise RuntimeDurabilityError("RUNTIME_COMMIT_MISSING", "runtime commit projection does not exist")
                projection, state_json, events_json = record
        state = json.loads(state_json)
        events = json.loads(events_json)
        if not isinstance(state, dict) or not isinstance(events, list):  # pragma: no cover - guarded by writes
            raise RuntimeDurabilityError("RUNTIME_COMMIT_CORRUPT", "runtime commit projection payload is invalid")
        actual_hash = hashlib.sha256(_encoded(state).encode("utf-8")).hexdigest()
        if actual_hash != projection.state_hash:
            raise RuntimeDurabilityError("RUNTIME_COMMIT_TAMPERED", "runtime state projection hash does not match")
        return state, events

    def _event_payload(self, event: Any) -> dict[str, Any]:
        if hasattr(event, "to_dict") and callable(event.to_dict):
            event = event.to_dict()
        if not isinstance(event, Mapping):
            raise TypeError("event must be an object")
        payload = json.loads(_encoded(dict(event)))
        if not isinstance(payload, dict) or not payload.get("event_id"):
            raise ValueError("event_id is required")
        return payload

    @staticmethod
    def _assert_same(existing: RuntimeCommitProjection, candidate: RuntimeCommitProjection) -> None:
        if existing.state_hash != candidate.state_hash or existing.event_ids != candidate.event_ids:
            raise RuntimeDurabilityError(
                "RUNTIME_COMMIT_CONFLICT",
                "runtime commit identity already exists with a different projection",
            )

    def _fetch(
        self,
        connection: sqlite3.Connection,
        runtime_instance_id: str,
        action_id: str,
    ) -> tuple[RuntimeCommitProjection, str, str] | None:
        row = connection.execute(
            "SELECT * FROM mcp_runtime_commit_projection WHERE runtime_instance_id = ? AND action_id = ?",
            (runtime_instance_id, action_id),
        ).fetchone()
        if row is None:
            return None
        return (
            RuntimeCommitProjection(
                commit_id=row["commit_id"],
                runtime_instance_id=row["runtime_instance_id"],
                action_id=row["action_id"],
                state_hash=row["state_hash"],
                event_ids=tuple(
                    _required(item["event_id"], "event_id") for item in json.loads(row["events_json"])
                ),
                event_count=int(row["event_count"]),
                created_at=int(row["created_at"]),
            ),
            row["state_json"],
            row["events_json"],
        )

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for runtime durability")
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
                "CREATE TABLE IF NOT EXISTS mcp_runtime_commit_projection ("
                "commit_id TEXT NOT NULL UNIQUE, runtime_instance_id TEXT NOT NULL, action_id TEXT NOT NULL, "
                "state_json TEXT NOT NULL, events_json TEXT NOT NULL, state_hash TEXT NOT NULL, "
                "event_count INTEGER NOT NULL, created_at INTEGER NOT NULL, "
                "PRIMARY KEY (runtime_instance_id, action_id))"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_runtime_commit_projection_created "
                "ON mcp_runtime_commit_projection (runtime_instance_id, created_at)"
            )


__all__ = [
    "RUNTIME_DURABILITY_CONTRACT",
    "RuntimeCommitProjection",
    "RuntimeDurabilityError",
    "RuntimeDurabilityStore",
]
