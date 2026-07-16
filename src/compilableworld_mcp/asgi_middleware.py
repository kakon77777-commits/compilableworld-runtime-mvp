"""ASGI authentication middleware for a real HTTP host boundary."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from uuid import uuid4

from .http_transport import HTTPRequestContextAdapter
from .request_security import RequestSecurityError


ASGI_MIDDLEWARE_CONTRACT = "compilableworld.mcp-asgi-auth/v0.1"
ASGIApp = Callable[[Mapping[str, Any], Callable[..., Awaitable[dict[str, Any]]], Callable[..., Awaitable[None]]], Awaitable[None]]


def _scope_headers(scope: Mapping[str, Any]) -> dict[str, str]:
    raw_headers = scope.get("headers", ())
    if not isinstance(raw_headers, Sequence):
        raise RequestSecurityError("TRANSPORT_HEADERS_MISSING", "ASGI scope has no HTTP headers")
    headers: dict[str, str] = {}
    for raw_name, raw_value in raw_headers:
        if isinstance(raw_name, bytes):
            name = raw_name.decode("latin-1")
        else:
            name = str(raw_name)
        if isinstance(raw_value, bytes):
            value = raw_value.decode("latin-1")
        else:
            value = str(raw_value)
        lowered = name.lower()
        headers[lowered] = f"{headers[lowered]}, {value}" if lowered in headers else value
    return headers


def _peer(scope: Mapping[str, Any]) -> str | None:
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return None


class ASGIAuthMiddleware:
    """Authenticate the Principal at HTTP ingress and expose safe context state.

    Session and role checks remain owned by the Secure Gateway, because the
    same HTTP request can invoke either a sessionless or session-bound tool.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_client_id: str | Callable[[Mapping[str, Any]], str],
        adapter: HTTPRequestContextAdapter,
        request_id_header: str = "x-request-id",
    ) -> None:
        if not callable(app):
            raise RequestSecurityError("INVALID_ASGI_MIDDLEWARE", "ASGI app must be callable")
        if not callable(trusted_client_id) and not str(trusted_client_id).strip():
            raise RequestSecurityError("INVALID_ASGI_MIDDLEWARE", "trusted client id must be non-empty")
        self.app = app
        self.adapter = adapter
        self.trusted_client_id = trusted_client_id
        self.request_id_header = str(request_id_header).strip().lower() or "x-request-id"

    def context_from_scope(self, scope: Mapping[str, Any]):
        headers = _scope_headers(scope)
        client = self.trusted_client_id(scope) if callable(self.trusted_client_id) else self.trusted_client_id
        request_id = headers.get(self.request_id_header) or f"http_{uuid4().hex}"
        return HTTPRequestContextAdapter(
            self.adapter.pipeline,
            trusted_client_id=client,
            session_token_header=self.adapter.session_token_header,
        ).context_from_headers(headers, request_id=request_id, peer=_peer(scope))

    async def __call__(self, scope: Mapping[str, Any], receive: Callable[..., Awaitable[dict[str, Any]]], send: Callable[..., Awaitable[None]]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        try:
            context = self.context_from_scope(scope)
            state = dict(scope.get("state") or {})
            state["compilableworld.request_auth_context"] = context
            forwarded_scope = dict(scope)
            forwarded_scope["state"] = state
            with self.adapter.pipeline.dispatch(context, require_session=False):
                await self.app(forwarded_scope, receive, send)
        except RequestSecurityError as exc:
            await self._send_error(send, exc)

    @staticmethod
    async def _send_error(send: Callable[..., Awaitable[None]], error: RequestSecurityError) -> None:
        code = error.code
        status = 429 if code == "RATE_LIMITED" else 403 if code in {"PRINCIPAL_ROLE_DENIED", "ACL_DENIED", "PERMISSION_DENIED"} else 401
        body = json.dumps(
            {"format": ASGI_MIDDLEWARE_CONTRACT, "status": "error", **error.to_dict()},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))],
        })
        await send({"type": "http.response.body", "body": body})


__all__ = ["ASGI_MIDDLEWARE_CONTRACT", "ASGIAuthMiddleware"]
