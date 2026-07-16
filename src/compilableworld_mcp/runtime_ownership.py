"""Exclusive runtime ownership leases for a host or migration worker."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .contracts import MCPWorldError


RUNTIME_OWNERSHIP_CONTRACT = "compilableworld.runtime-ownership/v0.1"
LEASE_STATUS_ACTIVE = "active"
LEASE_STATUS_EXPIRED = "expired"
LEASE_STATUS_RELEASED = "released"


class RuntimeOwnershipError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = RUNTIME_OWNERSHIP_CONTRACT
        return payload


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", f"{field_name} must be non-empty")
    return normalized


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


def _hash(value: str) -> str:
    return hashlib.sha256(_required(value, "lease_id").encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RuntimeLeaseGrant:
    world_id: str
    runtime_instance_id: str
    owner_id: str
    lease_id: str
    issued_at: int
    expires_at: int
    fencing_token: int = 0

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "format": RUNTIME_OWNERSHIP_CONTRACT,
            "world_id": self.world_id,
            "runtime_instance_id": self.runtime_instance_id,
            "owner_id": self.owner_id,
            "lease_id_present": True,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "fencing_token": self.fencing_token,
        }


@dataclass(frozen=True, slots=True)
class RuntimeOwnershipRecord:
    world_id: str
    runtime_instance_id: str
    owner_id: str
    lease_id_hash: str
    issued_at: int
    expires_at: int
    status: str = LEASE_STATUS_ACTIVE
    revision: int = 0
    fencing_token: int = 0

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "format": RUNTIME_OWNERSHIP_CONTRACT,
            "world_id": self.world_id,
            "runtime_instance_id": self.runtime_instance_id,
            "owner_id": self.owner_id,
            "lease_id_hash": self.lease_id_hash,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "revision": self.revision,
            "fencing_token": self.fencing_token,
        }


class RuntimeOwnershipLeaseStore:
    """Process-local or SQLite-backed exclusive lease store.

    Lease IDs are treated as opaque credentials and persisted only as SHA-256
    hashes.  The store coordinates runtime ownership; it never stores world
    state or decides how a runtime migrates.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = None if db_path is None else str(db_path)
        self._local: dict[tuple[str, str], RuntimeOwnershipRecord] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def acquire(
        self,
        world_id: str,
        runtime_instance_id: str,
        owner_id: str,
        *,
        ttl_seconds: int = 30,
        now: int | None = None,
    ) -> RuntimeLeaseGrant:
        world = _required(world_id, "world_id")
        runtime = _required(runtime_instance_id, "runtime_instance_id")
        owner = _required(owner_id, "owner_id")
        ttl = int(ttl_seconds)
        if ttl <= 0:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "lease TTL must be positive")
        current = _now(now)
        grant = RuntimeLeaseGrant(world, runtime, owner, f"lease_{uuid4().hex}", current, current + ttl)
        key = (world, runtime)
        if self.db_path is None:
            with self._lock:
                existing = self._local.get(key)
                if existing is not None and existing.status == LEASE_STATUS_ACTIVE:
                    if existing.expires_at <= current:
                        existing = replace(existing, status=LEASE_STATUS_EXPIRED, revision=existing.revision + 1)
                        self._local[key] = existing
                    else:
                        raise RuntimeOwnershipError(
                            "RUNTIME_BUSY",
                            "runtime is already owned by another active lease",
                            retryable=True,
                        )
                grant = replace(
                    grant,
                    fencing_token=1 if existing is None else existing.fencing_token + 1,
                )
                revision = 0 if existing is None else existing.revision + 1
                self._local[key] = self._record_from_grant(grant, revision=revision)
            return grant

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._fetch(connection, key)
            if existing is not None and existing.status == LEASE_STATUS_ACTIVE:
                if existing.expires_at <= current:
                    connection.execute(
                        "UPDATE mcp_runtime_ownership SET status = ?, revision = revision + 1 WHERE world_id = ? AND runtime_instance_id = ?",
                        (LEASE_STATUS_EXPIRED, *key),
                    )
                    existing = replace(existing, status=LEASE_STATUS_EXPIRED, revision=existing.revision + 1)
                else:
                    raise RuntimeOwnershipError(
                        "RUNTIME_BUSY",
                        "runtime is already owned by another active lease",
                        retryable=True,
                    )
            grant = replace(
                grant,
                fencing_token=1 if existing is None else existing.fencing_token + 1,
            )
            revision = 0 if existing is None else existing.revision + 1
            values = self._values(self._record_from_grant(grant, revision=revision))
            connection.execute(
                "INSERT INTO mcp_runtime_ownership (world_id, runtime_instance_id, owner_id, lease_id_hash, issued_at, expires_at, status, revision, fencing_token) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(world_id, runtime_instance_id) DO UPDATE SET owner_id=excluded.owner_id, lease_id_hash=excluded.lease_id_hash, issued_at=excluded.issued_at, expires_at=excluded.expires_at, status=excluded.status, revision=excluded.revision, fencing_token=excluded.fencing_token",
                values,
            )
        return grant

    def recover(
        self,
        world_id: str,
        runtime_instance_id: str,
        owner_id: str,
        *,
        ttl_seconds: int = 30,
        now: int | None = None,
    ) -> RuntimeLeaseGrant:
        """Re-issue a lease after an explicit host restart.

        An unexpired lease may only be recovered by the same configured
        owner. Recovery rotates the opaque lease credential, so the previous
        process can no longer renew it if it returns unexpectedly.
        """
        world = _required(world_id, "world_id")
        runtime = _required(runtime_instance_id, "runtime_instance_id")
        owner = _required(owner_id, "owner_id")
        ttl = int(ttl_seconds)
        if ttl <= 0:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "lease TTL must be positive")
        current = _now(now)
        grant = RuntimeLeaseGrant(world, runtime, owner, f"lease_{uuid4().hex}", current, current + ttl)
        key = (world, runtime)
        if self.db_path is None:
            with self._lock:
                existing = self._local.get(key)
                if (
                    existing is not None
                    and existing.status == LEASE_STATUS_ACTIVE
                    and existing.expires_at > current
                    and existing.owner_id != owner
                ):
                    raise RuntimeOwnershipError(
                        "RUNTIME_BUSY",
                        "runtime is already owned by another active lease",
                        retryable=True,
                    )
                grant = replace(
                    grant,
                    fencing_token=1 if existing is None else existing.fencing_token + 1,
                )
                revision = 0 if existing is None else existing.revision + 1
                self._local[key] = self._record_from_grant(grant, revision=revision)
            return grant

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._fetch(connection, key)
            if (
                existing is not None
                and existing.status == LEASE_STATUS_ACTIVE
                and existing.expires_at > current
                and existing.owner_id != owner
            ):
                raise RuntimeOwnershipError(
                    "RUNTIME_BUSY",
                    "runtime is already owned by another active lease",
                    retryable=True,
                )
            grant = replace(
                grant,
                fencing_token=1 if existing is None else existing.fencing_token + 1,
            )
            revision = 0 if existing is None else existing.revision + 1
            values = self._values(self._record_from_grant(grant, revision=revision))
            connection.execute(
                "INSERT INTO mcp_runtime_ownership (world_id, runtime_instance_id, owner_id, lease_id_hash, issued_at, expires_at, status, revision, fencing_token) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(world_id, runtime_instance_id) DO UPDATE SET owner_id=excluded.owner_id, lease_id_hash=excluded.lease_id_hash, issued_at=excluded.issued_at, expires_at=excluded.expires_at, status=excluded.status, revision=excluded.revision, fencing_token=excluded.fencing_token",
                values,
            )
        return grant

    def require(self, grant: RuntimeLeaseGrant, *, now: int | None = None) -> RuntimeOwnershipRecord:
        current = _now(now)
        key = (_required(grant.world_id, "world_id"), _required(grant.runtime_instance_id, "runtime_instance_id"))
        if self.db_path is None:
            with self._lock:
                record = self._local.get(key)
                if record is None:
                    raise RuntimeOwnershipError("RUNTIME_OWNERSHIP_MISSING", "runtime has no ownership lease")
                if record.status == LEASE_STATUS_ACTIVE and record.expires_at <= current:
                    record = replace(record, status=LEASE_STATUS_EXPIRED, revision=record.revision + 1)
                    self._local[key] = record
        else:
            with self._connection() as connection:
                record = self._fetch(connection, key)
                if record is None:
                    raise RuntimeOwnershipError("RUNTIME_OWNERSHIP_MISSING", "runtime has no ownership lease")
                if record.status == LEASE_STATUS_ACTIVE and record.expires_at <= current:
                    connection.execute(
                        "UPDATE mcp_runtime_ownership SET status = ?, revision = revision + 1 WHERE world_id = ? AND runtime_instance_id = ? AND status = ?",
                        (LEASE_STATUS_EXPIRED, *key, LEASE_STATUS_ACTIVE),
                    )
                    record = replace(record, status=LEASE_STATUS_EXPIRED, revision=record.revision + 1)
        self._assert_active(record, grant)
        return record

    def renew(
        self,
        grant: RuntimeLeaseGrant,
        *,
        ttl_seconds: int = 30,
        now: int | None = None,
    ) -> RuntimeLeaseGrant:
        ttl = int(ttl_seconds)
        if ttl <= 0:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "lease TTL must be positive")
        current = _now(now)
        record = self.require(grant, now=current)
        renewed = RuntimeLeaseGrant(
            grant.world_id,
            grant.runtime_instance_id,
            grant.owner_id,
            grant.lease_id,
            record.issued_at,
            current + ttl,
            grant.fencing_token,
        )
        updated = replace(record, expires_at=renewed.expires_at, revision=record.revision + 1)
        self._write(updated)
        return renewed

    def release(self, grant: RuntimeLeaseGrant, *, now: int | None = None) -> RuntimeOwnershipRecord:
        record = self.require(grant, now=now)
        released = replace(record, status=LEASE_STATUS_RELEASED, revision=record.revision + 1)
        self._write(released)
        return released

    def prune(self, *, before: int | None = None) -> int:
        cutoff = _now(before)
        terminal = (LEASE_STATUS_EXPIRED, LEASE_STATUS_RELEASED)
        if self.db_path is None:
            with self._lock:
                keys = [
                    key for key, record in self._local.items()
                    if record.status in terminal and record.expires_at <= cutoff
                ]
                for key in keys:
                    del self._local[key]
                return len(keys)
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM mcp_runtime_ownership WHERE status IN (?, ?) AND expires_at <= ?",
                (*terminal, cutoff),
            )
            return int(cursor.rowcount)

    def _assert_active(self, record: RuntimeOwnershipRecord, grant: RuntimeLeaseGrant) -> None:
        if record.status != LEASE_STATUS_ACTIVE:
            code = {
                LEASE_STATUS_EXPIRED: "RUNTIME_LEASE_EXPIRED",
                LEASE_STATUS_RELEASED: "RUNTIME_LEASE_RELEASED",
            }.get(record.status, "RUNTIME_OWNERSHIP_INVALID")
            raise RuntimeOwnershipError(code, f"runtime ownership lease is {record.status}")
        if record.owner_id != grant.owner_id or record.lease_id_hash != _hash(grant.lease_id):
            raise RuntimeOwnershipError("RUNTIME_OWNERSHIP_MISMATCH", "runtime ownership lease does not match")
        if record.fencing_token != grant.fencing_token:
            raise RuntimeOwnershipError("RUNTIME_FENCING_MISMATCH", "runtime ownership fencing token does not match")

    @staticmethod
    def _record_from_grant(grant: RuntimeLeaseGrant, *, revision: int) -> RuntimeOwnershipRecord:
        return RuntimeOwnershipRecord(
            grant.world_id,
            grant.runtime_instance_id,
            grant.owner_id,
            _hash(grant.lease_id),
            grant.issued_at,
            grant.expires_at,
            revision=revision,
            fencing_token=grant.fencing_token,
        )

    def _write(self, record: RuntimeOwnershipRecord) -> None:
        key = (record.world_id, record.runtime_instance_id)
        if self.db_path is None:
            with self._lock:
                self._local[key] = record
            return
        with self._connection() as connection:
            connection.execute(
                "UPDATE mcp_runtime_ownership SET owner_id = ?, lease_id_hash = ?, issued_at = ?, expires_at = ?, status = ?, revision = ?, fencing_token = ? WHERE world_id = ? AND runtime_instance_id = ?",
                (
                    record.owner_id,
                    record.lease_id_hash,
                    record.issued_at,
                    record.expires_at,
                    record.status,
                    record.revision,
                    record.fencing_token,
                    *key,
                ),
            )

    @staticmethod
    def _values(record: RuntimeOwnershipRecord) -> tuple[Any, ...]:
        return (
            record.world_id,
            record.runtime_instance_id,
            record.owner_id,
            record.lease_id_hash,
            record.issued_at,
            record.expires_at,
            record.status,
            record.revision,
            record.fencing_token,
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RuntimeOwnershipRecord:
        return RuntimeOwnershipRecord(
            world_id=row["world_id"],
            runtime_instance_id=row["runtime_instance_id"],
            owner_id=row["owner_id"],
            lease_id_hash=row["lease_id_hash"],
            issued_at=int(row["issued_at"]),
            expires_at=int(row["expires_at"]),
            status=row["status"],
            revision=int(row["revision"]),
            fencing_token=int(row["fencing_token"]),
        )

    def _fetch(self, connection: sqlite3.Connection, key: tuple[str, str]) -> RuntimeOwnershipRecord | None:
        row = connection.execute(
            "SELECT * FROM mcp_runtime_ownership WHERE world_id = ? AND runtime_instance_id = ?",
            key,
        ).fetchone()
        return None if row is None else self._row_to_record(row)

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for local ownership store")
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
                "CREATE TABLE IF NOT EXISTS mcp_runtime_ownership ("
                "world_id TEXT NOT NULL, runtime_instance_id TEXT NOT NULL, owner_id TEXT NOT NULL, "
                "lease_id_hash TEXT NOT NULL, issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, "
                "status TEXT NOT NULL, revision INTEGER NOT NULL, fencing_token INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (world_id, runtime_instance_id))"
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(mcp_runtime_ownership)").fetchall()
            }
            if "fencing_token" not in columns:
                connection.execute(
                    "ALTER TABLE mcp_runtime_ownership ADD COLUMN fencing_token INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_runtime_ownership_status_expiry "
                "ON mcp_runtime_ownership (status, expires_at)"
            )


