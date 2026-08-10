# MCP Action Commit Journal M12 Local Slice

This document records the crash-recovery protocol between the authoritative
World Kernel and the MCP outbox.

## Implemented

- `ActionCommitJournalStore.prepare()` records the action identity before the
  Runtime submit.
- `record_runtime_committed()` persists the Runtime result after Kernel
  execution.
- `mark_outbox_enqueued()` closes the local handoff once the outbox accepts the
  receipt.
- `pending_delivery()` finds Runtime-committed entries that still need
  delivery.
- `recover_outbox()` re-enqueues those entries with the deterministic
  `action:<action_id>` dedupe key and can finalize a still-reserved
  `ActionReservationStore` record.
- `SecureActionMCPGateway` uses the journal on every guarded action.
- `EventLog.append_batch()` writes an action's emitted events as one durable
  batch (`flush`/`fsync`) before updating the in-memory log projection.
- `WorldRuntime` restores its state snapshot when that durable Kernel event
  commit fails, so a failed event-log write cannot leave a partial action
  state behind.
- `record_runtime_and_enqueue_outbox()` can atomically persist the Runtime
  result, outbox row, and journal completion when both stores share one SQLite
  database; deterministic action dedupe remains in force.
- `RuntimeDurabilityStore` can persist the corresponding Runtime state/event
  projection beside those recovery records, with a hash that can be verified
  after restart.

## Boundary still explicit

The Runtime Kernel state/event-log pair now has a local transaction boundary.
When journal and outbox share SQLite, the post-Kernel durable handoff is one
transaction; when they use different stores, a process crash between those
writes remains recoverable through the journal. The Kernel state/event-log
write and outbox handoff are still not one end-to-end ACID transaction, and
EventBus subscribers are downstream of the durable Kernel commit. Distributed
commit and consensus remain deployment-level work.

## Verification

`tests/test_runtime.py` covers rollback when the durable Kernel event commit
fails. `tests/test_mcp_action_control.py` covers SQLite journal persistence,
shared-database atomic handoff, rollback on outbox failure, post-submit
recovery, and normal gateway phase completion.
