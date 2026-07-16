# MCP Rehydration M12 Local Slice

This document records the explicit local restart boundary for MCP sessions and
runtime ownership.

## Implemented

- `SessionLifecycleStore` persists the server-side session scope without raw
  Principal or Session JTIs and can enumerate only active records.
- `SecureReadOnlyMCPGateway.rehydrate_sessions()` restores those active
  records into a newly constructed `ReadOnlyWorldService`.
- `RuntimeBindingStore` persists enabled package/event-log/snapshot startup
  bindings, and `ReadOnlyWorldService.rehydrate_from_binding_store()` loads
  them explicitly.
- `EventLog` reloads its JSONL history on Runtime startup and rejects malformed
  or duplicate event records instead of silently losing replay history.
- Rehydrated sessions preserve world, runtime instance, actor, role, client,
  user, and optional model metadata.
- `RuntimeOwnershipLeaseStore.recover()` supports explicit same-owner recovery
  of an unexpired local/SQLite lease and rotates the opaque lease credential.
- `ReadOnlyWorldService.register_package()` and `register_runtime()` expose
  `recover_ownership=True` for that host restart path.

## Restart sequence

1. Construct the binding store, service, and ownership store with the same
   local databases and stable
   `ownership_owner_id`.
2. Call `rehydrate_from_binding_store()` using the enabled binding records;
   this loads package, EventLog, and optional snapshot data.
3. Use `recover_ownership=True` when the previous lease may still be active.
4. Construct the gateway with the same session lifecycle database and signing
   policy.
5. Call `rehydrate_sessions()` before serving requests.

The package path and runtime snapshot remain host startup configuration. The
SQLite stores do not guess which package should be loaded, and rehydration
never mutates World Kernel state.

## Boundary still explicit

- Recovery is local/SQLite and same-owner only; it is not a distributed lock
  protocol or leader-election system.
- A later Runtime host can persist package manifests, snapshot selection, and
  Kernel/outbox commits in one authoritative store.

## Verification

`tests/test_mcp_secure_gateway.py` covers SQLite session rehydration across a
new service/gateway instance. `tests/test_mcp_coordination.py` covers same-owner
lease recovery and hostile-owner rejection.