class RuntimeOwnershipHeartbeat:
    """Renew one ownership lease until stopped or ownership is lost."""

    def __init__(
        self,
        store: RuntimeOwnershipLeaseStore,
        lease: RuntimeLeaseGrant,
        *,
        ttl_seconds: int = 30,
        interval_seconds: float | None = None,
        on_error: Callable[[RuntimeOwnershipError], None] | None = None,
    ) -> None:
        ttl = int(ttl_seconds)
        if ttl <= 0:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "heartbeat TTL must be positive")
        interval = max(0.1, ttl / 3) if interval_seconds is None else float(interval_seconds)
        if interval <= 0:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "heartbeat interval must be positive")
        self.store = store
        self._lease = lease
        self.ttl_seconds = ttl
        self.interval_seconds = interval
        self.on_error = on_error
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_error: RuntimeOwnershipError | None = None

    @property
    def lease(self) -> RuntimeLeaseGrant:
        with self._lock:
            return self._lease

    @property
    def last_error(self) -> RuntimeOwnershipError | None:
        with self._lock:
            return self._last_error

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def renew_once(self, *, now: int | None = None) -> RuntimeLeaseGrant:
        with self._lock:
            current = self._lease
        renewed = self.store.renew(current, ttl_seconds=self.ttl_seconds, now=now)
        with self._lock:
            self._lease = renewed
            self._last_error = None
        return renewed

    def start(self) -> "RuntimeOwnershipHeartbeat":
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop_event.clear()
            self._last_error = None
            self._thread = threading.Thread(
                target=self._run,
                name=f"cw-ownership-heartbeat-{self.lease.runtime_instance_id}",
                daemon=True,
            )
            self._thread.start()
        return self

    def stop(self, *, release: bool = False, timeout_seconds: float = 5.0) -> RuntimeLeaseGrant | None:
        with self._lock:
            thread = self._thread
        self._stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, float(timeout_seconds)))
        with self._lock:
            self._thread = None
            current = self._lease
        if release:
            self.store.release(current)
            return current
        return None

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.renew_once()
            except RuntimeOwnershipError as exc:
                with self._lock:
                    self._last_error = exc
                if self.on_error is not None:
                    try:
                        self.on_error(exc)
                    except Exception:
                        pass
                return


__all__ = [
    "LEASE_STATUS_ACTIVE",
    "LEASE_STATUS_EXPIRED",
    "LEASE_STATUS_RELEASED",
    "RUNTIME_OWNERSHIP_CONTRACT",
    "RuntimeLeaseGrant",
    "RuntimeOwnershipError",
    "RuntimeOwnershipLeaseStore",
    "RuntimeOwnershipRecord",
    "RuntimeOwnershipHeartbeat",
]
