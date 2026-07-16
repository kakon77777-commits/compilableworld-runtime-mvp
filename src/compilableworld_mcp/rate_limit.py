"""Small deterministic sliding-window limiter for MCP request controls."""

from __future__ import annotations

import threading
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "allowed": self.allowed,
            "limit": self.limit,
            "remaining": self.remaining,
            "retry_after_seconds": self.retry_after_seconds,
        }


class SlidingWindowRateLimiter:
    """Process-local or SQLite-backed fixed-cost sliding-window limiter.

    The limiter is deliberately independent from authentication and world
    state. SQLite mode shares the window across local host processes using the
    same database; a distributed deployment can replace this class with a
    shared implementation without changing the action contract.
    """

    def __init__(
        self,
        *,
        limit: int = 30,
        window_seconds: int = 60,
        db_path: str | Path | None = None,
    ) -> None:
        if int(limit) <= 0 or int(window_seconds) <= 0:
            raise ValueError("rate limit and window must be positive")
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self.db_path = None if db_path is None else str(db_path)
        self._hits: dict[str, list[int]] = {}
        self._lock = threading.RLock()
        if self.db_path is not None:
            self._initialize_db()

    def consume(
        self,
        key: str,
        *,
        now: int | None = None,
        cost: int = 1,
        limit: int | None = None,
    ) -> RateLimitDecision:
        normalized = str(key).strip()
        if not normalized:
            raise ValueError("rate-limit key must be non-empty")
        if isinstance(cost, bool) or int(cost) <= 0:
            raise ValueError("rate-limit cost must be positive")
        effective_limit = self.limit if limit is None else int(limit)
        if effective_limit <= 0:
            raise ValueError("rate-limit limit must be positive")
        current = int(time.time()) if now is None else int(now)
        cutoff = current - self.window_seconds + 1
        if self.db_path is not None:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM mcp_rate_limit_hits WHERE hit_at < ?", (cutoff,))
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM mcp_rate_limit_hits WHERE rate_key = ? AND hit_at >= ?",
                        (normalized, cutoff),
                    ).fetchone()[0]
                )
                if count + int(cost) > effective_limit:
                    first = connection.execute(
                        "SELECT MIN(hit_at) FROM mcp_rate_limit_hits WHERE rate_key = ?",
                        (normalized,),
                    ).fetchone()[0]
                    retry = max(1, int(first) + self.window_seconds - current) if first is not None else self.window_seconds
                    return RateLimitDecision(False, effective_limit, max(0, effective_limit - count), retry)
                connection.executemany(
                    "INSERT INTO mcp_rate_limit_hits (rate_key, hit_at) VALUES (?, ?)",
                    [(normalized, current)] * int(cost),
                )
                return RateLimitDecision(True, effective_limit, max(0, effective_limit - count - int(cost)), 0)
        with self._lock:
            hits = [tick for tick in self._hits.get(normalized, []) if tick >= cutoff]
            self._hits[normalized] = hits
            if len(hits) + int(cost) > effective_limit:
                retry = max(1, hits[0] + self.window_seconds - current) if hits else self.window_seconds
                return RateLimitDecision(False, effective_limit, max(0, effective_limit - len(hits)), retry)
            hits.extend([current] * int(cost))
            return RateLimitDecision(True, effective_limit, max(0, effective_limit - len(hits)), 0)

    def prune(self, *, now: int | None = None) -> int:
        current = int(time.time()) if now is None else int(now)
        cutoff = current - self.window_seconds + 1
        if self.db_path is not None:
            with self._connection() as connection:
                cursor = connection.execute("DELETE FROM mcp_rate_limit_hits WHERE hit_at < ?", (cutoff,))
                return int(cursor.rowcount)
        with self._lock:
            empty = [key for key, hits in self._hits.items() if not any(tick >= cutoff for tick in hits)]
            for key in empty:
                del self._hits[key]
            return len(empty)

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("SQLite connection requested for local rate limiter")
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _connection(self):
        class ConnectionContext:
            def __init__(self, owner: "SlidingWindowRateLimiter") -> None:
                self.owner = owner
                self.connection: sqlite3.Connection | None = None

            def __enter__(self) -> sqlite3.Connection:
                self.connection = self.owner._connect()
                return self.connection

            def __exit__(self, exc_type, exc, tb) -> None:
                assert self.connection is not None
                if exc_type is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
                self.connection.close()

        return ConnectionContext(self)

    def _initialize_db(self) -> None:
        path = Path(self.db_path or "")
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mcp_rate_limit_hits ("
                "rate_key TEXT NOT NULL, hit_at INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_mcp_rate_limit_hits_key_time "
                "ON mcp_rate_limit_hits (rate_key, hit_at)"
            )


__all__ = ["RateLimitDecision", "SlidingWindowRateLimiter"]
