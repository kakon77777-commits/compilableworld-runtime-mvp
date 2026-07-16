"""Fail-closed request authentication pipeline for MCP host adapters.

The pipeline is transport-neutral: a trusted HTTP, SSE, stdio, or FastMCP
host must first bind :class:`RequestAuthContext` and then call
``authenticate``.  Credentials are never accepted as tool arguments.  The
pipeline verifies the principal, optional session scope, principal role, and
optional world ACL before returning an immutable authenticated request.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from .acl import WorldACL
from .request_security import (
    MCP_REQUEST_SECURITY_CONTRACT,
    RequestAuthContext,
    RequestContextProvider,
    RequestSecurityError,
)
from .security import (
    BearerPrincipalResolver,
    SessionGrant,
    SessionTokenCodec,
    TrustedPrincipal,
)


MCP_AUTHENTICATED_REQUEST_CONTRACT = "compilableworld.mcp-authenticated-request/v0.1"


@dataclass(frozen=True, slots=True)
class AuthenticatedRequest:
    """Verified request identity and optional principal-bound session."""

    context: RequestAuthContext
    principal: TrustedPrincipal
    session: SessionGrant | None = None

    def safe_metadata(self) -> dict[str, Any]:
        """Return audit metadata without exposing token or authorization values."""
        payload = self.context.safe_metadata()
        payload.update(
            {
                "format": MCP_AUTHENTICATED_REQUEST_CONTRACT,
                "request_security_format": MCP_REQUEST_SECURITY_CONTRACT,
                "principal_user_id": self.principal.user_id,
                "principal_token_id": self.principal.token_id,
                "principal_roles": list(self.principal.roles),
                "session_id": None if self.session is None else self.session.session_id,
                "world_id": None if self.session is None else self.session.world_id,
                "actor_id": None if self.session is None else self.session.actor_id,
                "role": None if self.session is None else self.session.role,
            }
        )
        return payload


class RequestSecurityPipeline:
    """Authenticate one trusted Host-bound request before tool dispatch."""

    def __init__(
        self,
        principal_resolver: BearerPrincipalResolver,
        session_codec: SessionTokenCodec,
        *,
        context_provider: RequestContextProvider | None = None,
        acl: WorldACL | None = None,
    ) -> None:
        if not hasattr(principal_resolver, "resolve"):
            raise RequestSecurityError(
                "INVALID_PIPELINE",
                "principal resolver must provide resolve()",
            )
        self._principal_resolver = principal_resolver
        self._session_codec = session_codec
        self._context_provider = context_provider or RequestContextProvider()
        self._acl = acl

    @property
    def context_provider(self) -> RequestContextProvider:
        return self._context_provider

    def authenticate(
        self,
        *,
        require_session: bool = True,
        expected_world_id: str | None = None,
        expected_runtime_instance_id: str | None = None,
        expected_timeline_id: str | None = None,
        expected_actor_id: str | None = None,
        expected_role: str | None = None,
        now: int | None = None,
    ) -> AuthenticatedRequest:
        """Verify trusted context credentials and return the request identity.

        ``authorization`` and ``session_token`` are read only from the
        Host-bound context.  No user-controlled tool payload participates in
        authentication or authorization.
        """
        context = self._context_provider.require()
        principal = self._principal_resolver.resolve(
            context.require_authorization(),
            expected_client_id=context.client_id,
            now=now,
        )
        if not require_session:
            return AuthenticatedRequest(context=context, principal=principal)

        session = self._session_codec.verify(
            context.require_session_token(),
            principal=principal,
            expected_world_id=expected_world_id,
            expected_runtime_instance_id=expected_runtime_instance_id,
            expected_timeline_id=expected_timeline_id,
            expected_actor_id=expected_actor_id,
            expected_role=expected_role,
            now=now,
        )
        if session.role not in principal.roles:
            raise RequestSecurityError(
                "PRINCIPAL_ROLE_DENIED",
                "principal does not carry the session role",
            )
        if self._acl is not None:
            self._acl.authorize(principal.user_id, session.world_id, session.actor_id, session.role)
        return AuthenticatedRequest(context=context, principal=principal, session=session)

    @contextmanager
    def dispatch(
        self,
        context: RequestAuthContext,
        **kwargs: Any,
    ) -> Iterator[AuthenticatedRequest]:
        """Bind one Host context, authenticate, and always restore prior state."""
        token = self._context_provider.bind(context)
        try:
            yield self.authenticate(**kwargs)
        finally:
            self._context_provider.reset(token)


__all__ = [
    "AuthenticatedRequest",
    "MCP_AUTHENTICATED_REQUEST_CONTRACT",
    "RequestSecurityPipeline",
]
