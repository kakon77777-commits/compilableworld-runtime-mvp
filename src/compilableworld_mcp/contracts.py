from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

MCP_READONLY_CONTRACT = "compilableworld.mcp-readonly/v0.1"
SESSION_CONTRACT = "compilableworld.mcp-session/v0.1"
SESSION_REHYDRATION_CONTRACT = "compilableworld.mcp-session-rehydration/v0.1"
RUNTIME_REHYDRATION_CONTRACT = "compilableworld.mcp-runtime-rehydration/v0.1"
WORLD_STATUS_CONTRACT = "compilableworld.mcp-world-status/v0.1"
SCENE_CONTRACT = "compilableworld.mcp-scene/v0.1"
EVENT_PAGE_CONTRACT = "compilableworld.mcp-event-page/v0.1"

ALLOWED_ROLES = frozenset({"player", "observer", "reviewer", "admin"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session_id() -> str:
    return f"session_{uuid4().hex}"


class MCPWorldError(ValueError):
    """Stable, serializable error raised by the transport-neutral MCP core."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": MCP_READONLY_CONTRACT,
            "status": "error",
            "error_code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "world_state_changed": False,
        }


@dataclass(slots=True, frozen=True)
class WorldSession:
    session_id: str
    world_id: str
    runtime_instance_id: str
    actor_id: str
    role: str
    client_id: str
    user_id: str = "local-user"
    model_id: str | None = None
    opened_at: str = field(default_factory=utc_now)
    contract_version: str = MCP_READONLY_CONTRACT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
