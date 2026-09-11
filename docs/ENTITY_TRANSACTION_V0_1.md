# Entity Transaction v0.1

`entity_transaction/v0.1` is an additive Runtime capability for transaction-safe dynamic entity creation.

## Motivation

`WorldRuntime` historically commits `StateDelta` + `EventIR` atomically with durable EventLog rollback, while `EntityRegistry.add()` is an imperative operation used by initialization and player-generation paths. A Runtime Module therefore could not create an entity inside the same rollback boundary as its state and events.

## Contract

A module that returns `TransitionResult.entity_deltas` must declare:

```text
entity_transaction/v0.1
```

in `ModuleContract.requires_kernel` and execute under `EntityTransactionRuntime`.

The v0.1 transaction is:

```text
Module.evaluate(ActionIR)
  -> validate StateDelta + create-only EntityDelta
  -> commit StateDelta
  -> apply EntityDelta(create)
  -> append state.committed + entity.committed + module EventIR as one EventLog batch
  -> publish events only after durable append succeeds
```

If state commit, entity creation, or durable EventLog append fails, StateStore, EntityRegistry, and `dynamic_entities` are restored to the pre-action snapshot.

## Deliberate limits

- `EntityDelta.operation` supports `create` only.
- `expected_absent=true` is mandatory.
- remove/despawn/replace are not implied by this contract.
- Entity IDs come from governed callers; v0.1 does not define a dynamic ID allocator.
- Creation remains opt-in through `EntityTransactionRuntime`; base `WorldRuntime` rejects an entity-creation EventLog before applying state from it.
- Existing positional `TransitionResult(True, deltas, events, message)` remains source-compatible because `entity_deltas` is appended after `message`.

## Day 1 integration compatibility (2026-09-10)

The extension follows the existing Kernel lifecycle for plain delayed Actions,
including those without an authored Action behavior. Successful and rejected
scheduled creation both retain the `action.started` boundary.

Committed state, entity and module events are published as one FIFO batch via
the Kernel event dispatcher. Re-entrant reactions follow the complete parent
batch in the same order recorded by the EventLog.

The focused tests cover immediate creation, duplicate rejection, append failure,
declared capability, plain delayed success/failure, and reaction ordering.
Generic persistence is covered by the Day 2 extension below; the Day 1
create-only tests alone do not establish it.

## Day 2 persistence and continuation (2026-09-11)

The complete path is create, save, restore or replay, then continue Actions.
Run the offline example from the repository with `PYTHONPATH=src`:

```powershell
python -B examples/entity_lifecycle_demo.py
```

### Stored contracts and compatibility

- `entity.committed` retains EventIR version 1 and its existing
  `{"applied": [{"operation": "create", "entity": {...}}]}` payload. The
  independent storage schema is `schemas/entity-transaction.v0.1.schema.json`.
- Snapshot v0.6 already stores complete dynamic entities and State cells, so no
  new snapshot fields or version are introduced. Legacy optional Entity fields
  and missing `static_entity_ids` retain the existing defaults/migration.
- Entity IDs, type/name strings, components and JSON metadata are checked before
  creation and restoration. Recipe/provenance metadata and lineage State cells
  round-trip as data; they do not become executable rules.
- Removing/replacing entities, allocating new IDs, creating through Action
  child graphs, and Grammar mutation are outside this create-only contract.

### Replay contract

Register the creator modules before Replay, using contracts that declare
`entity_transaction/v0.1`. Replay checks these bindings but never calls
`evaluate` or regenerates an object. Old logs do not contain a creator-version
receipt, so callers must pin the compatible package and module versions; this
is structural validation of the log, not an authenticity proof.

Each creation record must immediately follow its paired `state.committed`
record with matching source, target, causation, correlation and tick. Empty
StateDelta batches and parent-state changes remain valid. Unsupported versions,
operations, malformed entities, mismatched bindings and duplicate live entity
IDs are rejected. Snapshot restore rewinds membership, so a later legitimate
recreation after that boundary can reuse an ID.

Package-backed IDs remain reserved even after their live entity is removed;
create-only operations cannot repurpose those identities. Delayed creation
also rechecks that its actor still exists at execution time. A replaced actor
produces a failed Action lifecycle rather than an unreplayable successful
creation. These rules align live execution with Snapshot and Replay.

`EntityTransactionRuntime.replay` restores the entire input stream atomically
in memory. Failure restores StateStore, registry, dynamic membership, generated
player state, scheduler, pending Actions and EventBus halt observations while
preserving the StateStore/Scheduler objects used by adapters. Replay neither
publishes events nor appends them to a log.

For a durable restart, construct the Runtime with the existing EventLog path,
register modules, then call `runtime.replay(runtime.event_log.events)`. The
constructor loads the existing history; subsequent Actions append to that same
history. Replaying into an unrelated empty in-memory log does not implicitly
copy the source log. The example proves a second restart after continuation.

See [development progress](DEVELOPMENT_PROGRESS_zh-TW.md) for the verified build
and tests; this contract does not imply general CRDWS or RGGG completion.
