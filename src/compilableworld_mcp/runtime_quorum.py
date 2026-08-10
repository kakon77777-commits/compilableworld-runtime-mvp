"""Fail-closed quorum gate for shared Runtime coordination."""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .contracts import MCPWorldError


RUNTIME_QUORUM_CONTRACT = "compilableworld.mcp-runtime-quorum/v0.1"


class RuntimeQuorumError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = RUNTIME_QUORUM_CONTRACT
        return payload


def _required(value: Any, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise RuntimeQuorumError("INVALID_RUNTIME_QUORUM", f"{field_name} must be non-empty")
    return normalized


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


@dataclass(frozen=True, slots=True)
class RuntimeQuorumTerm:
    term: int
    candidate_id: str
    members: tuple[str, ...]
    votes: tuple[str, ...]
    quorum_size: int
    opened_at: int

    @property
    def quorum_reached(self) -> bool:
        return len(self.votes) >= self.quorum_size

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": RUNTIME_QUORUM_CONTRACT,
            "term": self.term,
            "candidate_id": self.candidate_id,
            "members": list(self.members),
            "votes": list(self.votes),
            "vote_count": len(self.votes),
            "quorum_size": self.quorum_size,
            "quorum_reached": self.quorum_reached,
            "opened_at": self.opened_at,
        }


