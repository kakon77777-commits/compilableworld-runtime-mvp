"""Append-only local Raw ledger with a lightweight hash chain.

The JSONL file is intentionally a second durable representation, not a query
index.  SQLite metadata can be rebuilt from it after an interrupted process;
the append order is the AMK Raw watermark.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterable, Iterator

from .contracts import RawEvent, stable_json


class LedgerIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LedgerReceipt:
    line_number: int
    record_hash: str


class JsonlLedger:
    """A single-process append-only JSONL ledger.

    This is a local durability primitive, not an immutable remote backup.  A
    later replication layer must report its acknowledgement separately.
    """

    GENESIS_HASH = "sha256:genesis"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = Lock()
        self._line_count, self._last_hash = self._scan_tail()

    def _scan_tail(self) -> tuple[int, str]:
        previous = self.GENESIS_HASH
        count = 0
        with self.path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                count += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LedgerIntegrityError(f"Raw ledger 第 {count} 行不是合法 JSON") from exc
                if record.get("previous_hash") != previous:
                    raise LedgerIntegrityError(f"Raw ledger 第 {count} 行的 hash chain 中斷")
                expected = self._record_hash(record["event"], previous)
                if record.get("record_hash") != expected:
                    raise LedgerIntegrityError(f"Raw ledger 第 {count} 行的 record hash 不一致")
                previous = expected
        return count, previous

    @staticmethod
    def _record_hash(event: dict[str, object], previous_hash: str) -> str:
        digest = hashlib.sha256(stable_json({"event": event, "previous_hash": previous_hash}).encode("utf-8"))
        return f"sha256:{digest.hexdigest()}"

    def append(self, event: RawEvent) -> LedgerReceipt:
        """Append and fsync an event before returning its durable acknowledgement."""

        with self._lock:
            event_data = event.to_dict()
            record_hash = self._record_hash(event_data, self._last_hash)
            record = {
                "entry_type": "raw_event",
                "event": event_data,
                "previous_hash": self._last_hash,
                "record_hash": record_hash,
            }
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(stable_json(record) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._line_count += 1
            self._last_hash = record_hash
            return LedgerReceipt(line_number=self._line_count, record_hash=record_hash)

    def iter_records(self) -> Iterator[tuple[int, RawEvent, str]]:
        """Yield verified records for SQLite recovery or audit."""

        previous = self.GENESIS_HASH
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("previous_hash") != previous:
                    raise LedgerIntegrityError(f"Raw ledger 第 {line_number} 行的 hash chain 中斷")
                expected = self._record_hash(record["event"], previous)
                if record.get("record_hash") != expected:
                    raise LedgerIntegrityError(f"Raw ledger 第 {line_number} 行的 record hash 不一致")
                previous = expected
                yield line_number, RawEvent.from_dict(record["event"]), expected

    def verify(self) -> dict[str, object]:
        count, last_hash = self._scan_tail()
        return {"path": str(self.path), "records": count, "last_hash": last_hash, "valid": True}

    @property
    def last_hash(self) -> str:
        return self._last_hash

    @property
    def line_count(self) -> int:
        return self._line_count


def replayable_events(ledger: JsonlLedger) -> Iterable[RawEvent]:
    for _, event, _ in ledger.iter_records():
        yield event

