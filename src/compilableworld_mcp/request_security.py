"""Transport-neutral request context boundary for the M9 security slice.

This module deliberately stops before token verification, session issuance,
rate limiting, or Runtime mutation.  It establishes the fail-closed context
boundary that a future HTTP/SSE/stdio host can bind before MCP dispatch.
Credentials are accepted only as opaque in-process values and are never
included in repr or safe metadata projections.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from .contracts import MCPWorldError


MCP_REQUEST_SECURITY_CONTRACT = "compilableworld.mcp-request-security/v0.1"


class RequestSecurityError(MCPWorldError):
    """Stable fail-closed error for the request-context boundary."""

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = MCP_REQUEST_SECURITY_CONTRACT
        return payload


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise RequestSecurityError(
            "INVALID_REQUEST_CONTEXT",
            f"request context requires a non-empty {field_name}",
        )
    return normalized


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class RequestAuthContext:
    """Trusted metadata and opaque credentials supplied by the Host.

    ``authorization`` and ``session_token`` are intentionally not exposed by
    ``repr``.  Callers must use :meth:`safe_metadata` for diagnostics; it only
    reports whether each credential is present, never its value.
    """

    request_id: str
    transport: str
    client_id: str
    peer: str | None = None
    authorization: str | None = field(default=None, repr=False)
    session_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _required(self.request_id, "request_id"))
        object.__setattr__(self, "transport", _required(self.transport, "transport").lower())
        object.__setattr__(self, "client_id", _required(self.client_id, "client_id"))
        object.__setattr__(self, "peer", _optional(self.peer))
        object.__setattr__(self, "authorization", _optional(self.authorization))
        object.__setattr__(self, "session_token", _optional(self.session_token))

    def require_authorization(self) -> str:
        if self.authorization is None:
            raise RequestSecurityError(
                "AUTHORIZATION_MISSING",
                "trusted request context has no authorization credential",
            )
        return self.authorization

    def require_session_token(self) -> str:
        if self.session_token is None:
            raise RequestSecurityError(
                "SESSION_TOKEN_MISSING",
                "trusted request context has no session token",
            )
        return self.session_token

    def safe_metadata(self) -> dict[str, Any]:
        """Return diagnostics that cannot disclose credential values."""
        return {
            "format": MCP_REQUEST_SECURITY_CONTRACT,
            "request_id": self.request_id,
            "transport": self.transport,
            "client_id": self.client_id,
            "peer": self.peer,
            "authorization_present": self.authorization is not None,
            "session_token_present": self.session_token is not None,
        }


class RequestContextProvider:
    """Context-local binding used by a trusted Host around one dispatch."""

    def __init__(self) -> None:
        self._current: ContextVar[RequestAuthContext | None] = ContextVar(
            "compilableworld_request_auth_context",
            default=None,
        )

    def bind(self, context: RequestAuthContext) -> Token[RequestAuthContext | None]:
        if not isinstance(context, RequestAuthContext):
            raise RequestSecurityError(
                "INVALID_REQUEST_CONTEXT",
                "request context provider accepts only RequestAuthContext",
            )
        return self._current.set(context)

    def reset(self, token: Token[RequestAuthContext | None]) -> None:
        self._current.reset(token)

    def current(self) -> RequestAuthContext | None:
        return self._current.get()

    def require(self) -> RequestAuthContext:
        context = self.current()
        if context is None:
            raise RequestSecurityError(
                "REQUEST_CONTEXT_MISSING",
                "trusted request context was not bound before MCP dispatch",
            )
        return context


__all__ = [
    "MCP_REQUEST_SECURITY_CONTRACT",
    "RequestAuthContext",
    "RequestContextProvider",
    "RequestSecurityError",
]
