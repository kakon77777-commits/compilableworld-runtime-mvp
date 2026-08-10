# MCP Runtime Quorum M12 Local Slice

This document records the bounded quorum primitive added around the Runtime
coordination leader lease.

## Implemented

- `RuntimeQuorumGate` validates a fixed member set and computes a majority by
  default, or an explicit quorum size when configured.
- A term has one candidate and at most one vote per configured member.
- Duplicate votes are idempotent; unknown members, missing terms, membership
  drift, and candidate mismatches fail closed.
- Terms and votes can be stored in SQLite and survive a process restart.
- `RuntimeCoordinationGateway` exposes authenticated term, vote, and quorum
  endpoints, and requires a reached quorum before leader acquisition when a
  gate is configured.

## Boundary still explicit

This is a fail-closed vote threshold, not a consensus implementation. It does
not provide a replicated log, leader election algorithm, failure detector,
automatic membership changes, network partition handling, or an independent
quorum authority. Those guarantees require a real distributed coordination
service or a proven protocol implementation behind the same authenticated
control-plane boundary.

## Verification

`tests/test_mcp_runtime_quorum.py` covers majority behavior, idempotent votes,
SQLite restart recovery, and membership drift. The coordination suite covers
the gateway-level requirement that a leader cannot be acquired before quorum.
