# MCP Runtime Coordination M12 Production Boundary

This document records the first centralized coordination control plane beyond
same-host SQLite sharing.

## Implemented

- `RuntimeCoordinationGateway` binds acquire, same-owner recover, renew, and
  release to an authenticated Principal with the configured `admin` role.
- The owner identity is taken from the verified Principal `user_id`; it is not
  accepted as a client-supplied ownership field.
- `RuntimeCoordinationASGIApp` exposes POST endpoints under
  `/v1/runtime-ownership/*` and is intended to sit behind
  `ASGIAuthMiddleware`.
- Lease credentials are returned only through this authenticated host control
  plane. They are not MCP tool arguments or read-only world projections.
- Acquire and recovery responses carry a monotonic fencing token so Runtime
  consumers can reject stale-owner operations after takeover.
- The coordination store exposes a single fenced leader lease for the host
  control plane, so two admin hosts cannot both become the active coordinator
  for the same shared store.
- An optional `RuntimeQuorumGate` can require a configured majority (or explicit
  quorum size) before a candidate may acquire that leader lease. Terms and
  member votes can use the same SQLite store across host processes.
- The same `RuntimeOwnershipLeaseStore` can remain SQLite-backed for one host
  cluster or be replaced by a service-local backend behind this gateway.

## Endpoints

- `POST /v1/runtime-ownership/acquire`
- `POST /v1/runtime-ownership/recover`
- `POST /v1/runtime-ownership/renew`
- `POST /v1/runtime-ownership/release`
- `POST /v1/runtime-ownership/leader/acquire`
- `POST /v1/runtime-ownership/leader/recover`
- `POST /v1/runtime-ownership/leader/renew`
- `POST /v1/runtime-ownership/leader/release`
- `POST /v1/runtime-ownership/leader/term`
- `POST /v1/runtime-ownership/leader/vote`
- `POST /v1/runtime-ownership/leader/quorum`

## Boundary still explicit

The quorum gate is a fail-closed vote threshold around the existing fenced
leader lease. It is not Raft/Paxos consensus: there is no replicated log,
failure detector, membership-change protocol, or independently durable quorum
authority yet. The coordinator host and the distributed backend remain
deployment responsibilities; a later service can replace the gate/store
behind the authenticated endpoint contract.

The required production acceptance conditions are listed in
`MCP_M12_DISTRIBUTED_DEPLOYMENT_BOUNDARY.md`.

## Verification

`tests/test_mcp_runtime_coordination.py` covers Principal-bound owner identity,
lease lifecycle, fenced single-leader takeover, optional quorum-gated leader
acquisition, hostile-owner rejection, and ASGI acquire/renew dispatch.
