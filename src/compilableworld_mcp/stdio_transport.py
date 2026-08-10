"""Trusted stdio request context adapter for local FastMCP hosts."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .auth_pipeline import AuthenticatedRequest, RequestSecurityPipeline
from .request_security import RequestAuthContext


STDIO_TRANSPORT_CONTRACT = "compilableworld.mcp-stdio-transport/v0.1"


class StdioContextAdapter:
    """Bind host-configured opaque credentials to one stdio request.

    Credentials come from the trusted local host process, never from MCP tool
    arguments. A host can provide a new session token per request when a
    session rotates.
    """

    def __init__(
        self,
        pipeline: RequestSecurityPipeline,
        *,
        trusted_client_id: str,
        authorization: str | None = None,
        session_token: str | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._trusted_client_id = str(trusted_client_id).strip()
        self._authorization = authorization
        self._session_token = session_token

    def context_from_credentials(
        self,
        request_id: str,
        *,
        authorization: str | None = None,
        session_token: str | None = None,
        peer: str | None = None,
    ) -> RequestAuthContext:
        return RequestAuthContext(
            request_id=request_id,
            transport="stdio",
            client_id=self._trusted_client_id,
            peer=peer,
            authorization=self._authorization if authorization is None else authorization,
            session_token=self._session_token if session_token is None else session_token,
        )

    @contextmanager
    def dispatch(
        self,
        request_id: str,
        *,
        authorization: str | None = None,
        session_token: str | None = None,
        peer: str | None = None,
        **pipeline_options: object,
    ) -> Iterator[AuthenticatedRequest]:
        context = self.context_from_credentials(
            request_id,
            authorization=authorization,
            session_token=session_token,
            peer=peer,
        )
        with self._pipeline.dispatch(context, **pipeline_options) as request:
            yield request


__all__ = ["STDIO_TRANSPORT_CONTRACT", "StdioContextAdapter"]
