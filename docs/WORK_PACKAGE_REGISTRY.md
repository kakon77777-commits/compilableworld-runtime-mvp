# CompilableWorld Active Work Package Registry

- **Registry version:** v0.1
- **Updated:** 2026-08-11

## Baseline status

| Item | Value |
|---|---|
| Local integrated runtime | `0.1.1` |
| Verified tests | `333/333`, plus `64` subtests |
| GitHub `master` observed head | `70141f3` (verified 2026-08-11) |
| Current development branch | `agent/stateir-v05-bounded-hierarchy` |
| Remote synchronization status | M12 and Action routing v0.7 are merged; StateIR v0.2 and future-architecture notes remain on draft PR #4; StateIR v0.3 timer, v0.4 bounded chaining and v0.5 bounded hierarchy work are completed locally and intentionally unpushed |
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
status: completed-and-deployed-on-integration-branch
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

### CW-M12-ACTION-008 — Bounded conditional child branch

```yaml
owner_environment: codex
status: completed-and-deployed-on-integration-branch
outputs:
  - schemas/action-behaviors.v0.6.schema.json
  - v0.1 through v0.5 authoring compatibility paths
  - compiler-normalized unique priority and mandatory fallback branch contract
  - sticky action.branch_selected EventIR and implicit linear rejoin
  - Snapshot v0.5 selected branch persistence and v0.1 through v0.4 migration
  - branch-aware Replay, scoped StateIR, Studio projection and terminal notice
  - tests/test_action_behavior.py
acceptance:
  - non-final phases may declare two to sixteen compile-time-known branches
  - each branch set has unique priorities and exactly one lowest-priority fallback
  - highest-priority matching bounded AND branch is selected deterministically
  - selection and successful child step remain sticky across gate retry
  - branch execution rejoins only the next authored linear phase
  - EventLog failure restores StateStore, tick, queue, registry, branch and child progress
  - Snapshot rejects unknown or non-prefix selections and Replay rejects payload tampering
  - action.branch_selected can drive scoped StateIR without direct StateStore writes
  - 310/310 tests pass
out_of_scope:
  - arbitrary or recursive phase graphs, nested branches and dynamic topology
  - OR/NOT or free-form expressions
  - parallel child execution, explicit join, loop and history state
  - resume, rollback or compensation transactions
  - Studio visual behavior authoring/direct write-back
  - AI direct StateStore writes
```

### CW-M12-ACTION-009 — Bounded static phase DAG routing

```yaml
owner_environment: codex
status: completed-on-integration-branch
outputs:
  - schemas/action-behaviors.v0.7.schema.json
  - v0.1 through v0.6 authoring compatibility paths
  - compiler-validated unique entry/terminal, target closure, acyclicity and reachability
  - sticky single-path route cursor with actual terminal due convergence
  - Snapshot v0.6 route persistence and v0.1 through v0.5 migration
  - route-aware Replay, Studio projection and pending runtime projection
  - tests/test_action_behavior.py
acceptance:
  - every non-terminal phase has one to sixteen static next_phase_id edges
  - at least one phase is a real split and exactly one phase is terminal
  - unknown targets, self-routes, reachable cycles and unreachable phases fail compilation
  - highest-priority matching branch selects one path and never executes sibling paths
  - shorter routes reschedule completion to the actual terminal boundary
  - gate retry preserves the selected branch, route cursor and completed child step
  - Snapshot validates visited edges and queue/phase due ticks
  - Replay rejects branch targets or route boundary ticks that violate authored topology
  - 316/316 tests pass
out_of_scope:
  - runtime-generated, recursive or nested graph topology
  - OR/NOT or free-form expressions
  - parallel child execution and synchronizing join
  - loop, history, pause/resume and compensation transactions
  - Studio visual behavior authoring/direct write-back
  - AI direct StateStore writes
```

### CW-M12-STATEIR-010 — Bounded owner/actor StateIR conditions

```yaml
owner_environment: codex
status: completed-on-draft-pr
outputs:
  - schemas/state-machines.v0.2.schema.json
  - v0.1 authoring compatibility and explicit source-schema negotiation
  - compiler-normalized bounded transition when conditions
  - fail-closed owner/verified-actor StateStore condition evaluator
  - strict scalar comparison and deterministic priority fallback
  - Gray Crown owner/actor/numeric AND-condition vertical slice
  - Studio read-only condition projection
  - tests/test_scoped_state_machine.py
acceptance:
  - each v0.2 transition explicitly declares zero to sixteen AND conditions
  - condition IDs are machine-unique and all fields use bounded allowlists
  - actor reads require a verified EventIR causation chain
  - missing state, unknown provenance, invalid type and non-finite values return false
  - boolean values are not coerced to zero or one
  - only condition-matching candidates participate in priority selection
  - StateIR can still write only its own owner::fsm::<machine_id> cell
  - Snapshot format is unchanged and Replay still applies committed StateDelta
  - 320/320 tests and 46 subtests pass
out_of_scope:
  - OR/NOT groups and free-form expressions
  - arbitrary StateStore paths, effects or rewards
  - implicit geographic event routing
  - timers, history states, parallel regions and synchronizing joins
  - AI direct StateStore writes
```

