# MCP Security Pipeline — Local M10 Slice

This document records the local, transport-neutral M10 slice. The later M12
deployment and rehydration documents describe the host adapters and restart
path built on top of this pipeline.

## Implemented boundary

`RequestSecurityPipeline` authenticates a dispatch only after a trusted Host
binds `RequestAuthContext`. The pipeline then:

1. resolves the strict `Bearer` Principal token using the trusted transport
   `client_id`;
2. applies the configured Principal JTI revocation resolver;
3. verifies the Principal-bound Session token and its world/runtime/timeline/
   actor/role scope;
4. requires the Session role to be present in the Principal roles; and
5. applies the optional server-side `WorldACL`.

`dispatch()` restores the previous `ContextVar` binding in `finally`. Tool
arguments are not accepted by the pipeline as an authentication source, so
the model cannot supply or override credentials through Tool JSON.

## Explicitly pending

- SSE host policy and external process supervision remain deployment-specific;
- external identity-provider claim mapping beyond the local OIDC discovery,
  JWKS, and RS256 verifier;
- persistent server-side Session lifecycle store, tombstones, rotation, and
  session revocation are implemented locally, including an SQLite store;
  explicit service rehydration is documented in
  `MCP_REHYDRATION_M12_LOCAL_SLICE.md`;
- distributed rate limiting and an atomic World Kernel plus outbox
  transaction. The local action gateway now provides local/SQLite-shared rate limiting, Session
  idempotency reservation, post-submit outbox delivery, and actor-bound
  `submit_action`;
- distributed runtime ownership remains pending. A local explicit migration
  registry and process-local/SQLite ownership lease store with same-owner
  recovery now exist as separate coordination boundaries.

The read-only MCP service remains backwards compatible when no ACL is passed.
All local security slices are covered by the Runtime test suite.
