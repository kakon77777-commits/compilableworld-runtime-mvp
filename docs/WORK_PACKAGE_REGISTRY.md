# CompilableWorld Active Work Package Registry

- **Registry version:** v0.1
- **Updated:** 2026-07-16

## Baseline status

| Item | Value |
|---|---|
| Local integrated runtime | `0.1.1` |
| Verified tests | `228/228` |
| GitHub `master` observed head | `9ab8df0` |
| Remote synchronization status | **Not verified complete** — observed remote head predates integrated local files |
| Intended next release baseline | `v0.2.0-alpha.1` or equivalent |

## Current integrated local state

The local Runtime/MCP integration now includes authenticated read/action
facades, session and ACL boundaries, SQLite lifecycle/ownership recovery,
action journal and outbox handoff, audit envelopes with tamper-evident local
anchors, optional quorum-gated leader acquisition, and restart-verifiable
Runtime state/event projections.

The production deployment contract still explicitly requires an external
consensus authority, independently published audit anchors, and a single
authoritative Kernel/EventLog/journal/outbox transaction coordinator. See
`docs/MCP_M12_DISTRIBUTED_DEPLOYMENT_BOUNDARY.md`.

## Active work packages

### CW-M1-001 — Capability and contract audit

```yaml
owner_environment: chat
status: completed-locally
outputs:
  - docs/RUNTIME_CAPABILITY_MATRIX.md
  - docs/CONTRACT_INVENTORY.md
  - docs/PIW_MCP_GAP_ANALYSIS.md
acceptance:
  - integrated snapshot inspected
  - 113 tests passing
  - PIW-MCP reusable boundaries identified
```

### CW-M0-REMOTE — Synchronize integrated baseline

```yaml
owner_environment: local
status: blocked-or-incomplete-on-observed-remote
reason:
  GitHub master observed by Chat still points to 9ab8df0, while integrated
  local snapshot contains AMK, FunctionIR, ScenarioIR, Studio and schemas as
  modified/untracked files.
acceptance:
  - integrated files committed
  - remote commit visible
  - clean git status
  - 113 tests pass from fresh clone
```

### CW-M2-001 — Read-only MCP world access

```yaml
owner_environment: chat
status: queued
base_requirement:
  CW-M0-REMOTE complete and visible
branch: feature/mcp-readonly
in_scope:
  - open_world_session
  - get_world_status
  - get_current_scene
  - get_recent_events
  - close_world_session
  - versioned schemas
  - non-mutation tests
out_of_scope:
  - submit_action
  - remote authentication
  - multi-user
  - Drive write-back
  - LangGraph orchestration
```
