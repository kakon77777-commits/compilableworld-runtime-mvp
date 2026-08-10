# MCP M12 Distributed Deployment Boundary

This document is the integration contract for the three guarantees that
cannot be completed honestly by process-local code alone.

## 1. Consensus authority

The current `RuntimeQuorumGate` is a fail-closed vote threshold around the
fenced leader lease. A production authority must additionally provide:

- a replicated log or equivalent linearizable decision record;
- term monotonicity across restarts and network partitions;
- failure detection and leader replacement rules;
- an explicit membership-change protocol;
- a quorum proof bound to the candidate and fencing token.

The authenticated coordination API can remain the host-facing contract. The
external authority must return a decision containing the term, candidate,
member set, quorum proof, and fencing token, or fail closed.

## 2. Independent audit anchoring

The local `AuditStore.create_anchor()` and `verify_anchor()` provide a
restart-verifiable local chain checkpoint. A deployment-grade anchor service
must independently receive the anchor contract, hash, record range, and
creation time, then return a publisher identity, external reference, and
verifiable signature or equivalent immutable receipt.

The Runtime must not treat a local copy of its own anchor as independent
publication. If the external publisher is unavailable, the result is
`delivery_pending` or fail-closed according to the deployment policy.

## 3. End-to-end ACID runtime commit

The current boundary is deliberately layered:

- Kernel state and file-backed EventLog have local rollback protection;
- the action journal and shared SQLite outbox handoff are atomic after the
  Kernel commit;
- `RuntimeDurabilityStore` keeps a restart-verifiable state/event projection.

The production authoritative store must move Kernel state, EventLog, action
journal, and outbox into one transaction coordinator, or provide an
equivalent proven atomic commit protocol. A projection or recovery journal
alone is not sufficient evidence of end-to-end ACID behavior.

## Integration acceptance

The integration is complete only when an external deployment demonstrates:

1. two coordinator failures and a partition without split-brain leadership;
2. an audit anchor verified outside the Runtime process;
3. crash injection at every Kernel/journal/outbox boundary with no lost or
   duplicated committed action;
4. the existing Runtime/MCP regression suite remains green.
