# CompilableWorld Active Work Package Registry

- **Registry version:** v0.1
- **Updated:** 2026-08-09

## Baseline status

| Item | Value |
|---|---|
| Local integrated runtime | `0.1.1` |
| Verified tests | `257/257` |
| GitHub `master` observed head | `72334d7` (verified 2026-08-09) |
| GitHub integration branch before this package | `agent/m12-runtime-mcp-integration` at `acc1841` |
| Remote synchronization status | Integration branch was synchronized before this world-state-machine package; this package is deployed by its own commit/push |
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
status: completed-on-integration-branch
evidence:
  - origin/agent/m12-runtime-mcp-integration observed at acc1841 before this package
  - origin/master observed at 72334d7
acceptance:
  - integrated files committed
  - remote commit visible
  - full test suite passes
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

### CW-M12-WSM-001 — Bounded world state machine execution

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - src/compilableworld/state_machine.py
  - docs/WORLD_STATE_MACHINE_EXECUTION_CONTRACT_zh-TW.md
  - Studio World IR, mapping and reviewed-overlay compile integration
  - tests/test_world_state_machine.py
acceptance:
  - one shared EventIR trigger and payload-field contract
  - actor resolved from ActionIR causation before payload or quest-target fallback
  - deterministic priority, event_match and bounded requirements
  - terminal quest chaining without terminal reopening or duplicate reward
  - unreachable branches, terminal outgoing edges and ambiguous dispatch fail closed
  - Snapshot, Replay, multi-player isolation and reaction rollback verified
  - 257/257 tests pass
out_of_scope:
  - free-form guard execution
  - Runtime sampling of Studio bounded random metadata
  - AI direct StateStore writes
```
