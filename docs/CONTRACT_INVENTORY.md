# CompilableWorld Contract Inventory

- **Document version:** v0.1
- **Baseline:** integrated Runtime `0.1.1`
- **Purpose:** enumerate stable and emerging contracts before PIW-MCP implementation

## 1. Authority hierarchy

| Domain | Authoritative source | Non-authoritative projections/adapters |
|---|---|---|
| Canon and authored rules | Authoring files + validated compiler input | Drive-readable copies, Studio views, model summaries |
| Initial executable world | Compiled Runtime Package | README examples, UI defaults |
| Current world state | `StateStore` through Kernel commit | Web/CLI/MCP projections |
| Causal history | committed `EventIR` sequence | narrative recap, AMK clean memories |
| Agent memory evidence | AMK raw ledger and governed clean entries | retrieval ranking/context packet |
| Natural-language narrative | none; it is a projection | LLM renderer, room text |

## 2. Runtime contracts

### 2.1 `ActionIR`

**Role:** the only normalized action boundary accepted by runtime modules.

Required integration rules:

- AI/MCP adapters may construct it but may not execute state writes directly.
- actor, target and payload validation remains runtime responsibility.
- action status is returned through receipt/result contracts.
- future MCP request metadata must remain outside semantic world payload unless explicitly modeled.

### 2.2 `StateDelta`

**Role:** proposed state mutation emitted by modules.

Rules:

- a module returns deltas; it does not write the store.
- all paths must fit the module's declared write scope.
- failed validation leaves state unchanged.
- UI, dialogue projection, AMK and MCP cannot manufacture committed deltas.

### 2.3 `EventIR`

**Role:** committed causal fact and cross-module communication primitive.

Rules:

- event ordering is significant.
- reactions consume declared events rather than call module internals.
- AMK may subscribe read-only.
- MCP may expose filtered events but must not rewrite historical events.
- external effects should gain explicit reversibility/side-effect metadata in a future version.

### 2.4 `ModuleContract`

**Role:** declares action ownership and state read/write authority.

Current strength:

- write scopes are enforced by Kernel.

Known gap:

- generalized read-scope and action-authority isolation remains incomplete.

PIW-MCP rule:

- MCP policy does not replace Module Contract; both layers must authorize a write.

### 2.5 Runtime Package

**Role:** compiled executable world input.

Current contract ID:

- `runtime-package.v0.1.schema.json`

Contains or references:

- world metadata
- entities, rooms, exits, items
- quests and transitions
- World/Region/Scene/Entity/System scoped StateIR
- bounded Action-scope behavior definitions and lifecycle metadata
- dialogues and narrative overlays
- Function IR
- Scenario IR
- player templates
- schema contract IDs

## 3. Authoring contracts

Checked-in schemas:

1. `functions.v0.1.schema.json`
2. `scenarios.v0.1.schema.json`
3. `runtime-package.v0.1.schema.json`
4. `rooms.v0.1.csv.schema.json`
5. `exits.v0.1.csv.schema.json`
6. `entities.v0.1.csv.schema.json`
7. `items.v0.1.csv.schema.json`
8. `state-machines.v0.1.schema.json`
9. `action-behaviors.v0.4.schema.json`（Compiler 仍接受保留的 v0.1 單階段、v0.2 sequential 與 v0.3 condition-gated 來源）
10. `studio-world-ir.v0.1.schema.json`
11. `studio-mapping.v0.1.schema.json`

Compiler-owned semantic validation remains authoritative for:

- duplicate IDs
- cross-file references
- state reachability
- event payload semantics
- transition ambiguity
- safe source paths
- actor/entity type constraints

## 4. Function IR contract

**Authority:** pure deterministic calculation, not state transition.

Allowed operation family:

```text
add, sub, mul, div, min, max, neg, clamp, round
```

Invariants:

- no arbitrary Python
- no I/O
- no state writes
- exact validated numeric inputs
- deterministic result
- cache is derived and rebuildable

Function IR may compute values used by modules, but only modules produce `StateDelta`/`EventIR`.

## 5. Scenario IR contract

**Role:** executable Given/When/Then scenario using the normal runtime pipeline.

Invariants:

- `given` is memory-local setup for the scenario.
- `when` enters through Action IR and Kernel.
- `expect` observes state/events/status.
- scenarios cannot become a hidden second rules engine.
- invalid target/action/state reference fails during compilation.

PIW-MCP extension targets:

- tool contract scenarios
- duplicate request scenarios
- read-only non-mutation scenarios
- actor observation isolation scenarios
- 100-turn persistence scenarios

## 6. Projection contracts

Existing projections:

- terminal rendering
- Web View Model
- room narrative overlay
- Studio package/runtime overview
- function/schema catalogs

Required PIW-MCP projection types:

- `WorldStatusProjection`
- `SceneProjection`
- `ActorProjection`
- `RecentEventProjection`
- `AvailableActionProjection`

Projection invariants:

- read-only
- actor/session filtered
- contains stable IDs plus display labels
- does not expose secrets or internal state paths by default
- must declare projection contract version

## 7. AMK contracts

Core contracts include:

- `ActorIdentity`
- `MemoryScope`
- `AttributionEnvelope`
- `MemoryGovernance`
- `MemoryRelations`
- `ValidTime`
- `RawEvent`
- `MemoryEntry`
- `PromotionContract`
- `SyncCheckpoint`
- `ContextPacket`

AMK authority boundary:

$$
\text{World State/Event Log} \rightarrow \text{AMK Evidence Capture}
$$

but never:

$$
\text{AMK Memory} \rightarrow \text{Direct World State Override}
$$

## 8. Proposed PIW-MCP contracts

### 8.1 Session contract

```text
session_id
world_id
runtime_instance_id
timeline_id
actor_id
user_id
client_id
model_id
role
permissions
opened_at
expires_at
runtime_version
mcp_contract_version
```

### 8.2 Tool request envelope

```text
tool_name
session_id
client_request_id
request_time
arguments
expected_world_version (optional)
```

### 8.3 Tool result envelope

```text
status
request_id
world_state_changed
receipt/event projection
new_world_version
error_code
retryable
```

### 8.4 Idempotency contract

The tuple below must uniquely identify a write request:

```text
session_id + actor_id + timeline_id + client_request_id
```

### 8.5 Error contract

Initial stable codes:

```text
WORLD_NOT_FOUND
SESSION_INVALID
ACTOR_NOT_FOUND
PERMISSION_DENIED
ACTION_NOT_SUPPORTED
PRECONDITION_FAILED
TARGET_NOT_FOUND
TARGET_NOT_REACHABLE
STATE_CONFLICT
DUPLICATE_REQUEST
RUNTIME_VERSION_MISMATCH
INTERNAL_RUNTIME_ERROR
```

## 9. Contract version registry proposal

```json
{
  "runtime": "0.1.1",
  "runtime_package": "compilableworld.runtime-package/v0.1",
  "action_ir": "compilableworld.action-ir/v0.1",
  "event_ir": "compilableworld.event-ir/v0.1",
  "projection": "compilableworld.projection/v0.1",
  "amk": "agent-memory-kernel/v0.1",
  "mcp_world": "compilableworld.mcp/v0.1"
}
```

Before remote write tools are enabled, Action IR, Event IR and Projection should gain explicit serializable contract IDs rather than rely only on Python dataclass shape.
