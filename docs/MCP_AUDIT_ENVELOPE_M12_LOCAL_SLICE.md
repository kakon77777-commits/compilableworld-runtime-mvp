# MCP Audit Envelope M12 Local Slice

This document records the safe per-request audit projection shared by the
authenticated MCP read and action gateways.

## Implemented

- `MCPAuditEnvelope` records request, transport, Principal, session, world,
  runtime, actor, operation, outcome, state-change, event, idempotency, and
  delivery-pending metadata.
- Read-only session/world operations attach an audit envelope to their
  response.
- Action submit and idempotent replay attach distinct `action.submit` and
  `action.replay` envelopes.
- The envelope never contains authorization values, session tokens, or action
  arguments.
- `AuditStore` provides process-local or SQLite append/query persistence, and
  gateways can mark `audit_id`／`audit_persisted` without making audit storage
  authoritative over a completed world action.
- Each store maintains a SHA-256 hash chain; startup and append verify prior
  records, and direct record tampering fails closed.
- `create_anchor()` records a checkpoint hash, chain head, range, and record
  count; `verify_anchor()` validates that checkpoint after a store restart.

## Boundary still explicit

The local SQLite sink is tamper-evident within one store, but its checkpoint
is not yet independently published or signed by a distributed audit service,
and cross-host query is still pending. Host deployments still need to forward
it according to their operational retention policy.
The external acceptance contract is recorded in
`MCP_M12_DISTRIBUTED_DEPLOYMENT_BOUNDARY.md`.

## Verification

`tests/test_mcp_secure_gateway.py` and `tests/test_mcp_action_control.py`
cover session/status/action/replay attachment and token non-disclosure.
