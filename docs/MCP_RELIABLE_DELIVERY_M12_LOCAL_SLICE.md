# MCP Reliable Delivery M12 Local Slice

This document records the recovery boundary between the authoritative Runtime
EventLog and the MCP outbox.

## Implemented

- `RuntimeEventOutboxBridge` scans Runtime EventLog entries in order.
- Each event uses a runtime-scoped dedupe key, so a restarted bridge can
  safely replay from cursor zero without creating duplicate outbox records.
- The existing outbox worker claim/retry/ack transitions remain the only
  delivery state machine.
- SQLite outbox initialization migrates older tables by adding the dedupe
  column and unique partial index.
- `ActionCommitJournalStore` durably records the Kernel-to-outbox handoff and
  can replay runtime-committed receipts into the deduplicating outbox after a
  host restart.
- `StdioContextAdapter` and FastMCP stdio fallback bind host-provided opaque
  credentials through the same security pipeline.

## Boundary still explicit

The bridge and action journal are recoverable delivery, not a database
transaction spanning the in-memory World Kernel and outbox. A later
authoritative Runtime store can commit state and outbox rows atomically while
retaining this event contract.

## Verification

`tests/test_mcp_event_outbox.py` covers replay and runtime-scoped dedupe;
`tests/test_mcp_stdio.py` covers trusted stdio identity and fail-closed
fallback behavior.
