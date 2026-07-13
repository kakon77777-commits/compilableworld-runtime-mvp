from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    PARSED = "parsed"
    VALIDATED = "validated"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(slots=True)
class Entity:
    entity_id: str
    entity_type: str
    name: str
    components: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StateCell:
    value: Any
    version: int = 0


@dataclass(slots=True)
class StateDelta:
    owner: str
    namespace: str
    key: str
    operation: str
    value: Any
    expected_version: int | None = None
    source_module: str = ""

    @property
    def path(self) -> str:
        return f"{self.owner}::{self.namespace}::{self.key}"


@dataclass(slots=True)
class ActionIR:
    actor_id: str
    verb: str
    target_id: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    action_id: str = field(default_factory=lambda: new_id("action"))
    correlation_id: str = field(default_factory=lambda: new_id("corr"))
    status: ActionStatus = ActionStatus.PROPOSED
    authority: str = "player"
    proposed_at_tick: int = 0


@dataclass(slots=True)
class EventIR:
    event_type: str
    source: str
    payload: dict[str, Any]
    target: str | None = None
    event_id: str = field(default_factory=lambda: new_id("event"))
    causation_id: str | None = None
    correlation_id: str | None = None
    timestamp_tick: int = 0
    visibility: str = "public"
    authority: str = "runtime"
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TransitionResult:
    accepted: bool
    deltas: list[StateDelta] = field(default_factory=list)
    events: list[EventIR] = field(default_factory=list)
    message: str = ""


@dataclass(slots=True)
class ActionReceipt:
    action_id: str
    status: ActionStatus
    message: str
    event_ids: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ModuleContract:
    module_id: str
    version: str
    layer: str
    actions: list[str]
    events: list[str]
    read: list[str]
    write: list[str]
    requires_kernel: list[str] = field(default_factory=list)
