"""Optional FastMCP tool facade for the authenticated read-only gateway."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .secure_gateway import SecureReadOnlyMCPGateway
from .server import MCPDependencyError


def build_secure_mcp_server(
    gateway: SecureReadOnlyMCPGateway,
    *,
    trusted_client_id: str,
    action_gateway: Any | None = None,
    fastmcp_options: Mapping[str, Any] | None = None,
    stdio_credentials: Any | None = None,
) -> Any:
    """Create a lazy FastMCP facade; importing this module needs no SDK."""
    try:
        from mcp.server.fastmcp import Context, FastMCP
        from mcp.types import CallToolResult, TextContent
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise MCPDependencyError(
            'MCP SDK is not installed; use pip install -e ".[mcp]"'
        ) from exc

    from .fastmcp_transport import FastMCPContextAdapter

    adapter = FastMCPContextAdapter(
        gateway.pipeline,
        trusted_client_id=trusted_client_id,
        stdio_credentials=stdio_credentials,
    )
    server_options = {"json_response": True}
    if fastmcp_options is not None:
        server_options.update(dict(fastmcp_options))
    mcp = FastMCP("CompilableWorld Secure Read-Only", **server_options)

    def context_for(ctx: Context):
        return adapter.context_from_fastmcp(ctx)

    def result(callable_, *args: Any, **kwargs: Any) -> Any:
        try:
            payload = callable_(*args, **kwargs)
            if isinstance(payload, dict) and "session_token" in payload:
                session_token = payload["session_token"]
                visible = dict(payload)
                visible.pop("session_token", None)
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=json.dumps(visible, ensure_ascii=False, sort_keys=True),
                        )
                    ],
                    structuredContent=visible,
                    meta={"compilableworld.session-token": session_token},
                )
            return payload
        except (MCPDependencyError, ValueError) as exc:
            if hasattr(exc, "to_dict"):
                return exc.to_dict()  # type: ignore[no-any-return]
            raise

    @mcp.tool()
    def list_worlds(ctx: Context) -> dict[str, Any]:
        return result(gateway.list_worlds, context_for(ctx))

    @mcp.tool()
    def open_world_session(
        ctx: Context,
        world_id: str,
        actor_id: str | None = None,
        role: str = "player",
        model_id: str | None = None,
    ) -> dict[str, Any]:
        return result(
            gateway.open_world_session,
            context_for(ctx),
            world_id,
            actor_id=actor_id,
            role=role,
            model_id=model_id,
        )

    @mcp.tool()
    def get_world_status(ctx: Context) -> dict[str, Any]:
        return result(gateway.get_world_status, context_for(ctx))

    @mcp.tool()
    def get_current_scene(ctx: Context) -> dict[str, Any]:
        return result(gateway.get_current_scene, context_for(ctx))

    @mcp.tool()
    def get_recent_events(
        ctx: Context,
        after_index: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        return result(
            gateway.get_recent_events,
            context_for(ctx),
            after_index=after_index,
            limit=limit,
        )

    @mcp.tool()
    def close_world_session(ctx: Context) -> dict[str, Any]:
        return result(gateway.close_world_session, context_for(ctx))

    @mcp.tool()
    def rotate_session(ctx: Context) -> dict[str, Any]:
        return result(gateway.rotate_session, context_for(ctx))

    if action_gateway is not None:
        @mcp.tool()
        def submit_action(
            ctx: Context,
            action: dict[str, Any],
            idempotency_key: str,
        ) -> dict[str, Any]:
            return result(
                action_gateway.submit_action,
                context_for(ctx),
                action,
                idempotency_key,
            )

    return mcp


def build_secure_mcp_streamable_http_app(
    gateway: SecureReadOnlyMCPGateway,
    *,
    trusted_client_id: str,
    action_gateway: Any | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    streamable_http_path: str = "/mcp",
    stateless_http: bool = False,
    json_response: bool = True,
) -> Any:
    """Build the official FastMCP v1.x Streamable HTTP ASGI app.

    TLS termination and process supervision stay with the chosen ASGI host.
    The local ASGI authentication middleware is placed outside FastMCP so
    Principal verification occurs before MCP protocol dispatch.
    """
    try:
        server = build_secure_mcp_server(
            gateway,
            trusted_client_id=trusted_client_id,
            action_gateway=action_gateway,
            fastmcp_options={
                "host": host,
                "port": int(port),
                "streamable_http_path": streamable_http_path,
                "stateless_http": bool(stateless_http),
                "json_response": bool(json_response),
            },
        )
        app = server.streamable_http_app()
    except AttributeError as exc:  # pragma: no cover - SDK version dependent
        raise MCPDependencyError(
            "installed MCP SDK does not expose FastMCP.streamable_http_app()"
        ) from exc

    from .asgi_middleware import ASGIAuthMiddleware
    from .http_transport import HTTPRequestContextAdapter

    adapter = HTTPRequestContextAdapter(
        gateway.pipeline,
        trusted_client_id=trusted_client_id,
    )
    return ASGIAuthMiddleware(
        app,
        trusted_client_id=trusted_client_id,
        adapter=adapter,
    )


__all__ = ["build_secure_mcp_server", "build_secure_mcp_streamable_http_app"]
