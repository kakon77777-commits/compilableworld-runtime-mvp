from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .contracts import MCPWorldError
from .runtime_bindings import RuntimeBindingRecord, RuntimeBindingStore
from .runtime_ownership import RuntimeOwnershipLeaseStore
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
    parser.add_argument("packages", nargs="*", help="compiled world.package.json files")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="FastMCP v1.x transport",
    )
    parser.add_argument("--event-log", help="optional event log path for a single package")
    parser.add_argument("--snapshot", help="optional snapshot path for a single package binding")
    parser.add_argument("--binding-db", help="local/SQLite runtime startup binding registry")
    parser.add_argument("--ownership-db", help="local/SQLite runtime ownership lease database")
    parser.add_argument("--owner-id", help="stable host owner id for runtime leases")
    parser.add_argument(
        "--runtime-instance-id",
        help="stable runtime instance id; defaults to runtime_<world_id> with --binding-db",
    )
    parser.add_argument(
        "--recover-ownership",
        action="store_true",
        help="explicitly recover same-owner leases during startup",
    )
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        help="automatically renew registered runtime ownership leases",
    )
    parser.add_argument("--heartbeat-interval", type=float, help="ownership heartbeat interval in seconds")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.packages and not args.binding_db:
        raise SystemExit("provide at least one package or --binding-db")
    if args.event_log and len(args.packages) != 1:
        raise SystemExit("--event-log can only be used with one package")
    if args.snapshot and len(args.packages) != 1:
        raise SystemExit("--snapshot can only be used with one package")
    if args.snapshot and not args.binding_db:
        raise SystemExit("--snapshot requires --binding-db")
    if args.owner_id and not args.ownership_db:
        raise SystemExit("--owner-id requires --ownership-db")
    if args.ownership_db and not args.owner_id:
        raise SystemExit("--ownership-db requires --owner-id")
    if args.recover_ownership and not args.ownership_db:
        raise SystemExit("--recover-ownership requires --ownership-db and --owner-id")
    if args.heartbeat and not args.ownership_db:
        raise SystemExit("--heartbeat requires --ownership-db and --owner-id")

    binding_store = RuntimeBindingStore(args.binding_db) if args.binding_db else None
    ownership_store = RuntimeOwnershipLeaseStore(args.ownership_db) if args.ownership_db else None
    service = ReadOnlyWorldService(
        ownership_store=ownership_store,
        ownership_owner_id=args.owner_id,
    )
    if args.packages:
        for package in args.packages:
            runtime_instance_id = args.runtime_instance_id
            if binding_store is not None and runtime_instance_id is None:
                manifest = json.loads(Path(package).read_text(encoding="utf-8"))["manifest"]
                runtime_instance_id = f"runtime_{manifest['world_id']}"
            world_id = service.register_package(
                package,
                event_log_path=args.event_log,
                runtime_instance_id=runtime_instance_id,
                recover_ownership=args.recover_ownership,
            )
            if binding_store is not None:
                resolved_instance_id = runtime_instance_id
                if resolved_instance_id is None:
                    resolved_instance_id = next(
                        world["runtime_instance_id"]
                        for world in service.list_worlds()["worlds"]
                        if world["world_id"] == world_id
                    )
                record = RuntimeBindingRecord(
                    world_id=world_id,
                    runtime_instance_id=resolved_instance_id,
                    package_path=str(Path(package)),
                    event_log_path=None if args.event_log is None else str(Path(args.event_log)),
                    snapshot_path=None if args.snapshot is None else str(Path(args.snapshot)),
                )
                existing = binding_store.get(world_id, resolved_instance_id)
                if existing is None:
                    binding_store.register(record)
                else:
                    binding_store.update(record)
    elif binding_store is not None:
        service.rehydrate_from_binding_store(
            binding_store,
            recover_ownership=args.recover_ownership,
        )
    if args.heartbeat:
        for world in service.list_worlds()["worlds"]:
            service.start_runtime_ownership_heartbeat(
                world["world_id"],
                interval_seconds=args.heartbeat_interval,
            )
    try:
        server = build_mcp_server(service)
    except MCPDependencyError as exc:
        print(f"ERROR: {exc}")
        return 2
    try:
        server.run(transport=args.transport)
        return 0
    finally:
        service.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
