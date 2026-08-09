# CompilableWorld Runtime Capability Matrix

- **Document version:** v0.1
- **Baseline source:** uploaded integrated local snapshot
- **Runtime package version:** `0.1.1`
- **Audit date:** 2026-08-09
- **Verification:** `PYTHONPATH=src python -m unittest discover -s tests` — **305/305 passed**
- **Purpose:** authoritative inventory for PIW-MCP integration planning

> Status meanings: **Implemented** = code and tests exist; **Partial** = usable core exists but stated boundary remains; **Planned** = no production implementation found in this baseline.

## 1. Core compilation and runtime

| Capability | Status | Primary implementation | Test evidence | PIW-MCP consequence |
|---|---|---|---|---|
| JSON/CSV/Manifest authoring layer | Implemented | `compiler.py`, example manifests | `CompilerTests` | MCP must not bypass compiler contracts |
| Runtime Package compilation | Implemented | `compile_world()` | compiler and schema tests | MCP loads compiled packages, not raw prose |
| Versioned external schemas | Implemented | `schemas/`, `schema_registry.py` | `SchemaContractTests` | MCP contracts should follow same versioned pattern |
| Entity registry | Implemented | `EntityRegistry` | runtime integration tests | Actor/entity IDs are canonical boundaries |
| State store | Implemented | `StateStore` | atomic permission failure test | Runtime state remains authoritative |
| Action IR | Implemented | `ActionIR` | all runtime pipelines | `submit_action` should adapt to this contract |
| State Delta | Implemented | `StateDelta` | module/runtime tests | MCP must never write state directly |
| Event IR | Implemented | `EventIR` | runtime, dialogue, quest, AMK tests | MCP results should expose filtered event projections |
| Module Contract | Implemented | `ModuleContract` | permission and module tests | MCP cannot widen module write scopes |
| Atomic commit | Implemented | `WorldRuntime`, `StateStore` | `test_commit_is_atomic_on_permission_failure` | action result must be derived after commit |
| Event bus and reactions | Implemented | `EventBus`, `commit_reaction()` | dialogue→quest and quest reward tests | cross-module behavior remains event-driven |
| Event log | Implemented | `EventLog` | replay and AMK adapter tests | MCP recent-events tool can reuse this source |
| Snapshot/save | Implemented | runtime snapshot methods | round-trip and legacy migration tests | checkpoint tool may wrap existing snapshot boundary |
| Replay | Implemented | runtime replay path | movement/inventory/door replay tests | MCP session recovery can rely on replay, with version limits |
| Snapshot version validation | Implemented | runtime migration/version checks | unknown-version rejection test | MCP must return explicit version mismatch errors |
| Cross-version migration registry | Partial | `compilableworld_mcp.migration_registry`, plus explicit legacy snapshot migration | coordination and legacy migration tests | generic registry exists; Kernel snapshot loader is still a separate adapter |
| Scheduler | Implemented | `Scheduler`, Action behavior lifecycle | delay, cancellation, interruption, pending Replay and snapshot restore tests | composite actions remain under runtime authority |
| Single-process/single-world service | Partial | current runtime model | documented boundary | remote multi-session host remains outside current core |

## 2. World mechanics

