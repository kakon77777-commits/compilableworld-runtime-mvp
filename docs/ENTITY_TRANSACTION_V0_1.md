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
- The existing base `WorldRuntime` remains unchanged.
- Existing positional `TransitionResult(True, deltas, events, message)` remains source-compatible because `entity_deltas` is appended after `message`.
