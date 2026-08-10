"""HTTP transport boundary for the MCP request-security pipeline.

This adapter intentionally does not trust a client-supplied client id. The
HTTP host supplies that value from its configured connection or identity
mapping, while this module only extracts opaque credentials from headers.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from .auth_pipeline import AuthenticatedRequest, RequestSecurityPipeline
from .request_security import RequestAuthContext, RequestSecurityError


HTTP_TRANSPORT_CONTRACT = "compilableworld.mcp-http-transport/v0.1"
DEFAULT_SESSION_TOKEN_HEADER = "X-CompilableWorld-Session"


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Read a header case-insensitively without logging or copying secrets."""
    direct = headers.get(name)
    if direct is not None:
        return str(direct)
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return None


class HTTPRequestContextAdapter:
    """Convert trusted HTTP request metadata into one MCP request context."""

    def __init__(
        self,
        pipeline: RequestSecurityPipeline,
        *,
        trusted_client_id: str,
        session_token_header: str = DEFAULT_SESSION_TOKEN_HEADER,
    ) -> None:
        client_id = str(trusted_client_id).strip()
        if not client_id:
            raise RequestSecurityError(
                "INVALID_REQUEST_CONTEXT",
                "HTTP adapter requires a trusted client_id from the Host",
            )
        header_name = str(session_token_header).strip()
        if not header_name:
            raise RequestSecurityError(
                "INVALID_REQUEST_CONTEXT",
                "HTTP adapter requires a session token header name",
            )
        self._pipeline = pipeline
        self._trusted_client_id = client_id
        self._session_token_header = header_name

    @property
    def pipeline(self) -> RequestSecurityPipeline:
        return self._pipeline

    @property
    def session_token_header(self) -> str:
        return self._session_token_header

    @property
    def trusted_client_id(self) -> str:
        return self._trusted_client_id

    def context_from_headers(
        self,
        headers: Mapping[str, str],
        *,
        request_id: str,
        peer: str | None = None,
    ) -> RequestAuthContext:
        """Extract opaque credentials; verification happens in the pipeline."""
        if not hasattr(headers, "get") or not hasattr(headers, "items"):
            raise RequestSecurityError(
                "INVALID_REQUEST_CONTEXT",
                "HTTP headers must be a mapping",
            )
        return RequestAuthContext(
            request_id=request_id,
            transport="http",
            client_id=self._trusted_client_id,
            peer=peer,
            authorization=_header(headers, "Authorization"),
            session_token=_header(headers, self._session_token_header),
        )

    @contextmanager
    def dispatch(
        self,
        headers: Mapping[str, str],
        *,
        request_id: str,
        peer: str | None = None,
        **pipeline_options: Any,
    ) -> Iterator[AuthenticatedRequest]:
        """Build a context and run the authenticated dispatch boundary."""
        context = self.context_from_headers(headers, request_id=request_id, peer=peer)
        with self._pipeline.dispatch(context, **pipeline_options) as request:
            yield request


__all__ = [
    "DEFAULT_SESSION_TOKEN_HEADER",
    "HTTP_REQUEST_CONTEXT_CONTRACT",
    "HTTPRequestContextAdapter",
]


# Keep the public name explicit while preserving the conventional all-caps
# contract constant expected by callers.
HTTP_REQUEST_CONTEXT_CONTRACT = HTTP_TRANSPORT_CONTRACT
