"""Authenticated Runtime ownership coordination control plane."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .auth_pipeline import AuthenticatedRequest, RequestSecurityPipeline
from .request_security import RequestAuthContext, RequestSecurityError
from .runtime_ownership import RuntimeLeaseGrant, RuntimeOwnershipError, RuntimeOwnershipLeaseStore
from .runtime_quorum import RuntimeQuorumError, RuntimeQuorumGate, RuntimeQuorumTerm


RUNTIME_COORDINATION_CONTRACT = "compilableworld.mcp-runtime-coordination/v0.1"
RUNTIME_COORDINATION_PATH_PREFIX = "/v1/runtime-ownership"
RUNTIME_COORDINATION_LEADER_WORLD_ID = "__compilableworld_coordination__"
RUNTIME_COORDINATION_LEADER_INSTANCE_ID = "leader"
ASGIApp = Callable[
    [Mapping[str, Any], Callable[..., Awaitable[dict[str, Any]]], Callable[..., Awaitable[None]]],
    Awaitable[None],
]


def _required(value: Any, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", f"{field_name} must be non-empty")
    return normalized


class RuntimeCoordinationGateway:
    """Bind ownership operations to an authenticated admin Principal."""

    def __init__(
        self,
        store: RuntimeOwnershipLeaseStore,
        pipeline: RequestSecurityPipeline,
        *,
        required_role: str = "admin",
        max_ttl_seconds: int = 3600,
        quorum_gate: RuntimeQuorumGate | None = None,
    ) -> None:
        ttl = int(max_ttl_seconds)
        if ttl <= 0:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "maximum lease TTL must be positive")
        role = _required(required_role, "required_role")
        self.store = store
        self.pipeline = pipeline
        self.required_role = role
        self.max_ttl_seconds = ttl
        self.quorum_gate = quorum_gate

    def acquire(
        self,
        context: RequestAuthContext,
        world_id: str,
        runtime_instance_id: str,
        *,
        ttl_seconds: int = 30,
        recover: bool = False,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            owner_id = self._authorize_host(request)
            ttl = self._ttl(ttl_seconds)
            acquire = self.store.recover if recover else self.store.acquire
            lease = acquire(
                world_id,
                runtime_instance_id,
                owner_id,
                ttl_seconds=ttl,
                now=now,
            )
            return self._projection("recover" if recover else "acquire", lease)

    def acquire_leader(
        self,
        context: RequestAuthContext,
        *,
        ttl_seconds: int = 30,
        recover: bool = False,
        term: int | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Acquire the single coordinator leader lease for this store.

        This is a single-writer lease with fencing, not a quorum consensus
        protocol.  Deployments that need quorum semantics must provide that
        authority behind the same host boundary.
        """
        if self.quorum_gate is not None:
            with self.pipeline.dispatch(context, require_session=False, now=now) as request:
                owner_id = self._authorize_host(request)
                if term is None:
                    raise RuntimeOwnershipError("QUORUM_REQUIRED", "leader acquisition requires a quorum term")
                self._require_leader_quorum(self.quorum_gate, term, owner_id)
        return self.acquire(
            context,
            RUNTIME_COORDINATION_LEADER_WORLD_ID,
            RUNTIME_COORDINATION_LEADER_INSTANCE_ID,
            ttl_seconds=ttl_seconds,
            recover=recover,
            now=now,
        )

    def request_leader_term(
        self,
        context: RequestAuthContext,
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            owner_id = self._authorize_host(request)
            gate = self._require_quorum_gate()
            try:
                quorum = gate.open_term(owner_id, now=now)
            except RuntimeQuorumError as exc:
                raise self._translate_quorum_error(exc) from exc
            return self._quorum_projection("leader_term", quorum)

    def record_leader_vote(
        self,
        context: RequestAuthContext,
        term: int,
        *,
        candidate_id: str | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            member_id = self._authorize_host(request)
            gate = self._require_quorum_gate()
            try:
                quorum = gate.record_vote(term, member_id, candidate_id=candidate_id, now=now)
            except RuntimeQuorumError as exc:
                raise self._translate_quorum_error(exc) from exc
            return self._quorum_projection("leader_vote", quorum)

    def require_leader_quorum(
        self,
        context: RequestAuthContext,
        term: int,
        *,
        candidate_id: str | None = None,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            owner_id = self._authorize_host(request)
            gate = self._require_quorum_gate()
            quorum = self._require_leader_quorum(gate, term, candidate_id or owner_id)
            return self._quorum_projection("leader_quorum", quorum)

    def renew(
        self,
        context: RequestAuthContext,
        lease_payload: Mapping[str, Any],
        *,
        ttl_seconds: int = 30,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            owner_id = self._authorize_host(request)
            lease = self._grant_from_payload(lease_payload, owner_id)
            renewed = self.store.renew(lease, ttl_seconds=self._ttl(ttl_seconds), now=now)
            return self._projection("renew", renewed)

    def renew_leader(
        self,
        context: RequestAuthContext,
        lease_payload: Mapping[str, Any],
        *,
        ttl_seconds: int = 30,
        now: int | None = None,
    ) -> dict[str, Any]:
        self._assert_leader_payload(lease_payload)
        result = self.renew(context, lease_payload, ttl_seconds=ttl_seconds, now=now)
        result["operation"] = "leader_renew"
        return result

    def release(
        self,
        context: RequestAuthContext,
        lease_payload: Mapping[str, Any],
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        with self.pipeline.dispatch(context, require_session=False, now=now) as request:
            owner_id = self._authorize_host(request)
            lease = self._grant_from_payload(lease_payload, owner_id)
            released = self.store.release(lease, now=now)
            return {
                "format": RUNTIME_COORDINATION_CONTRACT,
                "operation": "release",
                "released": True,
                "lease": released.safe_metadata(),
                "world_state_changed": False,
            }

    def release_leader(
        self,
        context: RequestAuthContext,
        lease_payload: Mapping[str, Any],
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        self._assert_leader_payload(lease_payload)
        result = self.release(context, lease_payload, now=now)
        result["operation"] = "leader_release"
        return result

    def _authorize_host(self, request: AuthenticatedRequest) -> str:
        if self.required_role not in request.principal.roles:
            raise RequestSecurityError(
                "PRINCIPAL_ROLE_DENIED",
                f"runtime coordination requires the {self.required_role} role",
            )
        return _required(request.principal.user_id, "owner_id")

    def _ttl(self, value: int) -> int:
        ttl = int(value)
        if ttl <= 0 or ttl > self.max_ttl_seconds:
            raise RuntimeOwnershipError(
                "INVALID_RUNTIME_OWNERSHIP",
                f"lease TTL must be between 1 and {self.max_ttl_seconds} seconds",
            )
        return ttl

    def _require_quorum_gate(self) -> RuntimeQuorumGate:
        if self.quorum_gate is None:
            raise RuntimeOwnershipError("QUORUM_NOT_CONFIGURED", "runtime coordination has no quorum gate")
        return self.quorum_gate

    @staticmethod
    def _translate_quorum_error(error: RuntimeQuorumError) -> RuntimeOwnershipError:
        return RuntimeOwnershipError(error.code, error.message, retryable=error.retryable)

    @classmethod
    def _require_leader_quorum(
        cls,
        gate: RuntimeQuorumGate,
        term: int,
        candidate_id: str,
    ) -> RuntimeQuorumTerm:
        try:
            return gate.require_quorum(term, candidate_id=candidate_id)
        except RuntimeQuorumError as exc:
            raise cls._translate_quorum_error(exc) from exc

    @staticmethod
    def _grant_from_payload(payload: Mapping[str, Any], owner_id: str) -> RuntimeLeaseGrant:
        if not isinstance(payload, Mapping):
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "lease must be an object")
        try:
            return RuntimeLeaseGrant(
                _required(payload["world_id"], "world_id"),
                _required(payload["runtime_instance_id"], "runtime_instance_id"),
                owner_id,
                _required(payload["lease_id"], "lease_id"),
                int(payload["issued_at"]),
                int(payload["expires_at"]),
                int(payload["fencing_token"]),
            )
        except KeyError as exc:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", f"lease field is missing: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "lease timestamps are invalid") from exc

    @staticmethod
    def _assert_leader_payload(payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "leader lease must be an object")
        if payload.get("world_id") != RUNTIME_COORDINATION_LEADER_WORLD_ID:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "lease is not the coordination leader lease")
        if payload.get("runtime_instance_id") != RUNTIME_COORDINATION_LEADER_INSTANCE_ID:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "lease is not the coordination leader lease")

    @staticmethod
    def _projection(operation: str, lease: RuntimeLeaseGrant) -> dict[str, Any]:
        return {
            "format": RUNTIME_COORDINATION_CONTRACT,
            "operation": operation,
            "world_state_changed": False,
            "lease": {
                "world_id": lease.world_id,
                "runtime_instance_id": lease.runtime_instance_id,
                "owner_id": lease.owner_id,
                "lease_id": lease.lease_id,
                "issued_at": lease.issued_at,
                "expires_at": lease.expires_at,
                "fencing_token": lease.fencing_token,
            },
            "safe_metadata": lease.safe_metadata(),
        }

    @staticmethod
    def _quorum_projection(operation: str, quorum: RuntimeQuorumTerm) -> dict[str, Any]:
        return {
            "format": RUNTIME_COORDINATION_CONTRACT,
            "operation": operation,
            "world_state_changed": False,
            "quorum": quorum.to_dict(),
        }


class RuntimeCoordinationASGIApp:
    """Small HTTP control plane intended to sit behind ASGIAuthMiddleware."""

    def __init__(self, gateway: RuntimeCoordinationGateway, *, max_body_bytes: int = 65536) -> None:
        if int(max_body_bytes) <= 0:
            raise RuntimeOwnershipError("INVALID_RUNTIME_OWNERSHIP", "coordination body limit must be positive")
        self.gateway = gateway
        self.max_body_bytes = int(max_body_bytes)

    async def __call__(
        self,
        scope: Mapping[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self._send_json(send, 404, {"format": RUNTIME_COORDINATION_CONTRACT, "error_code": "NOT_FOUND"})
            return
        try:
            if str(scope.get("method", "")).upper() != "POST":
                raise RuntimeOwnershipError("METHOD_NOT_ALLOWED", "coordination endpoints require POST")
            context = self._context(scope)
            payload = await self._read_json(receive)
            path = str(scope.get("path", "")).rstrip("/")
            result = self._dispatch(context, path, payload)
            await self._send_json(send, 200, result)
        except (RequestSecurityError, RuntimeOwnershipError) as exc:
            await self._send_json(send, self._status_for(exc), {"format": RUNTIME_COORDINATION_CONTRACT, **exc.to_dict()})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            error = RuntimeOwnershipError("INVALID_COORDINATION_REQUEST", "coordination request JSON is invalid")
            await self._send_json(send, 400, {"format": RUNTIME_COORDINATION_CONTRACT, **error.to_dict()})

    def _dispatch(
        self,
        context: RequestAuthContext,
        path: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/acquire":
            return self.gateway.acquire(
                context,
                payload["world_id"],
                payload["runtime_instance_id"],
                ttl_seconds=payload.get("ttl_seconds", 30),
                now=payload.get("now"),
            )
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/recover":
            return self.gateway.acquire(
                context,
                payload["world_id"],
                payload["runtime_instance_id"],
                ttl_seconds=payload.get("ttl_seconds", 30),
                recover=True,
                now=payload.get("now"),
            )
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/renew":
            return self.gateway.renew(
                context,
                payload["lease"],
                ttl_seconds=payload.get("ttl_seconds", 30),
                now=payload.get("now"),
            )
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/release":
            return self.gateway.release(context, payload["lease"], now=payload.get("now"))
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/leader/acquire":
            return self.gateway.acquire_leader(
                context,
                ttl_seconds=payload.get("ttl_seconds", 30),
                term=payload.get("term"),
                now=payload.get("now"),
            )
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/leader/recover":
            return self.gateway.acquire_leader(
                context,
                ttl_seconds=payload.get("ttl_seconds", 30),
                recover=True,
                term=payload.get("term"),
                now=payload.get("now"),
            )
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/leader/renew":
            return self.gateway.renew_leader(
                context,
                payload["lease"],
                ttl_seconds=payload.get("ttl_seconds", 30),
                now=payload.get("now"),
            )
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/leader/release":
            return self.gateway.release_leader(context, payload["lease"], now=payload.get("now"))
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/leader/term":
            return self.gateway.request_leader_term(context, now=payload.get("now"))
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/leader/vote":
            return self.gateway.record_leader_vote(
                context,
                payload["term"],
                candidate_id=payload.get("candidate_id"),
                now=payload.get("now"),
            )
        if path == f"{RUNTIME_COORDINATION_PATH_PREFIX}/leader/quorum":
            return self.gateway.require_leader_quorum(
                context,
                payload["term"],
                candidate_id=payload.get("candidate_id"),
                now=payload.get("now"),
            )
        raise RuntimeOwnershipError("NOT_FOUND", "unknown runtime coordination endpoint")

    @staticmethod
    def _context(scope: Mapping[str, Any]) -> RequestAuthContext:
        state = scope.get("state")
        context = state.get("compilableworld.request_auth_context") if isinstance(state, Mapping) else None
        if not isinstance(context, RequestAuthContext):
            raise RequestSecurityError(
                "REQUEST_CONTEXT_MISSING",
                "coordination app must be wrapped by a trusted auth middleware",
            )
        return context

    async def _read_json(self, receive: Callable[..., Awaitable[dict[str, Any]]]) -> Mapping[str, Any]:
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            chunk = message.get("body", b"")
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            if not isinstance(chunk, bytes):
                raise RuntimeOwnershipError("INVALID_COORDINATION_REQUEST", "request body is invalid")
            size += len(chunk)
            if size > self.max_body_bytes:
                raise RuntimeOwnershipError("COORDINATION_BODY_TOO_LARGE", "coordination request body is too large")
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        payload = json.loads(b"".join(chunks).decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise RuntimeOwnershipError("INVALID_COORDINATION_REQUEST", "coordination payload must be an object")
        return payload

    @staticmethod
    def _status_for(error: RuntimeOwnershipError | RequestSecurityError) -> int:
        if isinstance(error, RequestSecurityError):
            if error.code in {"PRINCIPAL_ROLE_DENIED", "PERMISSION_DENIED"}:
                return 403
            return 401
        if error.code in {
            "RUNTIME_BUSY",
            "RUNTIME_OWNERSHIP_MISMATCH",
            "RUNTIME_LEASE_EXPIRED",
            "RUNTIME_LEASE_RELEASED",
            "QUORUM_NOT_REACHED",
            "QUORUM_TERM_MISSING",
            "QUORUM_CANDIDATE_MISMATCH",
            "QUORUM_MEMBERSHIP_MISMATCH",
        }:
            return 409
        if error.code == "METHOD_NOT_ALLOWED":
            return 405
        if error.code == "NOT_FOUND":
            return 404
        return 400

    @staticmethod
    async def _send_json(send: Callable[..., Awaitable[None]], status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": int(status),
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))],
        })
        await send({"type": "http.response.body", "body": body})


def build_runtime_coordination_asgi_app(gateway: RuntimeCoordinationGateway) -> RuntimeCoordinationASGIApp:
    return RuntimeCoordinationASGIApp(gateway)


__all__ = [
    "RUNTIME_COORDINATION_CONTRACT",
    "RUNTIME_COORDINATION_LEADER_INSTANCE_ID",
    "RUNTIME_COORDINATION_LEADER_WORLD_ID",
    "RUNTIME_COORDINATION_PATH_PREFIX",
    "RuntimeCoordinationASGIApp",
    "RuntimeCoordinationGateway",
    "build_runtime_coordination_asgi_app",
]