### CW-M12-STATEIR-011 — Bounded deterministic tick timers

```yaml
owner_environment: codex
status: completed-locally
outputs:
  - schemas/state-machines.v0.3.schema.json
  - v0.1 and v0.2 event-source compatibility paths
  - mutually exclusive EventIR on or bounded after_ticks trigger
  - compiler-reserved owner::fsm_runtime::state_machine_id entry tick
  - fsm.timer_elapsed lifecycle EventIR and timer-aware Replay validation
  - Gray Crown breached-to-contained timer vertical slice
  - Studio static trigger and live pending countdown projection
  - tests/test_scoped_state_machine.py
acceptance:
  - after_ticks is a positive integer bounded at 1,000,000
  - timer transitions reject on, event_match and actor conditions
  - timers use only the authoritative Kernel scheduler tick and no wall clock
  - owner conditions keep an elapsed timer eligible until a unique priority winner exists
  - all due machines select from one pre-commit state and commit as one bounded batch
  - entry tick changes only with the machine state through StateDelta
  - Snapshot v0.6 preserves timer entry state without a second queue or format bump
  - Replay validates authored timer identity and entered/eligible/fired tick arithmetic
  - EventLog append failure rolls back StateIR cells and an overdue timer can retry
  - 324/324 tests and 52 subtests pass
out_of_scope:
  - wall-clock, calendar, cron and multi-rate clock semantics
  - periodic timers, cancellation, pause/resume and dynamic rescheduling
  - history states, parallel regions and synchronizing joins
  - implicit geographic event routing
  - AI, Studio, player or MCP control of authoritative Runtime time
  - AI direct StateStore writes
```

### CW-M12-STATEIR-012 — Bounded non-terminal StateIR chaining

```yaml
owner_environment: codex
status: completed-locally
outputs:
  - schemas/state-machines.v0.4.schema.json
  - v0.1, v0.2 and v0.3 source compatibility paths
  - explicit fsm.transitioned source machine and transition binding
  - compile-time source existence and static payload consistency validation
  - acyclic dependency graph with a maximum depth of 64 edges
  - synchronous FIFO EventBus batch dispatch with a 4096-event root cascade limit
  - audit-only runtime.reaction_halted EventIR and Replay validation
  - Gray Crown breached-to-region-alerted non-terminal vertical slice
  - tests/test_event_bus.py and tests/test_scoped_state_machine.py
acceptance:
  - re-entrant events queue behind every event already present in the committed batch
  - StateIR v0.4 rejects broad fsm.transitioned listeners without machine and transition IDs
  - missing source transitions and mismatched authored source payload fields fail compilation
  - self/cross-machine dependency cycles and chains deeper than 64 edges fail compilation
  - the Runtime halts pending delivery after 4096 dispatched events without recursive stack growth
  - cascade halt preserves already committed StateDelta/EventIR and records an audit boundary
  - the halt audit event is not republished and cannot recursively trigger another reaction
  - Replay rejects tampered cascade boundaries and restores halt diagnostics
  - AI, Studio, player and MCP still have no direct StateStore write path
  - 329/329 tests and 58 subtests pass
out_of_scope:
  - cyclic feedback as an authored gameplay mechanism
  - dynamic runtime subscriptions or dependency graph mutation
  - arbitrary effects, scripts, free guards and implicit geographic routing
  - treating a cascade halt as a successful normal transition branch
  - distributed EventBus delivery or cross-process exactly-once semantics
```

### CW-M12-STATEIR-013 — Bounded single-active-leaf hierarchy

```yaml
owner_environment: codex
status: completed-locally
outputs:
  - schemas/state-machines.v0.5.schema.json
  - v0.1 through v0.4 source compatibility paths
  - direct child-to-parent and compound-to-initial-child maps
  - deterministic compound target and initial-state leaf resolution
  - priority-then-specificity ancestor transition selection
  - authored from/to plus actual from_leaf/to_leaf lifecycle provenance
  - Replay validation and Studio initial/current/source/target path projection
  - Gray Crown nominal-to-incident-to-breached compound entry slice
  - tests/test_scoped_state_machine.py and tests/test_schemas.py
acceptance:
  - Runtime StateStore retains exactly one authoritative active leaf per machine
  - every compound state declares exactly one direct initial child
  - hierarchy cycles, unknown edges and depth beyond 16 fail compilation
  - timer transitions originate only from active leaves
  - same-priority leaf transitions override matching ancestor transitions
  - transition targets resolve deterministically before StateDelta commit
  - lifecycle EventIR and Replay distinguish authored targets from resolved leaves
  - v0.1 through v0.4 sources compile into explicit empty hierarchy metadata
  - AI, Studio, player and MCP still have no direct StateStore write path
  - 333/333 tests and 64 subtests pass
out_of_scope:
  - parallel regions or multiple active leaves
  - history state or shallow/deep history restoration
  - arbitrary entry/exit effects and runtime hierarchy mutation
  - ancestor-authored internal resets that can become child-dependent no-ops
  - compound-state timers with independent ancestor entry clocks
```
