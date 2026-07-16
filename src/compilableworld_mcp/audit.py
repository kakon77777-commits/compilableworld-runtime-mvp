"""Safe, transport-neutral audit envelopes for MCP operations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .auth_pipeline import AuthenticatedRequest


MCP_AUDIT_ENVELOPE_CONTRACT = "compilableworld.mcp-audit-envelope/v0.1"


def _required(value: Any, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


@dataclass(frozen=True, slots=True)
class MCPAuditEnvelope:
    request_id: str
    operation: str
    outcome: str
    occurred_at: int
    transport: str
    client_id: str
    principal_user_id: str
    principal_token_id: str | None = None
    session_id: str | None = None
    world_id: str | None = None
    runtime_instance_id: str | None = None
    actor_id: str | None = None
    role: str | None = None
    world_state_changed: bool = False
    event_ids: tuple[str, ...] = ()
    idempotency_key: str | None = None
    error_code: str | None = None
    delivery_pending: bool = False
    replayed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": MCP_AUDIT_ENVELOPE_CONTRACT,
            "request_id": self.request_id,
            "operation": self.operation,
            "outcome": self.outcome,
            "occurred_at": self.occurred_at,
            "transport": self.transport,
            "client_id": self.client_id,
            "principal_user_id": self.principal_user_id,
            "principal_token_id": self.principal_token_id,
            "session_id": self.session_id,
            "world_id": self.world_id,
            "runtime_instance_id": self.runtime_instance_id,
            "actor_id": self.actor_id,
            "role": self.role,
            "world_state_changed": self.world_state_changed,
            "event_ids": list(self.event_ids),
            "idempotency_key": self.idempotency_key,
            "error_code": self.error_code,
            "delivery_pending": self.delivery_pending,
            "replayed": self.replayed,
        }


def build_audit_envelope(
    request: AuthenticatedRequest,
    operation: str,
    *,
    outcome: str = "success",
    world_state_changed: bool = False,
    event_ids: Iterable[str] = (),
    idempotency_key: str | None = None,
    error_code: str | None = None,
    delivery_pending: bool = False,
    replayed: bool = False,
    scope: Mapping[str, Any] | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    """Build a safe audit projection from an already authenticated request."""
    session = request.session
    override = {} if scope is None else dict(scope)
    normalized_events = tuple(_required(event_id, "event_id") for event_id in event_ids)
    return MCPAuditEnvelope(
        request_id=_required(request.context.request_id, "request_id"),
        operation=_required(operation, "operation"),
        outcome=_required(outcome, "outcome"),
        occurred_at=_now(now),
        transport=_required(request.context.transport, "transport"),
        client_id=_required(request.context.client_id, "client_id"),
        principal_user_id=_required(request.principal.user_id, "principal_user_id"),
        principal_token_id=_optional(request.principal.token_id),
        session_id=override.get("session_id", None if session is None else session.session_id),
        world_id=override.get("world_id", None if session is None else session.world_id),
        runtime_instance_id=override.get("runtime_instance_id", None if session is None else session.runtime_instance_id),
        actor_id=override.get("actor_id", None if session is None else session.actor_id),
        role=override.get("role", None if session is None else session.role),
        world_state_changed=bool(world_state_changed),
        event_ids=normalized_events,
        idempotency_key=_optional(idempotency_key),
        error_code=_optional(error_code),
        delivery_pending=bool(delivery_pending),
        replayed=bool(replayed),
    ).to_dict()


__all__ = [
    "MCP_AUDIT_ENVELOPE_CONTRACT",
    "MCPAuditEnvelope",
    "build_audit_envelope",
]
