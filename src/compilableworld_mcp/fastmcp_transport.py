"""Optional FastMCP v1.x context adapter without a hard SDK dependency.

FastMCP v1.x injects a Context object whose ``request_context.request`` carries
the underlying HTTP request. This adapter uses duck typing so the core package
can remain dependency-free and tests can exercise the boundary without
installing the optional SDK.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from .auth_pipeline import AuthenticatedRequest, RequestSecurityPipeline
from .http_transport import DEFAULT_SESSION_TOKEN_HEADER, HTTPRequestContextAdapter
from .request_security import RequestAuthContext, RequestSecurityError


FASTMCP_CONTEXT_TRANSPORT_CONTRACT = "compilableworld.mcp-fastmcp-context/v0.1"


def _request_id(context: Any) -> str:
    try:
        value = context.request_id
    except (AttributeError, ValueError, LookupError) as exc:
        raise RequestSecurityError(
            "INVALID_REQUEST_CONTEXT",
            "FastMCP context has no request_id",
        ) from exc
    return str(value)


def _peer(request: Any) -> str | None:
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return None if host is None else str(host)


class FastMCPContextAdapter:
    """Adapt an injected FastMCP v1.x Context into the local security boundary."""

    def __init__(
        self,
        pipeline: RequestSecurityPipeline,
        *,
        trusted_client_id: str,
        session_token_header: str = DEFAULT_SESSION_TOKEN_HEADER,
        stdio_credentials: Callable[[Any], tuple[str | None, str | None]] | None = None,
    ) -> None:
        self._http = HTTPRequestContextAdapter(
            pipeline,
            trusted_client_id=trusted_client_id,
            session_token_header=session_token_header,
        )
        self._stdio_credentials = stdio_credentials

    def _context_from_stdio(self, context: Any) -> RequestAuthContext:
        if self._stdio_credentials is None:
            raise RequestSecurityError(
                "TRANSPORT_REQUEST_MISSING",
                "FastMCP context has no HTTP request and no trusted stdio credential provider",
            )
        credentials = self._stdio_credentials(context)
        if not isinstance(credentials, tuple) or len(credentials) != 2:
            raise RequestSecurityError(
                "INVALID_REQUEST_CONTEXT",
                "stdio credential provider must return authorization and session token",
            )
        authorization, session_token = credentials
        return RequestAuthContext(
            request_id=_request_id(context),
            transport="stdio",
            client_id=self._http.trusted_client_id,
            authorization=authorization,
            session_token=session_token,
        )

    def context_from_fastmcp(self, context: Any) -> RequestAuthContext:
        """Extract only transport headers from an injected SDK Context.

        The SDK's convenience ``client_id`` property is deliberately ignored:
        in v1.x it is derived from MCP request metadata, which is not a trusted
        HTTP identity source.
        """
        try:
            request_context = getattr(context, "request_context", None)
        except (AttributeError, ValueError, LookupError) as exc:
            raise RequestSecurityError(
                "TRANSPORT_REQUEST_MISSING",
                "FastMCP context does not carry an HTTP request",
            ) from exc
        request = getattr(request_context, "request", None)
        if request is None:
            return self._context_from_stdio(context)
        headers = getattr(request, "headers", None)
        if headers is None:
            return self._context_from_stdio(context)
        return self._http.context_from_headers(
            headers,
            request_id=_request_id(context),
            peer=_peer(request),
        )

    @contextmanager
    def dispatch(
        self,
        context: Any,
        **pipeline_options: Any,
    ) -> Iterator[AuthenticatedRequest]:
        """Bind the extracted FastMCP request context for one tool dispatch."""
        request_context = self.context_from_fastmcp(context)
        with self._http.pipeline.dispatch(request_context, **pipeline_options) as request:
            yield request


__all__ = ["FASTMCP_CONTEXT_TRANSPORT_CONTRACT", "FastMCPContextAdapter"]
