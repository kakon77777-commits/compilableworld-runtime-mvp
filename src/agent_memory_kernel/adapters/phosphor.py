"""Minimal PHOSPHOR execution-trace capture adapter."""

from __future__ import annotations

from typing import Any

from ..contracts import MemoryScope, RawEvent
from ..service import AgentMemoryKernel


class PhosphorTraceAdapter:
    """Turns an execution trace into Raw evidence without interpreting it as truth."""

    def __init__(self, amk: AgentMemoryKernel, scope: MemoryScope, source_id: str = "phosphor") -> None:
        self.amk = amk
        self.scope = scope
        self.source_id = source_id

    def capture(self, trace: dict[str, Any]) -> RawEvent:
        return self.amk.capture_phosphor_trace(self.scope, trace, self.source_id)

