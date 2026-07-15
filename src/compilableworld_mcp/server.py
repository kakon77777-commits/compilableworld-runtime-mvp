from __future__ import annotations

import argparse
import json
from typing import Any, Sequence

from .contracts import MCPWorldError
from .service import ReadOnlyWorldService


class MCPDependencyError(RuntimeError):
    pass


def build_mcp_server(service: ReadOnlyWorldService) -> Any:
    """Create the optional FastMCP v1.x transport adapter.

    Import is intentionally lazy so the CompilableWorld runtime remains zero
    dependency unless users install ``compilableworld-runtime[mcp]``.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise MCPDependencyError(
            'MCP SDK is not installed; use pip install -e ".[mcp]"'
        ) from exc

    mcp = FastMCP("CompilableWorld Read-Only", json_response=True)

    def result(callable_, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return callable_(*args, **kwargs)
        except MCPWorldError as exc:
            return exc.to_dict()

    @mcp.tool()
    def list_worlds() -> dict[str, Any]:
        """List world packages registered in this MCP server process."""
        return service.list_worlds()

    @mcp.tool()
    def open_world_session(
        world_id: str,
        actor_id: str | None = None,
        role: str = "player",
        client_id: str = "mcp-client",
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """Open a read-only session bound to a world and actor."""
        return result(
            service.open_world_session,
            world_id,
            actor_id=actor_id,
            role=role,
            client_id=client_id,
            model_id=model_id,
        )

    @mcp.tool()
    def get_world_status(session_id: str) -> dict[str, Any]:
        """Return versioned world/runtime status without changing world state."""
        return result(service.get_world_status, session_id)

    @mcp.tool()
    def get_current_scene(session_id: str) -> dict[str, Any]:
        """Return the actor-filtered current scene projection."""
        return result(service.get_current_scene, session_id)

    @mcp.tool()
    def get_recent_events(session_id: str, after_index: int = 0, limit: int = 20) -> dict[str, Any]:
        """Return visible committed events in runtime order using a raw cursor."""
        return result(
            service.get_recent_events,
            session_id,
            after_index=after_index,
            limit=limit,
        )

    @mcp.tool()
    def close_world_session(session_id: str) -> dict[str, Any]:
        """Close MCP session metadata without stopping or mutating the world."""
        return result(service.close_world_session, session_id)

    return mcp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CompilableWorld read-only MCP server")
    parser.add_argument("packages", nargs="+", help="compiled world.package.json files")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="FastMCP v1.x transport",
    )
    parser.add_argument("--event-log", help="optional event log path for a single package")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.event_log and len(args.packages) != 1:
        raise SystemExit("--event-log can only be used with one package")
    service = ReadOnlyWorldService()
    for package in args.packages:
        service.register_package(package, event_log_path=args.event_log)
    try:
        server = build_mcp_server(service)
    except MCPDependencyError as exc:
        print(f"ERROR: {exc}")
        return 2
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
