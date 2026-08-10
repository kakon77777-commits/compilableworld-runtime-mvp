from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from compilableworld.kernel import RuntimeErrorBase, WorldRuntime
from compilableworld.modules import install_builtin_modules

from .acl import WorldACL
from .contracts import (
    MCPWorldError,
    RUNTIME_REHYDRATION_CONTRACT,
    SESSION_REHYDRATION_CONTRACT,
    WorldSession,
    new_session_id,
)
from .policy import validate_role
from .projections import (
    recent_events_projection,
    scene_projection,
    session_projection,
    world_status_projection,
)
from .runtime_ownership import (
    RuntimeLeaseGrant,
    RuntimeOwnershipError,
    RuntimeOwnershipHeartbeat,
    RuntimeOwnershipLeaseStore,
)
from .runtime_bindings import RuntimeBindingRecord, RuntimeBindingStore
from .session_store import SessionLifecycleRecord


@dataclass(slots=True)
class WorldBinding:
    world_id: str
    runtime_instance_id: str
    runtime: WorldRuntime
    lock: threading.RLock = field(default_factory=threading.RLock)
    ownership_lease: RuntimeLeaseGrant | None = None
    ownership_heartbeat: RuntimeOwnershipHeartbeat | None = None


class ReadOnlyWorldService:
    """Transport-neutral read-only access to one or more world runtimes.

    Session operations are metadata-only.  Read tools acquire a per-world lock
    so they can safely share a runtime with another serialized gateway, but
    this class offers no multiplayer or distributed consistency guarantee.
    """

    def __init__(
        self,
        *,
        acl: WorldACL | None = None,
        ownership_store: RuntimeOwnershipLeaseStore | None = None,
        ownership_owner_id: str | None = None,
        ownership_ttl_seconds: int = 30,
    ) -> None:
        self._worlds: dict[str, WorldBinding] = {}
        self._sessions: dict[str, WorldSession] = {}
        self._acl = acl
        self._lock = threading.RLock()
        if ownership_store is None and ownership_owner_id is not None:
            raise MCPWorldError("INVALID_RUNTIME_OWNERSHIP", "ownership_owner_id requires ownership_store")
        if ownership_store is not None and not str(ownership_owner_id or "").strip():
            raise MCPWorldError("INVALID_RUNTIME_OWNERSHIP", "ownership_store requires ownership_owner_id")
        if int(ownership_ttl_seconds) <= 0:
            raise MCPWorldError("INVALID_RUNTIME_OWNERSHIP", "ownership TTL must be positive")
        self._ownership_store = ownership_store
        self._ownership_owner_id = None if ownership_owner_id is None else str(ownership_owner_id).strip()
        self._ownership_ttl_seconds = int(ownership_ttl_seconds)

    def register_package(
        self,
        package_path: str | Path,
        *,
        event_log_path: str | Path | None = None,
        runtime_instance_id: str | None = None,
        recover_ownership: bool = False,
    ) -> str:
        runtime = WorldRuntime.from_package(package_path, event_log_path)
        install_builtin_modules(runtime)
        return self.register_runtime(
            runtime,
            runtime_instance_id=runtime_instance_id,
            recover_ownership=recover_ownership,
        )

    def register_runtime(
        self,
        runtime: WorldRuntime,
        *,
        runtime_instance_id: str | None = None,
        recover_ownership: bool = False,
    ) -> str:
        try:
            world_id = str(runtime.package["manifest"]["world_id"])
        except (KeyError, TypeError) as exc:
            raise MCPWorldError("WORLD_NOT_FOUND", "runtime package has no valid world_id") from exc
        with self._lock:
            if world_id in self._worlds:
                raise MCPWorldError("STATE_CONFLICT", f"world already registered: {world_id}")
            instance_id = runtime_instance_id or f"runtime_{uuid4().hex}"
            lease = None
            if self._ownership_store is not None:
                acquire = self._ownership_store.recover if recover_ownership else self._ownership_store.acquire
                lease = acquire(
                    world_id,
                    instance_id,
                    self._ownership_owner_id or "",
                    ttl_seconds=self._ownership_ttl_seconds,
                )
            self._worlds[world_id] = WorldBinding(world_id, instance_id, runtime, ownership_lease=lease)
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
                    "ownership": self._ownership_metadata(binding),
                }
                for binding in sorted(bindings, key=lambda item: item.world_id)
            ],
        }

    def rehydrate_runtime_bindings(
        self,
        bindings: Iterable[RuntimeBindingRecord],
        *,
        recover_ownership: bool = False,
    ) -> dict[str, Any]:
        """Load host startup bindings and optionally their snapshots."""
        materialized = [binding for binding in bindings if binding.enabled]
        prepared: list[tuple[RuntimeBindingRecord, WorldRuntime]] = []
        seen_worlds: set[str] = set()
        for binding in materialized:
            if binding.world_id in seen_worlds:
                raise MCPWorldError("STATE_CONFLICT", f"duplicate runtime binding: {binding.world_id}")
            seen_worlds.add(binding.world_id)
            with self._lock:
                if binding.world_id in self._worlds:
                    raise MCPWorldError("STATE_CONFLICT", f"world already registered: {binding.world_id}")
            try:
                runtime = WorldRuntime.from_package(binding.package_path, binding.event_log_path)
                install_builtin_modules(runtime)
                loaded_world_id = str(runtime.package["manifest"]["world_id"])
                if loaded_world_id != binding.world_id:
                    raise MCPWorldError(
                        "RUNTIME_BINDING_MISMATCH",
                        f"binding world_id does not match package: {binding.world_id}",
                    )
                if binding.snapshot_path is not None:
                    runtime.load_snapshot(binding.snapshot_path)
            except MCPWorldError:
                raise
            except (OSError, RuntimeErrorBase, KeyError, TypeError, ValueError) as exc:
                raise MCPWorldError(
                    "RUNTIME_REHYDRATION_FAILED",
                    f"cannot load runtime binding: {binding.world_id}",
                ) from exc
            prepared.append((binding, runtime))

        registered: list[str] = []
        try:
            for binding, runtime in prepared:
                self.register_runtime(
                    runtime,
                    runtime_instance_id=binding.runtime_instance_id,
                    recover_ownership=recover_ownership,
                )
                registered.append(binding.world_id)
        except Exception:
            with self._lock:
                removed = [self._worlds.pop(world_id, None) for world_id in registered]
            if self._ownership_store is not None:
                for binding in removed:
                    if binding is not None and binding.ownership_lease is not None:
                        try:
                            self._ownership_store.release(binding.ownership_lease)
                        except Exception:
                            pass
            raise
        return {
            "format": RUNTIME_REHYDRATION_CONTRACT,
            "read_only": True,
            "world_state_changed": False,
            "restored": len(registered),
            "world_ids": registered,
        }

    def rehydrate_from_binding_store(
        self,
        binding_store: RuntimeBindingStore,
        *,
        recover_ownership: bool = False,
    ) -> dict[str, Any]:
        """Restore enabled startup bindings from a local/SQLite registry."""
        return self.rehydrate_runtime_bindings(
            binding_store.list_enabled(),
            recover_ownership=recover_ownership,
        )

    def open_world_session(
        self,
        world_id: str,
        *,
        actor_id: str | None = None,
        role: str = "player",
        client_id: str = "mcp-client",
        user_id: str = "local-user",
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
        normalized_user_id = str(user_id or "local-user").strip()
        if self._acl is not None:
            self._acl.authorize(normalized_user_id, binding.world_id, resolved_actor, normalized_role)

        session = WorldSession(
            session_id=new_session_id(),
            world_id=binding.world_id,
            runtime_instance_id=binding.runtime_instance_id,
            actor_id=resolved_actor,
            role=normalized_role,
            client_id=str(client_id or "mcp-client"),
            user_id=normalized_user_id,
            model_id=None if model_id is None else str(model_id),
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session_projection(session)

    def rehydrate_sessions(
        self,
        records: Iterable[SessionLifecycleRecord],
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Restore active server-side sessions after runtimes are registered.

        This is intentionally explicit: package loading and ownership recovery
        remain host startup responsibilities, while the lifecycle store is the
        source of truth for which sessions may be restored.
        """
        current = int(time.time()) if now is None else int(now)
        materialized = list(records)
        restored: list[WorldSession] = []
        with self._lock:
            existing_ids = set(self._sessions)
            seen_ids: set[str] = set()
            for record in materialized:
                if record.session_id in seen_ids or record.session_id in existing_ids:
                    raise MCPWorldError("STATE_CONFLICT", f"session already registered: {record.session_id}")
                seen_ids.add(record.session_id)
                if record.status != "active" or record.expires_at <= current:
                    raise MCPWorldError("SESSION_EXPIRED", f"session is not active: {record.session_id}")
                binding = self._worlds.get(record.world_id)
                if binding is None:
                    raise MCPWorldError("WORLD_NOT_FOUND", f"unknown world: {record.world_id}")
                if binding.runtime_instance_id != record.runtime_instance_id:
                    raise MCPWorldError(
                        "RUNTIME_VERSION_MISMATCH",
                        f"session runtime instance is no longer active: {record.session_id}",
                    )
                role = validate_role(record.role)
                if not binding.runtime.registry.contains(record.actor_id):
                    raise MCPWorldError("ACTOR_NOT_FOUND", f"unknown actor: {record.actor_id}")
                entity = binding.runtime.registry.get(record.actor_id)
                if role == "player" and entity.entity_type != "character":
                    raise MCPWorldError("PERMISSION_DENIED", "player sessions require a character actor")
                if self._acl is not None:
                    self._acl.authorize(record.user_id, record.world_id, record.actor_id, role)
                restored.append(
                    WorldSession(
                        session_id=record.session_id,
                        world_id=record.world_id,
                        runtime_instance_id=record.runtime_instance_id,
                        actor_id=record.actor_id,
                        role=role,
                        client_id=record.client_id,
                        user_id=record.user_id,
                        model_id=record.model_id,
                        opened_at=datetime.fromtimestamp(record.issued_at, timezone.utc).isoformat(),
                    )
                )
            self._sessions.update({session.session_id: session for session in restored})
        return {
            "format": SESSION_REHYDRATION_CONTRACT,
            "read_only": True,
            "world_state_changed": False,
            "restored": len(restored),
            "session_ids": [session.session_id for session in restored],
        }

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

    def session_for_security(self, session_id: str) -> WorldSession:
        """Return live session metadata for a server-side security facade."""
        with self._lock:
            session = self._sessions.get(str(session_id))
        if session is None:
            raise MCPWorldError("SESSION_INVALID", f"unknown session: {session_id}")
        return session

    def runtime_for_security(self, session_id: str) -> WorldRuntime:
        """Return the authoritative runtime bound to a live session."""
        _, binding = self._session_binding(session_id)
        return binding.runtime

    def renew_runtime_ownership(self, world_id: str, *, now: int | None = None) -> dict[str, Any]:
        """Renew the optional host ownership lease for a registered world."""
        binding = self._binding(world_id)
        if self._ownership_store is None or binding.ownership_lease is None:
            raise MCPWorldError("RUNTIME_OWNERSHIP_UNCONFIGURED", "world has no configured ownership lease")
        if binding.ownership_heartbeat is not None:
            binding.ownership_lease = binding.ownership_heartbeat.renew_once(now=now)
        else:
            binding.ownership_lease = self._ownership_store.renew(
                binding.ownership_lease,
                ttl_seconds=self._ownership_ttl_seconds,
                now=now,
            )
        return binding.ownership_lease.safe_metadata()

    def start_runtime_ownership_heartbeat(
        self,
        world_id: str,
        *,
        interval_seconds: float | None = None,
        on_error: Callable[[RuntimeOwnershipError], None] | None = None,
    ) -> dict[str, Any]:
        """Start automatic lease renewal for one registered runtime."""
        binding = self._binding(world_id)
        if self._ownership_store is None or binding.ownership_lease is None:
            raise MCPWorldError("RUNTIME_OWNERSHIP_UNCONFIGURED", "world has no configured ownership lease")
        if binding.ownership_heartbeat is None:
            binding.ownership_heartbeat = RuntimeOwnershipHeartbeat(
                self._ownership_store,
                binding.ownership_lease,
                ttl_seconds=self._ownership_ttl_seconds,
                interval_seconds=interval_seconds,
                on_error=on_error,
            )
        binding.ownership_heartbeat.start()
        return self._ownership_metadata(binding) or {}

    def stop_runtime_ownership_heartbeat(
        self,
        world_id: str,
        *,
        release: bool = False,
    ) -> dict[str, Any]:
        """Stop automatic renewal and optionally release the host lease."""
        binding = self._binding(world_id)
        heartbeat = binding.ownership_heartbeat
        if heartbeat is None:
            if release and binding.ownership_lease is not None and self._ownership_store is not None:
                self._ownership_store.release(binding.ownership_lease)
                binding.ownership_lease = None
            if release:
                return {"released": True, "heartbeat_running": False, "ownership": None}
            return self._ownership_metadata(binding) or {}
        heartbeat.stop(release=release)
        if release:
            binding.ownership_lease = None
            binding.ownership_heartbeat = None
            return {"released": True, "heartbeat_running": False, "ownership": None}
        return self._ownership_metadata(binding) or {}

    def close(self) -> None:
        """Stop host lease renewal and release all configured ownership leases."""
        with self._lock:
            world_ids = list(self._worlds)
        for world_id in world_ids:
            try:
                self.stop_runtime_ownership_heartbeat(world_id, release=True)
            except MCPWorldError:
                pass

    def _binding(self, world_id: str) -> WorldBinding:
        with self._lock:
            binding = self._worlds.get(str(world_id))
        if binding is None:
            raise MCPWorldError("WORLD_NOT_FOUND", f"unknown world: {world_id}")
        return binding

    @staticmethod
    def _ownership_metadata(binding: WorldBinding) -> dict[str, Any] | None:
        if binding.ownership_lease is None:
            return None
        metadata = binding.ownership_lease.safe_metadata()
        metadata["heartbeat_running"] = bool(
            binding.ownership_heartbeat is not None and binding.ownership_heartbeat.running
        )
        return metadata

    def _session_binding(self, session_id: str) -> tuple[WorldSession, WorldBinding]:
        with self._lock:
            session = self._sessions.get(str(session_id))
        if session is None:
            raise MCPWorldError("SESSION_INVALID", f"unknown session: {session_id}")
        binding = self._binding(session.world_id)
        if binding.runtime_instance_id != session.runtime_instance_id:
            raise MCPWorldError("RUNTIME_VERSION_MISMATCH", "session runtime instance is no longer active")
        if self._acl is not None:
            self._acl.authorize(session.user_id, session.world_id, session.actor_id, session.role)
        return session, binding
