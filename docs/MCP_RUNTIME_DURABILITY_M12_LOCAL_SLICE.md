# MCP Runtime Durability M12 Local Slice

This document records the restart-verifiable Runtime projection used beside
the MCP action recovery journal.

## Implemented

- `RuntimeDurabilityStore` stores a JSON-safe state snapshot and event batch by
  `(runtime_instance_id, action_id)`.
- SQLite records are idempotent for the same action identity and reject a
  conflicting second projection.
- A SHA-256 state hash is returned in safe metadata and checked again when the
  projection is loaded after restart.
- `SecureActionMCPGateway` can attach the projection metadata to action results
  through the optional `durability_store` dependency.

## Boundary still explicit

This is a recovery projection, not a second World Kernel authority. It does
not make the in-memory Kernel state, file-backed EventLog, action journal, and
outbox one ACID transaction. Projection failure is visible in the result
metadata while the Kernel result remains authoritative. A later authoritative
runtime store can replace this adapter without changing the MCP action
contract.

## Verification

`tests/test_mcp_runtime_durability.py` covers SQLite restart recovery,
idempotency, projection conflict, and tamper detection. The action-control
suite covers gateway integration and event-ID continuity.
