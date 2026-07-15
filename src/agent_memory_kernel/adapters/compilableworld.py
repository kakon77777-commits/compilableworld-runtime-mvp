"""CompilableWorld event capture adapter.

The adapter subscribes to Runtime events and writes AMK Raw evidence only.  It
never receives a StateStore reference for mutation and cannot submit a Delta.
As an optional observer it is non-blocking by default: a local memory-store
failure must not turn an already-committed world transition into a failed game
action.
"""

from __future__ import annotations

from typing import Any

from ..contracts import MemoryScope
from ..service import AgentMemoryKernel


class CompilableWorldMemoryAdapter:
    def __init__(self, amk: AgentMemoryKernel, runtime: Any, scope: MemoryScope, *, strict: bool = False) -> None:
        self.amk = amk
        self.runtime = runtime
        self.scope = scope
        self.strict = strict
        self._bound = False
        self._captured = 0
        self._failed = 0
        self.last_error: str | None = None

    def bind(self) -> None:
        if self._bound:
            return
        self.runtime.events.subscribe("*", self.on_event)
        self._bound = True

    def on_event(self, event: Any) -> None:
        try:
            payload = event.to_dict() if hasattr(event, "to_dict") else dict(event)
            payload["runtime_tick"] = getattr(event, "timestamp_tick", None)
            payload["subject_ids"] = [item for item in (getattr(event, "source", None), getattr(event, "target", None)) if item]
            self.amk.capture_runtime_event(
                self.scope,
                event_type=str(getattr(event, "event_type", "unknown")),
                payload=payload,
                source_id=str(getattr(event, "source", "compilableworld.runtime")),
                environment={
                    "adapter": "compilableworld",
                    "runtime_version": self.runtime.package.get("manifest", {}).get("runtime_version"),
                    "world_id": self.runtime.package.get("manifest", {}).get("world_id"),
                },
            )
            self._captured += 1
        except Exception as exc:  # optional evidence capture must not alter Runtime truth
            self._failed += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            if self.strict:
                raise

    @property
    def status(self) -> dict[str, Any]:
        return {"bound": self._bound, "captured": self._captured, "failed": self._failed, "last_error": self.last_error}
