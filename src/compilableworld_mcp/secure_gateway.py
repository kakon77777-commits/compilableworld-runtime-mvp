"""Authenticated read-only MCP facade with server-side session issuance."""

from __future__ import annotations

from typing import Any, Mapping

from .audit import build_audit_envelope
from .audit_store import AuditStore, AuditStoreError
from .auth_pipeline import RequestSecurityPipeline
from .contracts import MCPWorldError
from .request_security import RequestAuthContext, RequestSecurityError
from .security import SessionTokenCodec
from .session_store import SessionLifecycleStore
from .service import ReadOnlyWorldService


SECURE_READONLY_GATEWAY_CONTRACT = "compilableworld.mcp-secure-readonly-gateway/v0.1"
DEFAULT_TIMELINE_ID = "main"


class SecureReadOnlyMCPGateway:
    """Authenticate transport context before delegating to the read-only core."""

    def __init__(
        self,
        service: ReadOnlyWorldService,
        pipeline: RequestSecurityPipeline,
        session_codec: SessionTokenCodec,
        *,
        timeline_id: str = DEFAULT_TIMELINE_ID,
        session_ttl_seconds: int = 300,
        session_store: SessionLifecycleStore | None = None,
        audit_store: AuditStore | None = None,
    ) -> None:
        timeline = str(timeline_id).strip()
        if not timeline:
            raise RequestSecurityError("INVALID_TOKEN_POLICY", "timeline_id must be non-empty")
        if int(session_ttl_seconds) <= 0:
            raise RequestSecurityError("INVALID_TOKEN_POLICY", "session TTL must be positive")
        self.service = service
        self.pipeline = pipeline
        self.session_codec = session_codec
        self.timeline_id = timeline
        self.session_ttl_seconds = int(session_ttl_seconds)
        self.session_store = session_store or SessionLifecycleStore()
        self.audit_store = audit_store

    def list_worlds(self, context: RequestAuthContext, *, now: int | None = None) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            return self._with_audit(request, "world.list", self.service.list_worlds(), now=now)

    def rehydrate_sessions(self, *, now: int | None = None) -> dict[str, Any]:
        """Restore active sessions after the host has re-registered runtimes."""
        return self.service.rehydrate_sessions(self.session_store.active_records(now=now), now=now)

    def open_world_session(
        self,
        context: RequestAuthContext,
        world_id: str,
        *,
        actor_id: str | None = None,
        role: str = "player",
        model_id: str | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            if role not in request.principal.roles:
                raise RequestSecurityError(
                    "PRINCIPAL_ROLE_DENIED",
                    "principal does not carry the requested session role",
                )
            opened = self.service.open_world_session(
                world_id,
                actor_id=actor_id,
                role=role,
                client_id=request.principal.client_id,
                user_id=request.principal.user_id,
                model_id=model_id,
            )
            session = opened["session"]
            session_token = self.session_codec.issue(
                principal=request.principal,
                session_id=session["session_id"],
                world_id=session["world_id"],
                runtime_instance_id=session["runtime_instance_id"],
                timeline_id=self.timeline_id,
                actor_id=session["actor_id"],
                role=session["role"],
                ttl_seconds=self.session_ttl_seconds,
                now=now,
            )
            session_grant = self.session_codec.verify(
                session_token,
                principal=request.principal,
                now=now,
            )
            self.session_store.register(
                session_grant,
                model_id=session.get("model_id"),
                now=now,
            )
            result = {
                "format": SECURE_READONLY_GATEWAY_CONTRACT,
                "read_only": True,
                "world_state_changed": False,
                "session": session,
                "session_token": session_token,
            }
            return self._with_audit(request, "session.open", result, scope=session, now=now)

    def get_world_status(
        self,
        context: RequestAuthContext,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, now=now) as request:
            self._require_live_session(request.session, now=now)
            return self._with_audit(
                request,
                "world.status",
                self.service.get_world_status(request.session.session_id),
                now=now,
            )

    def get_current_scene(
        self,
        context: RequestAuthContext,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, now=now) as request:
            self._require_live_session(request.session, now=now)
            return self._with_audit(
                request,
                "world.scene",
                self.service.get_current_scene(request.session.session_id),
                now=now,
            )

    def get_recent_events(
        self,
        context: RequestAuthContext,
        *,
        after_index: int = 0,
        limit: int = 20,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, now=now) as request:
            self._require_live_session(request.session, now=now)
            return self._with_audit(
                request,
                "world.events",
                self.service.get_recent_events(
                    request.session.session_id,
                    after_index=after_index,
                    limit=limit,
                ),
                now=now,
            )

    def close_world_session(
        self,
        context: RequestAuthContext,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, now=now) as request:
            self._require_live_session(request.session, now=now)
            closed = self.service.close_world_session(request.session.session_id)
            self.session_store.close(request.session.session_id, now=now)
            return self._with_audit(request, "session.close", closed, now=now)

    def rotate_session(
        self,
        context: RequestAuthContext,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Rotate the active server-side session token without changing world state."""
        with self.pipeline.dispatch(context, now=now) as request:
            self._require_live_session(request.session, now=now)
            if request.session is None:  # pragma: no cover - pipeline guarantees this
                raise RequestSecurityError("SESSION_TOKEN_MISSING", "authenticated request has no session")
            live = self.service.session_for_security(request.session.session_id)
            new_token = self.session_codec.issue(
                principal=request.principal,
                session_id=request.session.session_id,
                world_id=request.session.world_id,
                runtime_instance_id=request.session.runtime_instance_id,
                timeline_id=request.session.timeline_id,
                actor_id=request.session.actor_id,
                role=request.session.role,
                ttl_seconds=self.session_ttl_seconds,
                now=now,
            )
            new_grant = self.session_codec.verify(
                new_token,
                principal=request.principal,
                now=now,
            )
            self.session_store.rotate(request.session, new_grant, now=now)
            result = {
                "format": SECURE_READONLY_GATEWAY_CONTRACT,
                "read_only": True,
                "world_state_changed": False,
                "session": live.to_dict(),
                "session_token": new_token,
                "rotated": True,
            }
            return self._with_audit(request, "session.rotate", result, now=now)

    def _with_audit(
        self,
        request: Any,
        operation: str,
        result: dict[str, Any],
        *,
        scope: Mapping[str, Any] | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        payload = dict(result)
        payload["audit"] = build_audit_envelope(
            request,
            operation,
            outcome="success",
            world_state_changed=bool(payload.get("world_state_changed", False)),
            scope=scope,
            now=now,
        )
        self._persist_audit(payload, now=now)
        return payload

    def _persist_audit(self, payload: dict[str, Any], *, now: int | None = None) -> None:
        if self.audit_store is None:
            return
        try:
            record = self.audit_store.append(payload["audit"], now=now)
        except AuditStoreError as exc:
            payload["audit_persisted"] = False
            payload["audit_error_code"] = exc.code
            return
        payload["audit_persisted"] = True
        payload["audit_id"] = record.audit_id

    def _require_live_session(self, session: Any, *, now: int | None = None) -> None:
        if session is None:  # pragma: no cover - pipeline guarantees this
            raise RequestSecurityError("SESSION_TOKEN_MISSING", "authenticated request has no session")
        self.session_store.require_active(session, now=now)
        live = self.service.session_for_security(session.session_id)
        expected = {
            "user_id": session.user_id,
            "world_id": session.world_id,
            "runtime_instance_id": session.runtime_instance_id,
            "actor_id": session.actor_id,
            "role": session.role,
            "client_id": session.client_id,
        }
        actual = {key: getattr(live, key) for key in expected}
        if actual != expected:
            raise MCPWorldError(
                "SESSION_SCOPE_MISMATCH",
                "session token does not match the live server session",
            )


__all__ = [
    "DEFAULT_TIMELINE_ID",
    "SECURE_READONLY_GATEWAY_CONTRACT",
    "SecureReadOnlyMCPGateway",
]
