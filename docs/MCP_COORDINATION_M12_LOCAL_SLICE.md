# MCP Coordination M12 Local Slice

This document records the local M12 coordination boundary for the
CompilableWorld Runtime MVP.

## Implemented

- `MigrationRegistry` registers named, explicit migration steps.
- Migration paths are found deterministically and can contain multiple
  version hops.
- Migration transforms receive a deep copy, so the caller's payload is not
  mutated by the registry.
- `RuntimeOwnershipLeaseStore` provides exclusive ownership for a
  `(world_id, runtime_instance_id)` pair.
- Ownership leases support acquire, require, renew, release, expiry, prune,
  explicit same-owner recovery, process-local storage, and SQLite persistence.
- `RuntimeOwnershipHeartbeat` provides host lifecycle renewal and graceful
  release for an acquired lease.
- `ReadOnlyWorldService` exposes start/stop heartbeat methods and `close()` so
  a host can bind lease lifecycle to its service lifecycle.
- Lease IDs are opaque and SQLite stores only their SHA-256 hashes.
- Acquire/recovery grants carry a monotonic fencing token; stale grants fail
  closed even when an owner identity is otherwise valid.
- The authenticated coordination gateway exposes a single fenced leader lease
-  for the shared coordination store.
- Optional `RuntimeQuorumGate` terms and member votes can be persisted in the
  same SQLite store, and leader acquisition fails closed until the configured
  quorum is reached.
- `SlidingWindowRateLimiter` can use a SQLite-backed shared window for local
  host processes that point at the same database.
- `SessionLifecycleStore.active_records()` exposes only active lifecycle
  metadata for an explicit post-restart service rehydration.
- `ReadOnlyWorldService.rehydrate_sessions()` restores those sessions after
  the host has re-registered the corresponding runtimes.
- `RuntimeBindingStore` persists the local package/EventLog/snapshot startup
  mapping used by `ReadOnlyWorldService.rehydrate_from_binding_store()`.
- Ownership coordination does not write World Kernel state and does not
  decide migration semantics.

## Boundary still explicit

- The existing Kernel snapshot loader still owns its v0.1/v0.2 compatibility
  path; the generic registry is available for MCP/package/event adapters but
  is not silently injected into snapshot loading.
- Rehydration does not discover package paths or silently load runtimes: the
  host must register each package/runtime first, then call the explicit
  rehydration API.
- The quorum gate is only a vote threshold; full distributed consensus,
  failure detection, and membership changes remain deployment work.
- A distributed database/lock service and distributed rate limiter remain
  separate deployment work packages; the local action reservation,
  idempotency ledger, and transactional outbox slices are documented in their
  own M12 contracts.

## Verification

The coordination slice is covered by `tests/test_mcp_coordination.py`.