| Capability | Status | Notes |
|---|---|---|
| Room and movement | Implemented | Direction aliases, reach events, room projection |
| Doors, lock, unlock, open | Implemented | Needed-key protection and target validation |
| Inventory take/drop/give | Implemented | Recipient presence/type checks and display-name resolution |
| Health and death | Implemented | Simple and formula-backed combat paths |
| Combat formula registry | Implemented | HP, AR, DR, hit chance, damage, initiative, action economy |
| Exchange/action economy | Implemented | Canon worked example and integration tests |
| Tier breakthrough gating | Implemented | Real canon NPC integration validates extreme mismatch |
| Magic resources | Implemented | MP/FP derived from attributes |
| Spells | Partial | Shield and haste implemented; broader spell library remains |
| Generic status duration | Implemented | Refresh, decay, expiration, magnitude support |
| Ranged/mental combat paths | Planned | Formula source exists but wiring is not present |
| Multi-exchange channeling/interruption | Planned | Explicitly deferred |
| Quests: simple requirements/rewards | Implemented | Reach and delivery completion |
| Quests: event transitions | Implemented | action failure, movement, inventory, door, dialogue, combat, magic and terminal quest chaining share one bounded trigger contract |
| Quests: branch/failure/priority | Implemented | deterministic priority, actor causation, event matching, requirements, graph reachability, terminal-state rejection, ambiguous dispatch rejection and exactly-once terminal reward; see `docs/WORLD_STATE_MACHINE_EXECUTION_CONTRACT_zh-TW.md` |
| Scoped StateIR: World/Region/Scene/Entity/System | Implemented | versioned authoring schema, owner validation, isolated `fsm.*` cells, deterministic EventIR transitions, visibility projection, terminal chaining, Snapshot and Replay; owner scope is not implicit geographic event routing; see `docs/SCOPED_STATE_IR_EXECUTION_CONTRACT_zh-TW.md` |
| Action-scope state machines | Implemented | v0.5 bounded sequential phases and non-recursive primitive child Actions, fail-closed actor/target State Cell AND gates, fixed-interval retry/deadline, atomic child Module StateDelta/EventIR plus `action.child_*`/progress/retry/failure lifecycle, v0.1–v0.4 compatibility, cancellation, interruption, Snapshot v0.4 and pending Replay; arbitrary/recursive Action Graph, branching, resume, compensation, parallel/join, free backoff/jitter and arbitrary guards remain pending; see `docs/ACTION_SCOPE_BEHAVIOR_EXECUTION_CONTRACT_zh-TW.md` |
| Runtime-generated items/entities | Partial | generated player exists; generic runtime entity spawning remains bounded |

## 3. Narrative, dialogue and player entry

| Capability | Status | Primary implementation | Boundary |
|---|---|---|---|
| Deterministic intent parser | Implemented | `gateway.py` | AI adapter must emit the same Action IR |
| Terminal gateway | Implemented | `TerminalGateway` | shared kernel |
| Web gateway | Implemented | `WebGateway`, stdlib HTTP server | single browser actor/session assumption |
| State-aware room narrative | Implemented | `narrative.py`, `narrative.json` | read-only projection; no state writes |
| Data-driven dialogue | Implemented | `dialogue.py`, `DialogueModule` | emits `dialogue.responded`; does not mutate quests |
| Dialogue topic fallback and conditions | Implemented | compiler/runtime selection rules | local-state projection only |
| Player template catalog | Implemented | `player_generation.py` | templates are suggestions, not canon characters |
| Deterministic seeded generation | Implemented | seed and override logic | no second combat formula path |
| Player snapshot persistence | Implemented | materialized generated actor | tested round-trip |
| LLM semantic intent adapter | Planned | no model dependency in runtime | PIW-MCP/agent layer responsibility |
| AI narrative renderer | Planned | runtime exposes facts/projections | external adapter responsibility |
| Actor belief/secret projection | Planned | no generalized belief store found | major PIW-MCP/world-model gap |

## 4. Function IR and scenarios

| Capability | Status | Notes |
|---|---|---|
| Restricted pure Function IR | Implemented | numeric expression tree only; no arbitrary Python |
| Allowed operations | Implemented | add, sub, mul, div, min, max, neg, clamp, round |
| Compile-time validation | Implemented | unsupported operations rejected |
| Exact numeric inputs | Implemented | validated argument names and numeric types |
| Bounded LRU memoization | Implemented | default bounded cache, diagnostics available |
| Studio function catalog/preview | Implemented | read-only projection |
| Scenario IR Given/When/Then | Implemented | uses normal ActionIR/Kernel/EventIR pipeline |
| Scenario compile-time validation | Implemented | unknown target and invalid actions rejected |
| Scenario state/event expectations | Implemented | packaged authoring scenarios |
| Long-session property scenarios | Partial | 100-turn deterministic observation/replay gate exists; broader stateful/property generation remains |

## 5. Studio and EveGlyph integration

| Capability | Status | Notes |
|---|---|---|
| Runtime Studio overview | Implemented | FMS/TMS/entity/state/quest graph, scoped StateIR static/current state, Action behavior definitions/pending progress and trace tail |
| Read-only Studio HTTP APIs | Implemented | overview, functions, schemas, import |
| EveGlyph YAML parser | Implemented | nested lists and quoted scalars supported |
| Studio World IR normalization | Implemented | entities, entity lists, state machines, diagnostics |
| Deterministic JSON artifact output | Implemented | reproducible World IR artifact |
| Bounded random import | Implemented | unbounded random rejected |
| Migration plan | Implemented | explicit missing bindings and diagnostics |
| Mapping suggestion | Implemented | preserves explicit values; unknowns remain unresolved |
| Mapping validation | Implemented | fail-closed World IR diagnostics, transition conflicts, and guard policy |
| Reviewed overlay compilation | Implemented | base source is not mutated |
| Full visual editing/write-back | Partial | current APIs are intentionally read-only/controlled |

