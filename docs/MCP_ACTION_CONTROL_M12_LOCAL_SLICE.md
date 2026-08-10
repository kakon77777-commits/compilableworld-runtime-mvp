# MCP Action Control M12 Local Slice

This document records the first guarded write path for the Runtime MVP.

## Implemented

- `SecureActionMCPGateway.submit_action` authenticates the existing Principal
  and Session before touching the Runtime.
- The action actor is always taken from the live Session. A client-supplied
  actor ID must match it and cannot switch actors.
- Action payloads are limited to `verb`, `target_id`, `args`, and an optional
  matching `actor_id`; arbitrary ActionIR authority or IDs cannot be supplied
  by the client.
- `SlidingWindowRateLimiter` applies a per-user/world action limit.
- `ActionReservationStore` scopes idempotency keys to a Session, detects
  fingerprint conflicts, and replays completed or failed results.
- `TransactionalOutbox` provides durable/process-local enqueue, worker claim,
  retry, and ack transitions.
- `ActionCommitJournalStore` records `prepared`, `runtime_committed`, and
  `outbox_enqueued` phases, with SQLite recovery for a Kernel-committed action
  whose delivery enqueue was interrupted.
- Optional `RuntimeDurabilityStore` records a restart-verifiable state snapshot
  and event batch projection for each committed action, including a state hash
  and event IDs in the action result metadata.
- `secure_server.build_secure_mcp_server(..., action_gateway=...)` exposes the
  action tool only when the host explicitly opts into the write facade.

## Important boundary

The Runtime Kernel remains the only state authority. The current MVP Runtime
does not have a database transaction that atomically commits World Kernel
state and the outbox row. The journal is therefore a durable recovery
protocol, not a replacement for a single atomic Kernel/outbox transaction.
The durability store is likewise a recovery projection; a projection failure
is surfaced in metadata and does not silently change the Kernel result.
The later authoritative store can move both operations into one transaction
without changing the MCP action contract.

## Verification

`tests/test_mcp_action_control.py` covers rate limiting, SQLite idempotency,
actor binding, replay, commit-journal recovery, runtime durability projection,
and outbox worker transitions.
