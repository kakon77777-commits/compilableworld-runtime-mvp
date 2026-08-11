# Persistent Interactive World MCP Gap Analysis

- **Document version:** v0.1
- **Runtime baseline:** CompilableWorld `0.1.1`, current local suite `333/333` plus 64 subtests passing
- **Objective:** define the minimum work required to expose the existing world runtime safely through MCP

## 1. Executive conclusion

The project does **not** need a second world engine, memory framework, quest system or event database.

The missing layer is primarily:

```text
MCP transport
+ session binding
+ policy
+ idempotency
+ actor-filtered projections
+ contract serialization
```

The shortest valid implementation is a thin adapter around existing Runtime APIs.

## Current implementation status

The original P0 read-only and P1 action-loop packages are now implemented as
the local M0–M12 integration: authenticated sessions, ACL, idempotency,
rate-limits, audit, action journal, outbox, ownership, rehydration,
coordination, quorum gating, and Runtime durability projection are covered by
the current regression suite. The 100-turn local long-session gate is also now
executable in `tests/test_long_session.py`.

P2 observation/belief projection, M4 AMK ContextPacket binding, complete Studio
write-back, and M6 production-grade distributed hosting remain partial. The
external consensus, independent audit anchoring, and end-to-end ACID boundary
are deployment contracts rather than claims of the local MVP.

## 2. Readiness matrix

| PIW-MCP requirement | Existing reusable capability | Gap | Priority |
|---|---|---|---|
| Open a world | package loader/runtime construction | instance/session registry | P0 |
| Read world status | runtime diagnostics/state | stable filtered status schema | P0 |
| Read current scene | Web View Model/narrative projection | actor/session-neutral adapter | P0 |
| Read recent events | Event Log | pagination/filter/schema | P0 |
| Submit action | ActionIR + deterministic parser + Kernel | MCP action schema, idempotency, audit | P1 |
| Checkpoint | snapshot/save | named checkpoint registry and permission | P1 |
| Restore | snapshot load/migration | high-risk approval and semantic side-effect policy | P2 |
| Actor knowledge | room visibility and dialogue conditions | generalized observation/belief model | P2 |
| Long-term memory | AMK | context packet binding to MCP session | P2 |
| Multi-world | package/runtime constructors | host registry and lifecycle | P2 |
| Multi-user | none | auth, session isolation, concurrency model | P3 |
| Remote deployment | stdlib web server exists | MCP Streamable HTTP, TLS/auth | P3 |

## 3. P0 work package: read-only MCP

### Tools

1. `open_world_session`
2. `get_world_status`
3. `get_current_scene`
4. `get_recent_events`
5. `close_world_session`

### Required modules

```text
src/compilableworld_mcp/
├── __init__.py
├── server.py
├── sessions.py
├── schemas.py
├── projections.py
├── policy.py
└── tools_readonly.py
```

### Acceptance criteria

- no tool can mutate `StateStore`
- opening/closing a session does not change world state
- scene output matches Web View Model facts for the same actor
- recent events preserve committed order
- unknown world/session/actor fails closed
- output is JSON-serializable and versioned
- historical 113-test baseline remains green; current local suite is 333/333 plus 64 subtests
- new read-only contract tests prove pre/post state hash equality

## 4. P1 work package: action loop

### New tool

`submit_action`

### Required additions

- `ActionIR` serialization contract
- input validation
- session actor binding
- role/tool policy
- idempotency ledger
- action audit record
- receipt/error projection
- optimistic world-version check (recommended)

### Critical invariant

```text
MCP -> ActionIR -> WorldRuntime.submit() -> StateDelta/EventIR -> Kernel commit
```

Forbidden path:

```text
MCP -> StateStore.set(...)
```

## 5. P2 work package: observation and memory

### Observation

The existing scene projection knows physical visibility but not a generalized epistemic model.

Needed concepts:

```text
world truth
actor-observed fact
actor-believed fact
secret classification
source event
confidence
valid time
```

### AMK integration

AMK should compile context after world projection, not replace it:

```text
Runtime Projection
+ Filtered Recent EventIR
+ AMK ContextPacket
-> Agent context
```

AMK failure remains non-fatal to world execution.

## 6. Security gaps

### Current strengths

- no arbitrary Python in Function IR
- path escape rejection
- module write-scope enforcement
- fail-closed compiler and mapping validation
- AMK adapter read-only and failure-isolated
- no mandatory network/AI dependency

### Required before remote writes

- authenticated user identity
- session expiration/revocation
- per-tool permissions
- actor ownership checks
- request size and rate limits
- remote transport security
- audit retention
- prompt-injection isolation for Drive/authoring text
- explicit external-side-effect classification

## 7. Concurrency gaps

The current runtime is documented as single process/single world and Web Gateway serializes requests with one lock.

Before multi-user support, choose one authority model:

1. one runtime process per world instance;
2. actor/session requests serialized through a world mailbox;
3. versioned optimistic commits with retry;
4. database-backed authoritative state in a later architecture.

MCP v0.1 should not imply multiplayer guarantees.

## 8. Contract gaps to close before P1

- explicit `ActionIR` JSON schema
- explicit `EventIR` JSON schema
- explicit projection schema
- request/result envelope schema
- error-code registry
- idempotency record schema
- runtime instance/version fields

## 9. Recommended implementation order

```text
M1 capability/contract audit        [this document set]
  ↓
M2 read-only MCP adapter
  ↓ local MCP Inspector validation
M3 submit_action + idempotency
  ↓ 100-turn scenario validation
M4 AMK ContextPacket integration
  ↓
M5 actor observation/belief projection
  ↓
M6 remote authentication and multi-world hosting
```

## 10. Explicit non-goals for MCP v0.1

- replacing the existing Web Gateway
- replacing deterministic intent parsing
- adding LangGraph inside World Kernel
- exposing raw SQL or arbitrary filesystem access
- automatic Drive-to-Canon write-back
- multiplayer consistency guarantees
- unrestricted restore/branch operations
- making AMK clean memory authoritative world truth
