from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from compilableworld.kernel import RuntimeErrorBase, WorldRuntime
from compilableworld.modules import install_builtin_modules

from .contracts import MCPWorldError, WorldSession, new_session_id
from .policy import validate_role
from .projections import (
    recent_events_projection,
    scene_projection,
    session_projection,
    world_status_projection,
)


@dataclass(slots=True)
class WorldBinding:
    world_id: str
    runtime_instance_id: str
    runtime: WorldRuntime
    lock: threading.RLock = field(default_factory=threading.RLock)


class ReadOnlyWorldService:
    """Transport-neutral read-only access to one or more world runtimes.

    Session operations are metadata-only.  Read tools acquire a per-world lock
    so they can safely share a runtime with another serialized gateway, but
    this class offers no multiplayer or distributed consistency guarantee.
    """

    def __init__(self) -> None:
        self._worlds: dict[str, WorldBinding] = {}
        self._sessions: dict[str, WorldSession] = {}
        self._lock = threading.RLock()

    def register_package(
        self,
        package_path: str | Path,
        *,
        event_log_path: str | Path | None = None,
        runtime_instance_id: str | None = None,
    ) -> str:
        runtime = WorldRuntime.from_package(package_path, event_log_path)
        install_builtin_modules(runtime)
        return self.register_runtime(runtime, runtime_instance_id=runtime_instance_id)

    def register_runtime(self, runtime: WorldRuntime, *, runtime_instance_id: str | None = None) -> str:
        try:
            world_id = str(runtime.package["manifest"]["world_id"])
        except (KeyError, TypeError) as exc:
            raise MCPWorldError("WORLD_NOT_FOUND", "runtime package has no valid world_id") from exc
        with self._lock:
            if world_id in self._worlds:
                raise MCPWorldError("STATE_CONFLICT", f"world already registered: {world_id}")
            instance_id = runtime_instance_id or f"runtime_{uuid4().hex}"
            self._worlds[world_id] = WorldBinding(world_id, instance_id, runtime)
        return world_id

    def list_worlds(self) -> dict[str, Any]:
        with self._lock:
            bindings = list(self._worlds.values())
        return {
            "format": "compilableworld.mcp-world-list/v0.1",
            "read_only": True,
            "world_state_changed": False,
            "worlds": [
                {
                    "world_id": binding.world_id,
                    "runtime_instance_id": binding.runtime_instance_id,
                    "world_version": binding.runtime.package["manifest"]["world_version"],
                    "runtime_version": binding.runtime.package["manifest"]["runtime_version"],
                }
                for binding in sorted(bindings, key=lambda item: item.world_id)
            ],
        }

    def open_world_session(
        self,
        world_id: str,
        *,
        actor_id: str | None = None,
        role: str = "player",
        client_id: str = "mcp-client",
        model_id: str | None = None,
    ) -> dict[str, Any]:
        binding = self._binding(world_id)
        normalized_role = validate_role(role)
        resolved_actor = actor_id or binding.runtime.active_player_id or binding.runtime.package.get("world", {}).get("default_player_entity")
        if not resolved_actor:
            raise MCPWorldError("ACTOR_NOT_FOUND", "world has no default actor; actor_id is required")
        if not binding.runtime.registry.contains(resolved_actor):
            raise MCPWorldError("ACTOR_NOT_FOUND", f"unknown actor: {resolved_actor}")
        entity = binding.runtime.registry.get(resolved_actor)
        if normalized_role == "player" and entity.entity_type != "character":
            raise MCPWorldError("PERMISSION_DENIED", "player sessions require a character actor")

        session = WorldSession(
            session_id=new_session_id(),
            world_id=binding.world_id,
            runtime_instance_id=binding.runtime_instance_id,
            actor_id=resolved_actor,
            role=normalized_role,
            client_id=str(client_id or "mcp-client"),
            model_id=None if model_id is None else str(model_id),
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session_projection(session)

    def close_world_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise MCPWorldError("SESSION_INVALID", f"unknown session: {session_id}")
        return {
            "format": "compilableworld.mcp-session-closed/v0.1",
            "read_only": True,
            "world_state_changed": False,
            "session_id": session_id,
            "closed": True,
        }

    def get_world_status(self, session_id: str) -> dict[str, Any]:
        session, binding = self._session_binding(session_id)
        with binding.lock:
            return world_status_projection(binding.runtime, session)

    def get_current_scene(self, session_id: str) -> dict[str, Any]:
        session, binding = self._session_binding(session_id)
        with binding.lock:
            try:
                return scene_projection(binding.runtime, session)
            except RuntimeErrorBase as exc:
                raise MCPWorldError("ACTOR_NOT_FOUND", str(exc)) from exc

    def get_recent_events(
        self,
        session_id: str,
        *,
        after_index: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        session, binding = self._session_binding(session_id)
        with binding.lock:
            try:
                return recent_events_projection(
                    binding.runtime,
                    session,
                    after_index=after_index,
                    limit=limit,
                )
            except ValueError as exc:
                raise MCPWorldError("INVALID_ARGUMENT", str(exc)) from exc

    def runtime_for_testing(self, world_id: str) -> WorldRuntime:
        """Explicit test/local integration hook; not exposed as an MCP tool."""
        return self._binding(world_id).runtime

    def _binding(self, world_id: str) -> WorldBinding:
        with self._lock:
            binding = self._worlds.get(str(world_id))
        if binding is None:
            raise MCPWorldError("WORLD_NOT_FOUND", f"unknown world: {world_id}")
        return binding

    def _session_binding(self, session_id: str) -> tuple[WorldSession, WorldBinding]:
        with self._lock:
            session = self._sessions.get(str(session_id))
        if session is None:
            raise MCPWorldError("SESSION_INVALID", f"unknown session: {session_id}")
        binding = self._binding(session.world_id)
        if binding.runtime_instance_id != session.runtime_instance_id:
            raise MCPWorldError("RUNTIME_VERSION_MISMATCH", "session runtime instance is no longer active")
        return session, binding
