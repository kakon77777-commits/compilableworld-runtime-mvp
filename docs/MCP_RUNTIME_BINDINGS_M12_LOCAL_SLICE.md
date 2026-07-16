# MCP Runtime Bindings M12 Local Slice

This document records the host startup registry used by the Runtime MVP.

## Implemented

- `RuntimeBindingRecord` names one `(world_id, runtime_instance_id)` and its
  package, optional JSONL EventLog, and optional snapshot paths.
- `RuntimeBindingStore` supports process-local and SQLite persistence,
  deterministic enabled-record ordering, revisioned updates, and safe metadata
  that does not expose local filesystem paths.
- `ReadOnlyWorldService.rehydrate_from_binding_store()` loads enabled bindings,
  validates package world IDs, restores EventLog history and optional snapshots,
  then registers the runtimes.
- EventLog startup parsing is fail-closed for malformed JSON, invalid event
  shapes, and duplicate event IDs.

## Boundary still explicit

The registry is a local host startup configuration store. It is not service
discovery, leader election, a distributed lock, or a cloud package registry.
The ownership heartbeat only renews the lease supplied by the configured
backend; it does not elect a leader. The host still owns path permissions and
decides when to call rehydration.

## Verification

`tests/test_mcp_runtime_bindings.py` covers EventLog restart replay and SQLite
binding-driven package/snapshot rehydration.
