# MCP Host Startup M12 Local Slice

This document records the executable host startup path for the Runtime MVP.

## CLI

The `cw-mcp-readonly` entry point supports:

- direct package startup with `cw-mcp-readonly package.json`;
- binding-only restart with `--binding-db bindings.sqlite3`;
- package/event-log/snapshot binding registration;
- SQLite ownership with `--ownership-db` and stable `--owner-id`;
- explicit same-owner recovery with `--recover-ownership`;
- automatic lease renewal with `--heartbeat` and `--heartbeat-interval`.

When no package argument is supplied, enabled bindings are loaded first,
including EventLog history and optional snapshots. Service shutdown releases
configured leases through the service lifecycle.

## Boundary still explicit

This is a local/SQLite startup registry and host lifecycle. It does not provide
cloud service discovery, leader election, or process supervision beyond the
selected FastMCP/Uvicorn host.

## Verification

`tests/test_mcp_server.py` covers package registration into the binding store
and binding-only rehydration through the CLI entry point.
