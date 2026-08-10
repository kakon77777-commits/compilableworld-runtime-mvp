"""Server-side World ACL primitive for the first local M12 slice."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .contracts import ALLOWED_ROLES, MCPWorldError


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise MCPWorldError("INVALID_ARGUMENT", f"ACL requires a non-empty {field_name}")
    return normalized


@dataclass(frozen=True, slots=True)
class WorldAccessGrant:
    user_id: str
    world_id: str
    roles: tuple[str, ...]
    actor_ids: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorldACL:
    """Thread-safe in-process ACL with fail-closed authorization."""

    def __init__(self) -> None:
        self._grants: dict[tuple[str, str], WorldAccessGrant] = {}
        self._lock = threading.RLock()

    def grant(
        self,
        user_id: str,
        world_id: str,
        *,
        roles: Iterable[str],
        actor_ids: Iterable[str] | None = None,
    ) -> WorldAccessGrant:
        normalized_roles = tuple(sorted({_required(role, "role").lower() for role in roles}))
        if not normalized_roles or any(role not in ALLOWED_ROLES for role in normalized_roles):
            raise MCPWorldError("PERMISSION_DENIED", "ACL grant contains an unsupported role")
        normalized_actors = None
        if actor_ids is not None:
            normalized_actors = tuple(sorted({_required(actor, "actor_id") for actor in actor_ids}))
            if not normalized_actors:
                raise MCPWorldError("INVALID_ARGUMENT", "actor_ids cannot be empty when provided")
        record = WorldAccessGrant(
            user_id=_required(user_id, "user_id"),
            world_id=_required(world_id, "world_id"),
            roles=normalized_roles,
            actor_ids=normalized_actors,
        )
        with self._lock:
            self._grants[(record.user_id, record.world_id)] = record
        return record

    def revoke(self, user_id: str, world_id: str) -> bool:
        key = (_required(user_id, "user_id"), _required(world_id, "world_id"))
        with self._lock:
            return self._grants.pop(key, None) is not None

    def authorize(self, user_id: str, world_id: str, actor_id: str, role: str) -> WorldAccessGrant:
        key = (_required(user_id, "user_id"), _required(world_id, "world_id"))
        actor = _required(actor_id, "actor_id")
        normalized_role = _required(role, "role").lower()
        with self._lock:
            grant = self._grants.get(key)
        if grant is None:
            raise MCPWorldError("WORLD_ACCESS_DENIED", "user has no grant for this world")
        if normalized_role not in grant.roles:
            raise MCPWorldError("WORLD_ROLE_DENIED", "user grant does not allow this role")
        if grant.actor_ids is not None and actor not in grant.actor_ids:
            raise MCPWorldError("ACTOR_ACCESS_DENIED", "user grant does not allow this actor")
        return grant

    def list_grants(self) -> dict[str, Any]:
        with self._lock:
            grants = [grant.to_dict() for grant in self._grants.values()]
        return {
            "format": "compilableworld.mcp-world-acl/v0.1",
            "read_only": True,
            "world_state_changed": False,
            "grants": sorted(grants, key=lambda item: (item["user_id"], item["world_id"])),
        }


__all__ = ["WorldACL", "WorldAccessGrant"]