## 6. Agent Memory Kernel

| Capability | Status | Notes |
|---|---|---|
| Raw immutable JSONL ledger | Implemented | integrity and replay support |
| SQLite metadata/index | Implemented | local persistence and rebuildable retrieval index |
| Clean memory promotion | Implemented | governed, auditable process |
| Evidence/authority/attribution | Implemented | explicit contracts |
| Scope and visibility isolation | Implemented | conflicts retained rather than overwritten |
| Reviewer separation | Implemented | proposer cannot approve own candidate |
| Inference vs observation separation | Implemented | inference cannot silently become OBS fact |
| Secret masking/redaction | Implemented | context access removal tested |
| Negative memory/raw fallback | Implemented | retrievable with governance boundaries |
| Lexical retrieval/context packet | Implemented | canonical retrieval unaffected by index rebuild |
| Runtime EventIR adapter | Implemented | read-only capture path |
| Adapter failure isolation | Implemented | cannot change committed runtime outcome |
| Optional CLI binding | Implemented | opt-in AMK storage |
| Remote replication/cloud sync | Partial | checkpoint/sync contracts exist; remote service not established |
| Vector retrieval | Planned/optional | not required for canonical memory authority |

## 7. PIW-MCP readiness summary

### Directly reusable

- `ActionIR`, `EventIR`, `StateDelta`, `ActionReceipt`
- `WorldRuntime`, `EventLog`, snapshot/replay
- deterministic projections and Web View Model
- Scenario IR for contract tests
- Schema registry pattern
- AMK read-only EventIR capture
- Function IR and diagnostics

### Must be added outside the world kernel

- MCP transport/server package (Partial: read-only, secure, opt-in action FastMCP facades, ASGI/stdio ingress, Streamable HTTP builder, TLS-aware Uvicorn runner, and binding-aware CLI startup exist; external process supervision and optional SDK deployment remain host-specific)
- MCP tool/resource schemas (Partial: read-only, request-context, authenticated request, and secure gateway contracts exist; per-tool JSON schemas remain pending)
- world-session registry (Partial: in-process service plus process-local/SQLite lifecycle store, explicit session rehydration, and local runtime-binding startup registry exist; distributed service discovery remains host-specific)
- actor/session/role binding (Partial: session scope and first user/world/role/actor ACL slice exist)
- idempotency request ledger (Partial: Session-scoped reservation/replay and SQLite action commit journal recovery exist; distributed ledger semantics remain pending)
- rate limiting, action reservation, and outbox (Partial: local/SQLite-shared Session ledger, sliding-window limiter, claim/ack outbox, replayable deduplicated EventLog bridge, local Kernel state/event-log commit rollback, shared-SQLite journal/outbox atomic handoff, action commit journal recovery, and optional restart-verifiable Runtime state/event projection exist; distributed limits and end-to-end Kernel/outbox ACID commit remain pending)
- filtered event and projection adapters
- remote authentication and authorization (Partial: HMAC/OIDC Principal paths, JTI revoke, ACL, lifecycle rotation, ASGI/FastMCP adapters exist; TLS termination, external claim policy, and distributed deployment remain pending)
- runtime ownership lease (Partial: process-local/SQLite exclusive lease, monotonic fencing tokens, explicit same-owner recovery, heartbeat lifecycle, optional service startup/renewal binding, authenticated centralized coordination API, single-store fenced leader lease, and optional fail-closed quorum vote gate exist; full quorum consensus remains pending)
- per-actor observation/belief projection
- MCP audit envelope (Partial: safe request/Principal/session/world/runtime/action/replay response envelopes, process-local/SQLite append/query sink, gateway persistence markers, local SHA-256 tamper detection, and restart-verifiable checkpoints exist; independently published distributed anchors and cross-host query remain pending)
- multi-world process/service boundary

### Must not be duplicated

- world state database
- quest state machine
- combat/magic resolution
- event log
- memory-as-world-truth
- narrative-owned state
- direct MCP writes to `StateStore`
