"""Persistent host startup bindings for Runtime package rehydration."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .contracts import MCPWorldError


RUNTIME_BINDING_CONTRACT = "compilableworld.mcp-runtime-binding/v0.1"


class RuntimeBindingError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = RUNTIME_BINDING_CONTRACT
        return payload


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise RuntimeBindingError("INVALID_RUNTIME_BINDING", f"{field_name} must be non-empty")
    return normalized


def _optional_path(value: str | Path | None) -> str | None:
    if value is None:
        return None
    return _required(str(value), "path")


@dataclass(frozen=True, slots=True)
class RuntimeBindingRecord:
    world_id: str
    runtime_instance_id: str
    package_path: str
    event_log_path: str | None = None
    snapshot_path: str | None = None
    enabled: bool = True
    revision: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_id", _required(self.world_id, "world_id"))
        object.__setattr__(self, "runtime_instance_id", _required(self.runtime_instance_id, "runtime_instance_id"))
        object.__setattr__(self, "package_path", _required(self.package_path, "package_path"))
        object.__setattr__(self, "event_log_path", _optional_path(self.event_log_path))
        object.__setattr__(self, "snapshot_path", _optional_path(self.snapshot_path))
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "revision", int(self.revision))

    @property
    def key(self) -> tuple[str, str]:
        return self.world_id, self.runtime_instance_id

    def safe_metadata(self) -> dict[str, Any]:
        """Expose startup metadata without leaking local filesystem paths."""
        return {
            "format": RUNTIME_BINDING_CONTRACT,
            "world_id": self.world_id,
            "runtime_instance_id": self.runtime_instance_id,
            "package_present": True,
            "event_log_present": self.event_log_path is not None,
            "snapshot_present": self.snapshot_path is not None,
            "enabled": self.enabled,
            "revision": self.revision,
        }


class RuntimeBindingStore:
    """Process-local or SQLite-backed startup binding registry."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[tuple[str, str], RuntimeBindingRecord] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def register(self, record: RuntimeBindingRecord) -> RuntimeBindingRecord:
        if not isinstance(record, RuntimeBindingRecord):
            raise RuntimeBindingError("INVALID_RUNTIME_BINDING", "record must be a RuntimeBindingRecord")
        if self.db_path is None:
            with self._lock:
                if record.key in self._local:
                    raise RuntimeBindingError("RUNTIME_BINDING_CONFLICT", "runtime binding already exists")
                self._local[record.key] = record
            return record
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO mcp_runtime_bindings (world_id, runtime_instance_id, package_path, event_log_path, snapshot_path, enabled, revision) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    self._values(record),
                )
            except sqlite3.IntegrityError as exc:
                raise RuntimeBindingError("RUNTIME_BINDING_CONFLICT", "runtime binding already exists") from exc
        return record

    def update(self, record: RuntimeBindingRecord) -> RuntimeBindingRecord:
        if not isinstance(record, RuntimeBindingRecord):
            raise RuntimeBindingError("INVALID_RUNTIME_BINDING", "record must be a RuntimeBindingRecord")
        if self.db_path is None:
            with self._lock:
                existing = self._local.get(record.key)
                if existing is None:
                    raise RuntimeBindingError("RUNTIME_BINDING_MISSING", "runtime binding does not exist")
                updated = replace(record, revision=existing.revision + 1)
                self._local[record.key] = updated
            return updated
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT revision FROM mcp_runtime_bindings WHERE world_id = ? AND runtime_instance_id = ?",
                record.key,
            ).fetchone()
            if existing is None:
                raise RuntimeBindingError("RUNTIME_BINDING_MISSING", "runtime binding does not exist")
            updated = replace(record, revision=int(existing["revision"]) + 1)
            cursor = connection.execute(
                "UPDATE mcp_runtime_bindings SET package_path = ?, event_log_path = ?, snapshot_path = ?, enabled = ?, revision = ? "
                "WHERE world_id = ? AND runtime_instance_id = ?",
                (
                    updated.package_path,
                    updated.event_log_path,
                    updated.snapshot_path,
                    int(updated.enabled),
                    updated.revision,
                    *updated.key,
                ),
            )
        return updated

    def get(self, world_id: str, runtime_instance_id: str) -> RuntimeBindingRecord | None:
        key = (_required(world_id, "world_id"), _required(runtime_instance_id, "runtime_instance_id"))
        if self.db_path is None:
            with self._lock:
                return self._local.get(key)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM mcp_runtime_bindings WHERE world_id = ? AND runtime_instance_id = ?",
                key,
            ).fetchone()
            return None if row is None else self._row_to_record(row)

    def list_enabled(self) -> list[RuntimeBindingRecord]:
        if self.db_path is None:
            with self._lock:
                return sorted(
                    (record for record in self._local.values() if record.enabled),
                    key=lambda item: item.key,
                )
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM mcp_runtime_bindings WHERE enabled = 1 ORDER BY world_id, runtime_instance_id"
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def list_all(self) -> list[RuntimeBindingRecord]:
        if self.db_path is None:
            with self._lock:
                return sorted(self._local.values(), key=lambda item: item.key)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM mcp_runtime_bindings ORDER BY world_id, runtime_instance_id"
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _values(record: RuntimeBindingRecord) -> tuple[Any, ...]:
        return (
            record.world_id,
            record.runtime_instance_id,
            record.package_path,
            record.event_log_path,
            record.snapshot_path,
            int(record.enabled),
            record.revision,
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RuntimeBindingRecord:
        return RuntimeBindingRecord(
            world_id=row["world_id"],
            runtime_instance_id=row["runtime_instance_id"],
            package_path=row["package_path"],
            event_log_path=row["event_log_path"],
            snapshot_path=row["snapshot_path"],
            enabled=bool(row["enabled"]),
            revision=int(row["revision"]),
        )

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for runtime bindings")
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
                "CREATE TABLE IF NOT EXISTS mcp_runtime_bindings ("
                "world_id TEXT NOT NULL, runtime_instance_id TEXT NOT NULL, package_path TEXT NOT NULL, "
                "event_log_path TEXT, snapshot_path TEXT, enabled INTEGER NOT NULL, revision INTEGER NOT NULL, "
                "PRIMARY KEY (world_id, runtime_instance_id))"
            )


__all__ = [
    "RUNTIME_BINDING_CONTRACT",
    "RuntimeBindingError",
    "RuntimeBindingRecord",
    "RuntimeBindingStore",
]
