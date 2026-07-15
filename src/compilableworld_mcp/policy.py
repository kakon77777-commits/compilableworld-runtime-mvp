from __future__ import annotations

from compilableworld.models import EventIR

from .contracts import ALLOWED_ROLES, MCPWorldError, WorldSession


def validate_role(role: str) -> str:
    normalized = str(role).strip().lower()
    if normalized not in ALLOWED_ROLES:
        raise MCPWorldError("PERMISSION_DENIED", f"unsupported MCP role: {role}")
    return normalized


def event_visible_to(event: EventIR, session: WorldSession) -> bool:
    """Fail-closed visibility filter for the first read-only contract.

    This deliberately does not attempt to infer secrets from arbitrary event
    payloads.  Only events already marked public, actor-private events, and
    audit events for reviewer/admin sessions are exposed.
    """
    visibility = str(event.visibility or "").strip().lower()
    if visibility == "public":
        return True
    if visibility == "private":
        return session.role in {"reviewer", "admin"} or event.target == session.actor_id
    if visibility == "audit":
        return session.role in {"reviewer", "admin"}
    return session.role == "admin"