class RuntimeQuorumGate:
    """Coordinate a candidate term until a configured member quorum votes."""

    def __init__(
        self,
        members: Iterable[str],
        *,
        quorum_size: int | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        normalized = tuple(sorted({_required(member, "member_id") for member in members}))
        if not normalized:
            raise RuntimeQuorumError("INVALID_RUNTIME_QUORUM", "at least one quorum member is required")
        size = len(normalized) // 2 + 1 if quorum_size is None else int(quorum_size)
        if size <= 0 or size > len(normalized):
            raise RuntimeQuorumError("INVALID_RUNTIME_QUORUM", "quorum size must fit the member set")
        self.members = normalized
        self.quorum_size = size
        self.db_path = None if db_path is None else str(db_path)
        self._lock = threading.RLock()
        self._terms: dict[int, tuple[str, int, set[str]]] = {}
        self._next_term = 0
        if self.db_path is not None:
            self._initialize_db()

    def open_term(self, candidate_id: str, *, now: int | None = None) -> RuntimeQuorumTerm:
        candidate = self._member(candidate_id, "candidate_id")
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                self._next_term += 1
                self._terms[self._next_term] = (candidate, current, set())
                return self._snapshot_local(self._next_term)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT COALESCE(MAX(term), 0) FROM mcp_runtime_quorum_term").fetchone()[0]
            term = int(previous) + 1
            connection.execute(
                "INSERT INTO mcp_runtime_quorum_term (term, candidate_id, opened_at) VALUES (?, ?, ?)",
                (term, candidate, current),
            )
            return self._snapshot_connection(connection, term)

    def record_vote(
        self,
        term: int,
        member_id: str,
        *,
        candidate_id: str | None = None,
        now: int | None = None,
    ) -> RuntimeQuorumTerm:
        term_number = self._term_number(term)
        member = self._member(member_id, "member_id")
        current = _now(now)
        if self.db_path is None:
            with self._lock:
                candidate, opened_at, votes = self._term_local(term_number)
                expected = candidate if candidate_id is None else self._member(candidate_id, "candidate_id")
                if expected != candidate:
                    raise RuntimeQuorumError("QUORUM_CANDIDATE_MISMATCH", "vote candidate does not match the term")
                if member in votes:
                    return self._snapshot_local(term_number)
                votes.add(member)
                self._terms[term_number] = (candidate, opened_at, votes)
                return self._snapshot_local(term_number)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT candidate_id FROM mcp_runtime_quorum_term WHERE term = ?",
                (term_number,),
            ).fetchone()
            if row is None:
                raise RuntimeQuorumError("QUORUM_TERM_MISSING", "quorum term does not exist")
            candidate = row["candidate_id"]
            expected = candidate if candidate_id is None else self._member(candidate_id, "candidate_id")
            if expected != candidate:
                raise RuntimeQuorumError("QUORUM_CANDIDATE_MISMATCH", "vote candidate does not match the term")
            existing = connection.execute(
                "SELECT member_id FROM mcp_runtime_quorum_vote WHERE term = ? AND member_id = ?",
                (term_number, member),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO mcp_runtime_quorum_vote (term, member_id, voted_at) VALUES (?, ?, ?)",
                    (term_number, member, current),
                )
            return self._snapshot_connection(connection, term_number)

    def require_quorum(self, term: int, *, candidate_id: str | None = None) -> RuntimeQuorumTerm:
        snapshot = self.status(term)
        if candidate_id is not None and self._member(candidate_id, "candidate_id") != snapshot.candidate_id:
            raise RuntimeQuorumError("QUORUM_CANDIDATE_MISMATCH", "candidate does not match the quorum term")
        if not snapshot.quorum_reached:
            raise RuntimeQuorumError(
                "QUORUM_NOT_REACHED",
                f"quorum requires {snapshot.quorum_size} votes but has {len(snapshot.votes)}",
                retryable=True,
            )
        return snapshot

    def status(self, term: int) -> RuntimeQuorumTerm:
        term_number = self._term_number(term)
        if self.db_path is None:
            with self._lock:
                return self._snapshot_local(term_number)
        with self._connection() as connection:
            return self._snapshot_connection(connection, term_number)

    def _member(self, value: Any, field_name: str) -> str:
        member = _required(value, field_name)
        if member not in self.members:
            raise RuntimeQuorumError("QUORUM_MEMBER_UNKNOWN", f"{field_name} is not a configured quorum member")
        return member

    @staticmethod
    def _term_number(value: Any) -> int:
        if isinstance(value, bool):
            raise RuntimeQuorumError("INVALID_RUNTIME_QUORUM", "term must be a positive integer")
        try:
            term = int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeQuorumError("INVALID_RUNTIME_QUORUM", "term must be a positive integer") from exc
        if term <= 0:
            raise RuntimeQuorumError("INVALID_RUNTIME_QUORUM", "term must be a positive integer")
        return term

    def _term_local(self, term: int) -> tuple[str, int, set[str]]:
        try:
            return self._terms[term]
        except KeyError as exc:
            raise RuntimeQuorumError("QUORUM_TERM_MISSING", "quorum term does not exist") from exc

    def _snapshot_local(self, term: int) -> RuntimeQuorumTerm:
        candidate, opened_at, votes = self._term_local(term)
        return RuntimeQuorumTerm(term, candidate, self.members, tuple(sorted(votes)), self.quorum_size, opened_at)

    def _snapshot_connection(self, connection: sqlite3.Connection, term: int) -> RuntimeQuorumTerm:
        row = connection.execute(
            "SELECT term, candidate_id, opened_at FROM mcp_runtime_quorum_term WHERE term = ?",
            (term,),
        ).fetchone()
        if row is None:
            raise RuntimeQuorumError("QUORUM_TERM_MISSING", "quorum term does not exist")
        votes = tuple(
            sorted(
                item[0]
                for item in connection.execute(
                    "SELECT member_id FROM mcp_runtime_quorum_vote WHERE term = ? ORDER BY member_id",
                    (term,),
                ).fetchall()
            )
        )
        return RuntimeQuorumTerm(term, row["candidate_id"], self.members, votes, self.quorum_size, int(row["opened_at"]))

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for quorum gate")
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
                "CREATE TABLE IF NOT EXISTS mcp_runtime_quorum_member (member_id TEXT PRIMARY KEY)"
            )
            existing = {
                row[0]
                for row in connection.execute("SELECT member_id FROM mcp_runtime_quorum_member").fetchall()
            }
            if existing and existing != set(self.members):
                raise RuntimeQuorumError(
                    "QUORUM_MEMBERSHIP_MISMATCH",
                    "quorum membership mismatch: configured members differ from the shared store",
                )
            for member in self.members:
                connection.execute(
                    "INSERT OR IGNORE INTO mcp_runtime_quorum_member (member_id) VALUES (?)",
                    (member,),
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mcp_runtime_quorum_term (term INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL, opened_at INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mcp_runtime_quorum_vote (term INTEGER NOT NULL, member_id TEXT NOT NULL, voted_at INTEGER NOT NULL, PRIMARY KEY (term, member_id))"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_runtime_quorum_vote_term ON mcp_runtime_quorum_vote (term, member_id)"
            )


__all__ = [
    "RUNTIME_QUORUM_CONTRACT",
    "RuntimeQuorumError",
    "RuntimeQuorumGate",
    "RuntimeQuorumTerm",
]
