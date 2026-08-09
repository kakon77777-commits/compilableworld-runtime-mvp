# CompilableWorld Active Work Package Registry

- **Registry version:** v0.1
- **Updated:** 2026-08-09

## Baseline status

| Item | Value |
|---|---|
| Local integrated runtime | `0.1.1` |
| Verified tests | `305/305` |
| GitHub `master` observed head | `72334d7` (verified 2026-08-09) |
| GitHub integration branch before bounded-child package | `agent/m12-runtime-mcp-integration` at `bbe375d` |
| Remote synchronization status | Bounded retry/deadline v0.4 is pushed; primitive child Action v0.5 is the current reviewed integration-branch package |
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

### CW-M12-HSM-002 — Scoped executable StateIR

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - schemas/state-machines.v0.1.schema.json
  - src/compilableworld/compiler.py
  - src/compilableworld/modules.py
  - src/compilableworld/studio.py
  - examples/gray_crown/state_machines.json
  - docs/SCOPED_STATE_IR_EXECUTION_CONTRACT_zh-TW.md
  - tests/test_scoped_state_machine.py
acceptance:
  - World, Region, Scene, Entity and System owners compile to isolated fsm cells
  - deterministic EventIR equality matching and priority selection
  - fsm terminal events chain into another FSM or actor quest with full causation
  - public, private and audit visibility fail closed from authored visibility
  - legacy owner::fsm::state seeds remain compatible
  - Snapshot, Replay, Studio projection and reaction rollback verified
  - 265/265 tests pass
out_of_scope:
  - implicit geographic event routing
  - Action-scope composite state machines
  - free-form guards, arbitrary effects or rewards
  - Runtime sampling of Studio bounded random metadata
  - AI direct StateStore writes
```

### CW-M12-ACTION-003 — Cancellable Action-scope behaviors

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - schemas/action-behaviors.v0.1.schema.json
  - src/compilableworld/action_behavior.py
  - Scheduler and Kernel lifecycle integration
  - exploration.core careful-search vertical slice
  - Studio static/pending projections and terminal commands
  - MCP scheduled-action receipt alignment
  - docs/ACTION_SCOPE_BEHAVIOR_EXECUTION_CONTRACT_zh-TW.md
  - tests/test_action_behavior.py
acceptance:
  - authored duration and one-per-actor concurrency compile fail closed
  - scheduled actions emit deterministic lifecycle EventIR
  - owner-scoped cancellation and movement/damage/defeat interruption work
  - completion writes only through module StateDelta/EventIR
  - Snapshot preserves exact progress and EventLog Replay rebuilds pending work
  - lifecycle events can drive scoped StateIR
  - Studio and MCP report scheduled work without treating it as failure
  - 281/281 tests pass
out_of_scope:
  - resume and compensation transactions
  - parallel child steps or arbitrary interrupt expressions
  - Studio visual authoring/write-back form
  - player/MCP remote control of authoritative Runtime time
  - AI direct StateStore writes
```

### CW-M12-ACTION-004 — Bounded sequential phase checkpoints

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - schemas/action-behaviors.v0.2.schema.json
  - v0.1 authoring compatibility path
  - exact-tick action.progressed EventIR
  - phase-aware pending, Snapshot, Replay and Studio projections
  - terminal phase progress notification
  - tests/test_action_behavior.py
acceptance:
  - each behavior declares two to sixty-four ordered bounded phases
  - Compiler derives total duration and rejects duplicate or unbounded phases
  - advance across multiple ticks emits every checkpoint at its exact tick
  - checkpoint EventLog failure restores tick and retries without duplication
  - Snapshot preserves current phase and Replay restores the last emitted checkpoint
  - action.progressed can drive scoped StateIR without direct StateStore writes
  - legacy v0.1 single-stage authoring remains compilable and truthfully identified
  - 285/285 tests pass
out_of_scope:
  - child Action execution or generic phase effects
  - conditional, retry, timeout or parallel graphs
  - resume and compensation transactions
  - Studio visual authoring/write-back form
  - AI direct StateStore writes
