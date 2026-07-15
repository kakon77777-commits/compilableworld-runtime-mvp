"""SQLite metadata and rebuildable lexical index for AMK v0.1."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator

from .contracts import (
    ActorIdentity,
    ActorRole,
    AttributionEnvelope,
    MemoryEntry,
    MemoryScope,
    MemoryStatus,
    PromotionContract,
    RawEvent,
    SyncCheckpoint,
    utc_now,
)
from .ledger import LedgerReceipt
from .text import tokens


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


class AMKDatabase:
    """Canonical local metadata store.

    Raw JSONL is the append-only event ledger.  This database stores queryable
    projections, versioned Clean entries, proposals, checkpoints and a
    disposable token index.  The token index never acts as the only source of
    truth: it can be recreated from `clean_entries` at any time.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "AMKDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS amk_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS raw_events (
                event_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                operation TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                attribution_json TEXT NOT NULL,
                environment_json TEXT NOT NULL,
                policy_decision TEXT NOT NULL,
                causal_parents_json TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                ledger_line INTEGER,
                ledger_hash TEXT,
                redacted_at TEXT,
                redacted_by TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_amk_raw_scope_sequence
                ON raw_events(scope_key, sequence DESC);
            CREATE INDEX IF NOT EXISTS idx_amk_raw_operation
                ON raw_events(operation, sequence DESC);

            CREATE TABLE IF NOT EXISTS promotion_contracts (
                proposal_id TEXT PRIMARY KEY,
                decision TEXT NOT NULL,
                contract_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_amk_proposal_decision
                ON promotion_contracts(decision, updated_at DESC);

            CREATE TABLE IF NOT EXISTS clean_entries (
                memory_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                is_current INTEGER NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                scope_key TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL,
                importance REAL NOT NULL,
                attribution_json TEXT NOT NULL,
                subject_refs_json TEXT NOT NULL,
                evidence_refs_json TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(memory_id, version)
            );
            CREATE INDEX IF NOT EXISTS idx_amk_clean_current_scope
                ON clean_entries(is_current, scope_key, status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_amk_clean_subjects
                ON clean_entries(is_current, kind, status);

            CREATE TABLE IF NOT EXISTS derived_tokens (
                memory_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                token TEXT NOT NULL,
                PRIMARY KEY(memory_id, version, token),
                FOREIGN KEY(memory_id, version)
                    REFERENCES clean_entries(memory_id, version) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_amk_token_lookup
                ON derived_tokens(token, memory_id, version);

            CREATE TABLE IF NOT EXISTS sync_checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                raw_sequence INTEGER NOT NULL,
                clean_revision INTEGER NOT NULL,
                index_version INTEGER NOT NULL,
                state_hash TEXT NOT NULL,
                runtime_state_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_amk_checkpoint_session
                ON sync_checkpoints(session_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS sync_acks (
                ack_id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL REFERENCES sync_checkpoints(checkpoint_id) ON DELETE CASCADE,
                target_id TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                acknowledged_at TEXT NOT NULL,
                UNIQUE(checkpoint_id, target_id, status)
            );
            """
        )
        defaults = {
            "schema_version": str(self.SCHEMA_VERSION),
            "clean_revision": "0",
            "index_version": "0",
        }
        for key, value in defaults.items():
            self.connection.execute("INSERT OR IGNORE INTO amk_meta(key, value) VALUES (?, ?)", (key, value))
        self.connection.commit()

    def _meta_int(self, key: str) -> int:
        row = self.connection.execute("SELECT value FROM amk_meta WHERE key = ?", (key,)).fetchone()
        return int(row["value"]) if row is not None else 0

    def _bump_meta(self, key: str) -> int:
        value = self._meta_int(key) + 1
        self.connection.execute(
            "INSERT INTO amk_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        return value

    @property
    def clean_revision(self) -> int:
        return self._meta_int("clean_revision")

    @property
    def index_version(self) -> int:
        return self._meta_int("index_version")

    def next_raw_sequence(self) -> int:
        row = self.connection.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM raw_events").fetchone()
        return int(row["next"])

    def raw_watermark(self) -> int:
        row = self.connection.execute("SELECT COALESCE(MAX(sequence), 0) AS watermark FROM raw_events").fetchone()
        return int(row["watermark"])

    def raw_by_idempotency(self, key: str | None) -> RawEvent | None:
        if not key:
            return None
        row = self.connection.execute("SELECT * FROM raw_events WHERE idempotency_key = ?", (key,)).fetchone()
        return None if row is None else self._raw_from_row(row)

    def record_raw_event(self, event: RawEvent, receipt: LedgerReceipt | None = None) -> bool:
        """Store a ledger projection.  Returns False for an already-reconciled event."""

        try:
            self.connection.execute(
                """INSERT INTO raw_events(
                    event_id, sequence, timestamp, actor_id, actor_role, operation,
                    scope_json, scope_key, payload_json, payload_hash, attribution_json,
                    environment_json, policy_decision, causal_parents_json, idempotency_key,
                    ledger_line, ledger_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.sequence,
                    event.timestamp,
                    event.actor.actor_id,
                    event.actor.role.value,
                    event.operation,
                    _json(event.scope.to_dict()),
                    event.scope.key,
                    _json(event.payload),
                    event.payload_hash,
                    _json(event.attribution.to_dict()),
                    _json(event.environment),
                    event.policy_decision,
                    _json(list(event.causal_parents)),
                    event.idempotency_key,
                    None if receipt is None else receipt.line_number,
                    None if receipt is None else receipt.record_hash,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if self.get_raw_event(event.event_id) is not None:
                return False
            raise exc
        self.connection.commit()
        return True

    def reconcile_ledger(self, records: Iterable[tuple[int, RawEvent, str]]) -> int:
        repaired = 0
        for line_number, event, record_hash in records:
            if self.get_raw_event(event.event_id) is not None:
                continue
            self.record_raw_event(event, LedgerReceipt(line_number, record_hash))
            repaired += 1
        return repaired

    def get_raw_event(self, event_id: str) -> RawEvent | None:
        row = self.connection.execute("SELECT * FROM raw_events WHERE event_id = ?", (event_id,)).fetchone()
        return None if row is None else self._raw_from_row(row)

    def raw_events(
        self, requester: MemoryScope | None = None, limit: int = 200, newest_first: bool = True,
    ) -> list[RawEvent]:
        direction = "DESC" if newest_first else "ASC"
        rows = self.connection.execute(
            f"SELECT * FROM raw_events ORDER BY sequence {direction} LIMIT ?", (max(1, limit),)
        ).fetchall()
        events = [self._raw_from_row(row) for row in rows]
        return [event for event in events if requester is None or event.scope.permits(requester)]

    def search_raw(self, requester: MemoryScope, query_tokens: set[str], limit: int = 12) -> list[RawEvent]:
        candidates = self.raw_events(requester=requester, limit=500, newest_first=True)
        ranked: list[tuple[int, int, RawEvent]] = []
        for index, event in enumerate(candidates):
            haystack = " ".join((event.operation, _json(event.payload), _json(event.environment)))
            overlap = len(query_tokens & tokens(haystack))
            if overlap or not query_tokens:
                ranked.append((overlap, -index, event))
        ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
        return [item[2] for item in ranked[:max(1, limit)]]

    def redact_raw_event(self, event_id: str, actor: ActorIdentity) -> bool:
        cursor = self.connection.execute(
            """UPDATE raw_events SET payload_json=?, policy_decision='redacted',
               redacted_at=?, redacted_by=? WHERE event_id=? AND redacted_at IS NULL""",
            (_json({"redacted": True}), utc_now(), actor.actor_id, event_id),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def _raw_from_row(self, row: sqlite3.Row) -> RawEvent:
        return RawEvent(
            event_id=str(row["event_id"]),
            sequence=int(row["sequence"]),
            timestamp=str(row["timestamp"]),
            actor=ActorIdentity(actor_id=str(row["actor_id"]), role=ActorRole(str(row["actor_role"]))),
            operation=str(row["operation"]),
            scope=MemoryScope.from_dict(json.loads(row["scope_json"])),
            payload=json.loads(row["payload_json"]),
            attribution=AttributionEnvelope.from_dict(json.loads(row["attribution_json"])),
            environment=json.loads(row["environment_json"]),
            policy_decision=str(row["policy_decision"]),
            causal_parents=tuple(json.loads(row["causal_parents_json"])),
            idempotency_key=row["idempotency_key"],
        )

    def save_proposal(self, contract: PromotionContract) -> None:
        now = utc_now()
        self.connection.execute(
            """INSERT INTO promotion_contracts(proposal_id, decision, contract_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(proposal_id) DO UPDATE SET
                 decision=excluded.decision, contract_json=excluded.contract_json, updated_at=excluded.updated_at""",
            (contract.proposal_id, contract.decision.value, _json(contract.to_dict()), contract.created_at, now),
        )
        self.connection.commit()

    def get_proposal(self, proposal_id: str) -> PromotionContract | None:
        row = self.connection.execute(
            "SELECT contract_json FROM promotion_contracts WHERE proposal_id = ?", (proposal_id,)
        ).fetchone()
        return None if row is None else PromotionContract.from_dict(json.loads(row["contract_json"]))

    def list_proposals(self, pending_only: bool = False) -> list[PromotionContract]:
        sql = "SELECT contract_json FROM promotion_contracts"
        parameters: tuple[Any, ...] = ()
        if pending_only:
            sql += " WHERE decision = ?"
            parameters = ("pending",)
        sql += " ORDER BY updated_at DESC"
        return [PromotionContract.from_dict(json.loads(row["contract_json"])) for row in self.connection.execute(sql, parameters)]

    def current_entry(self, memory_id: str) -> MemoryEntry | None:
        row = self.connection.execute(
            "SELECT entry_json FROM clean_entries WHERE memory_id = ? AND is_current = 1", (memory_id,)
        ).fetchone()
        return None if row is None else MemoryEntry.from_dict(json.loads(row["entry_json"]))

    def entry_history(self, memory_id: str) -> list[MemoryEntry]:
        rows = self.connection.execute(
            "SELECT entry_json FROM clean_entries WHERE memory_id = ? ORDER BY version", (memory_id,)
        ).fetchall()
        return [MemoryEntry.from_dict(json.loads(row["entry_json"])) for row in rows]

    def next_entry_version(self, memory_id: str) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM clean_entries WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        return int(row["next"])

    def insert_clean_entry(self, entry: MemoryEntry) -> int:
        """Write a new immutable version and refresh its disposable token projection."""

        if entry.version != self.next_entry_version(entry.memory_id):
            raise ValueError(f"記憶 {entry.memory_id} 的版本必須連續")
        with self.connection:
            self.connection.execute(
                "UPDATE clean_entries SET is_current = 0 WHERE memory_id = ? AND is_current = 1",
                (entry.memory_id,),
            )
            self.connection.execute(
                """INSERT INTO clean_entries(
                    memory_id, version, is_current, kind, status, scope_json, scope_key,
                    content, confidence, importance, attribution_json, subject_refs_json,
                    evidence_refs_json, entry_json, content_hash, created_at, updated_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.memory_id,
                    entry.version,
                    entry.kind.value,
                    entry.status.value,
                    _json(entry.scope.to_dict()),
                    entry.scope.key,
                    entry.content,
                    entry.confidence,
                    entry.importance,
                    _json(entry.attribution.to_dict()),
                    _json(list(entry.subject_refs)),
                    _json(list(entry.evidence_refs)),
                    _json(entry.to_dict()),
                    entry.content_hash,
                    entry.created_at,
                    entry.updated_at,
                ),
            )
            self.connection.execute("DELETE FROM derived_tokens WHERE memory_id = ?", (entry.memory_id,))
            if entry.status in {MemoryStatus.ACTIVE, MemoryStatus.DISPUTED}:
                self.connection.executemany(
                    "INSERT OR IGNORE INTO derived_tokens(memory_id, version, token) VALUES (?, ?, ?)",
                    [(entry.memory_id, entry.version, token) for token in tokens(self._entry_text(entry))],
                )
            revision = self._bump_meta("clean_revision")
            self._bump_meta("index_version")
        return revision

    def list_current_entries(
        self, requester: MemoryScope | None = None, statuses: tuple[MemoryStatus, ...] | None = None,
        limit: int = 500,
    ) -> list[MemoryEntry]:
        clauses = ["is_current = 1"]
        params: list[Any] = []
        if statuses:
            clauses.append("status IN (%s)" % ",".join("?" for _ in statuses))
            params.extend(status.value for status in statuses)
        clauses.append("1 = 1")
        rows = self.connection.execute(
            f"SELECT entry_json FROM clean_entries WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ?",
            (*params, max(1, limit)),
        ).fetchall()
        entries = [MemoryEntry.from_dict(json.loads(row["entry_json"])) for row in rows]
        return [entry for entry in entries if requester is None or entry.scope.permits(requester)]

    def search_current_entries(
        self, requester: MemoryScope, query_tokens: set[str], limit: int = 80,
    ) -> list[tuple[MemoryEntry, int]]:
        if not query_tokens:
            return [(entry, 0) for entry in self.list_current_entries(
                requester, (MemoryStatus.ACTIVE, MemoryStatus.DISPUTED), limit
            )]
        placeholders = ",".join("?" for _ in query_tokens)
        rows = self.connection.execute(
            f"""SELECT clean_entries.entry_json, COUNT(DISTINCT derived_tokens.token) AS matched
                 FROM derived_tokens
                 JOIN clean_entries ON clean_entries.memory_id = derived_tokens.memory_id
                    AND clean_entries.version = derived_tokens.version
                 WHERE clean_entries.is_current = 1
                    AND clean_entries.status IN (?, ?)
                    AND derived_tokens.token IN ({placeholders})
                 GROUP BY clean_entries.memory_id, clean_entries.version
                 ORDER BY matched DESC, clean_entries.updated_at DESC LIMIT ?""",
            (MemoryStatus.ACTIVE.value, MemoryStatus.DISPUTED.value, *query_tokens, max(1, limit)),
        ).fetchall()
        output: list[tuple[MemoryEntry, int]] = []
        for row in rows:
            entry = MemoryEntry.from_dict(json.loads(row["entry_json"]))
            if entry.scope.permits(requester):
                output.append((entry, int(row["matched"])))
        return output

    def rebuild_derived_index(self) -> int:
        with self.connection:
            self.connection.execute("DELETE FROM derived_tokens")
            rows = self.connection.execute(
                "SELECT entry_json FROM clean_entries WHERE is_current = 1 AND status IN (?, ?)",
                (MemoryStatus.ACTIVE.value, MemoryStatus.DISPUTED.value),
            ).fetchall()
            for row in rows:
                entry = MemoryEntry.from_dict(json.loads(row["entry_json"]))
                self.connection.executemany(
                    "INSERT OR IGNORE INTO derived_tokens(memory_id, version, token) VALUES (?, ?, ?)",
                    [(entry.memory_id, entry.version, token) for token in tokens(self._entry_text(entry))],
                )
            return self._bump_meta("index_version")

    @staticmethod
    def _entry_text(entry: MemoryEntry) -> str:
        return " ".join((entry.kind.value, entry.content, " ".join(entry.subject_refs), _json(entry.value)))

    def save_checkpoint(self, checkpoint: SyncCheckpoint) -> None:
        self.connection.execute(
            """INSERT INTO sync_checkpoints(
                checkpoint_id, session_id, raw_sequence, clean_revision, index_version,
                state_hash, runtime_state_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                checkpoint.checkpoint_id,
                checkpoint.session_id,
                checkpoint.raw_sequence,
                checkpoint.clean_revision,
                checkpoint.index_version,
                checkpoint.state_hash,
                _json(checkpoint.runtime_state),
                checkpoint.created_at,
            ),
        )
        self.connection.commit()

    def latest_checkpoint(self, session_id: str) -> SyncCheckpoint | None:
        row = self.connection.execute(
            "SELECT * FROM sync_checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT 1", (session_id,)
        ).fetchone()
        return None if row is None else self._checkpoint_from_row(row)

    def get_checkpoint(self, checkpoint_id: str) -> SyncCheckpoint | None:
        row = self.connection.execute(
            "SELECT * FROM sync_checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
        ).fetchone()
        return None if row is None else self._checkpoint_from_row(row)

    @staticmethod
    def _checkpoint_from_row(row: sqlite3.Row) -> SyncCheckpoint:
        return SyncCheckpoint(
            checkpoint_id=str(row["checkpoint_id"]),
            session_id=str(row["session_id"]),
            raw_sequence=int(row["raw_sequence"]),
            clean_revision=int(row["clean_revision"]),
            index_version=int(row["index_version"]),
            state_hash=str(row["state_hash"]),
            runtime_state=json.loads(row["runtime_state_json"]),
            created_at=str(row["created_at"]),
        )

    def add_sync_ack(self, checkpoint_id: str, target_id: str, status: str, details: dict[str, Any] | None = None) -> None:
        self.connection.execute(
            """INSERT INTO sync_acks(checkpoint_id, target_id, status, details_json, acknowledged_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(checkpoint_id, target_id, status) DO UPDATE SET
                 details_json=excluded.details_json, acknowledged_at=excluded.acknowledged_at""",
            (checkpoint_id, target_id, status, _json(details or {}), utc_now()),
        )
        self.connection.commit()

    def sync_acks(self, checkpoint_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT target_id, status, details_json, acknowledged_at FROM sync_acks WHERE checkpoint_id = ? "
            "ORDER BY acknowledged_at",
            (checkpoint_id,),
        ).fetchall()
        return [
            {
                "target_id": row["target_id"],
                "status": row["status"],
                "details": json.loads(row["details_json"]),
                "acknowledged_at": row["acknowledged_at"],
            }
            for row in rows
        ]

    def stats(self) -> dict[str, int]:
        return {
            "raw_events": int(self.connection.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]),
            "clean_current": int(self.connection.execute(
                "SELECT COUNT(*) FROM clean_entries WHERE is_current = 1"
            ).fetchone()[0]),
            "pending_proposals": int(self.connection.execute(
                "SELECT COUNT(*) FROM promotion_contracts WHERE decision = 'pending'"
            ).fetchone()[0]),
            "raw_watermark": self.raw_watermark(),
            "clean_revision": self.clean_revision,
            "index_version": self.index_version,
        }

