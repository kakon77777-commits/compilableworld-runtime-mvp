# CompilableWorld Read-only MCP M0

- Contract: `compilableworld.mcp-readonly/v0.1`
- Runtime baseline: `0.1.1`
- Status: transport-neutral core implemented; FastMCP transport is optional

## Boundary

```text
MCP Tool
  -> ReadOnlyWorldService
  -> session/policy validation
  -> existing Runtime projection and EventLog
  -> versioned JSON result
```

No read-only MCP tool receives a `StateStore` write path.  Session open/close
changes only service metadata and does not change Runtime state, event log,
scheduler tick or action registry.

## Tools

- `list_worlds`
- `open_world_session`
- `get_world_status`
- `get_current_scene`
- `get_recent_events`
- `close_world_session`

## Install optional transport

```bash
python -m pip install -e ".[mcp]"
```

The dependency is pinned to the stable MCP Python SDK v1 line:

```text
mcp>=1.27,<2
```

## Run

```bash
cw-mcp-readonly build/gray_crown/world.package.json
```

Streamable HTTP for Inspector/local clients:

```bash
cw-mcp-readonly build/gray_crown/world.package.json --transport streamable-http
```

## Deliberate exclusions

- no `submit_action`
- no state writes
- no remote auth
- no multiplayer guarantee
- no generalized belief/secret model
- no Drive write-back
- no LangGraph dependency