```

### CW-M12-ACTION-005 — Fail-closed phase-entry conditions

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - schemas/action-behaviors.v0.3.schema.json
  - v0.1 and v0.2 authoring compatibility paths
  - bounded actor/target State Cell condition evaluator
  - atomic conditional action.failed lifecycle
  - condition-aware Studio and redacted player pending projections
  - tests/test_action_behavior.py
acceptance:
  - non-initial phases accept at most sixteen deterministic AND conditions
  - subjects, namespaces, keys, operators and finite scalar values compile fail closed
  - missing owners/cells, bad types and non-finite values fail without coercion
  - target numeric comparisons and strict boolean equality are verified
  - condition failure atomically removes the queue item and emits phase/condition provenance
  - EventLog failure restores tick, queue and ActionStatus without duplicate failure
  - conditional action.failed can drive scoped StateIR
  - player pending projection does not expose condition path, operator or value
  - 290/290 tests pass
out_of_scope:
  - if/else branching or OR/NOT expression graphs
  - child Action execution or generic phase effects
  - retry, timeout, resume, compensation or parallel graphs
  - Studio visual authoring/write-back form
  - AI direct StateStore writes
```

### CW-M12-ACTION-006 — Bounded retry and timeout

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - schemas/action-behaviors.v0.4.schema.json
  - v0.1, v0.2 and v0.3 authoring compatibility paths
  - fixed-interval retry and deadline checkpoint execution
  - action.retry_scheduled and retry_exhausted EventIR
  - Snapshot v0.3 action runtime state and v0.1/v0.2 migration
  - retry-aware EventLog Replay, Studio pending projection and terminal notice
  - tests/test_action_behavior.py
acceptance:
  - non-initial conditional phases may author one to sixteen retry attempts
  - interval and timeout are positive, bounded and compiler-validated
  - failed gates atomically shift due tick or terminate at attempt/deadline exhaustion
  - EventLog failure restores tick, queue, due tick, ActionStatus and retry state
  - Snapshot and Replay preserve attempt, first failure, next retry and deadline
  - action.retry_scheduled can drive scoped StateIR without direct StateStore writes
  - v0.1/v0.2/v0.3 sources preserve their original no-retry semantics
  - 297/297 tests pass
out_of_scope:
  - exponential or free-form backoff, jitter and dynamic deadline extension
  - if/else branching or OR/NOT expression graphs
  - child Action execution, compensation, resume or parallel graphs
  - Studio visual authoring/write-back form
  - AI direct StateStore writes
```

### CW-M12-ACTION-007 — Bounded primitive child Action sequence

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - schemas/action-behaviors.v0.5.schema.json
  - v0.1, v0.2, v0.3 and v0.4 authoring compatibility paths
  - compiler-normalized primitive child verb/module/target/args contract
  - action.child_started, action.child_completed and action.child_failed EventIR
  - atomic child Module StateDelta/EventIR plus parent checkpoint transaction
  - Snapshot v0.4 completed-step prefix and v0.1/v0.2/v0.3 migration
  - child-aware Replay, Studio projection and terminal notice
  - tests/test_action_behavior.py
acceptance:
  - non-final phases may execute one fixed child step in authored phase order
  - child actor/correlation are inherited and authored behaviors cannot recurse
  - primitive verb, module owner, static/parent target and args compile fail closed
  - completed steps do not rerun during phase-gate retry
  - rejected child terminates the parent with explicit child provenance
  - EventLog failure restores StateStore, tick, queue, registry and child progress
  - Snapshot and Replay preserve an exact authored completed-step prefix
  - child lifecycle can drive scoped StateIR without direct StateStore writes
  - 305/305 tests pass
out_of_scope:
  - arbitrary or recursive child Action graphs and dynamic actors/targets
  - if/else branching, OR/NOT graphs, parallel or join
  - resume, rollback or compensation transactions
  - Studio visual authoring/write-back form
  - AI direct StateStore writes
```
