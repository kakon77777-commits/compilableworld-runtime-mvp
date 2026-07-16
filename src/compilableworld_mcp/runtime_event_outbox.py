"""Replayable bridge from the authoritative Runtime EventLog to the outbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import MCPWorldError
from .outbox import TransactionalOutbox


RUNTIME_EVENT_OUTBOX_CONTRACT = "compilableworld.mcp-runtime-event-outbox/v0.1"


@dataclass(slots=True)
class RuntimeEventOutboxBridge:
    runtime_instance_id: str
    outbox: TransactionalOutbox
    cursor: int = 0

    def drain(self, runtime: Any, *, now: int | None = None, limit: int = 100) -> int:
        if not str(self.runtime_instance_id).strip():
            raise MCPWorldError("INVALID_OUTBOX_BRIDGE", "runtime_instance_id must be non-empty")
        if isinstance(limit, bool) or int(limit) <= 0:
            raise MCPWorldError("INVALID_OUTBOX_BRIDGE", "drain limit must be positive")
        events = getattr(getattr(runtime, "event_log", None), "events", None)
        if not isinstance(events, list):
            raise MCPWorldError("INVALID_OUTBOX_BRIDGE", "runtime has no readable EventLog")
        start = min(max(0, int(self.cursor)), len(events))
        stop = min(len(events), start + int(limit))
        scanned = 0
        for index in range(start, stop):
            event = events[index]
            event_id = str(getattr(event, "event_id", "")).strip()
            if not event_id:
                raise MCPWorldError("INVALID_OUTBOX_BRIDGE", "EventLog event has no event_id")
            payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)
            self.outbox.enqueue(
                "runtime.event",
                event_id,
                payload,
                dedupe_key=f"{self.runtime_instance_id}:{event_id}",
                now=now,
            )
            self.cursor = index + 1
            scanned += 1
        return scanned


__all__ = ["RUNTIME_EVENT_OUTBOX_CONTRACT", "RuntimeEventOutboxBridge"]
