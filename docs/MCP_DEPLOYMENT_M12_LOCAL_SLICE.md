# MCP Deployment M12 Local Slice

This document records the real-host security boundary now available in the
Runtime MVP.

The optional host environment can install the deployment dependencies with
`pip install -e ".[mcp-host]"`; the default Runtime install remains
dependency-free.

## Implemented

- `ASGIAuthMiddleware` extracts HTTP headers into the existing opaque request
  context and authenticates the Principal before invoking the application.
- The trusted client ID comes from host configuration or a host callback; it
  is never taken from a client header.
- The middleware exposes the safe `RequestAuthContext` through ASGI scope
  state for downstream routing.
- Authentication failures return versioned JSON responses with 401/403/429
  status mapping and no credential values.
- `OIDCDiscoveryClient` validates one configured HTTPS issuer and caches its
  discovery document and JWKS.
- `OIDCPrincipalResolver` verifies RS256 signatures without adding PyJWT or
  cryptography as mandatory Runtime dependencies, then validates issuer,
  audience, `iat`/`nbf`/`exp`, `jti`, user, and roles claims.
- `build_secure_mcp_streamable_http_app` creates the official FastMCP v1.x
  `streamable_http_app()` and wraps it with the ASGI Principal gate.
- `SecureMCPHostSettings` and `serve_secure_mcp_streamable_http` centralize
  host/port/path/TLS settings and lazily hand the app to Uvicorn.
- TLS is required by default; plaintext mode is explicitly restricted to
  localhost development.
- stdio hosts can use `StdioContextAdapter` or the FastMCP stdio credential
  provider, while still keeping credentials outside tool arguments.
- `cw-mcp-readonly` can start from package arguments or an enabled SQLite
  `RuntimeBindingStore`, with optional same-owner recovery and ownership
  heartbeat flags.
- `RuntimeCoordinationASGIApp` provides an authenticated host control plane for
  centralized ownership acquire/recover/renew/release operations.

## Boundary still explicit

- This is the ASGI ingress boundary; process supervision and TLS termination
  still depend on the chosen ASGI host.
- Only RS256 is accepted by the dependency-free OIDC verifier. Other OIDC
  algorithms require a separately audited provider adapter.
- SSE/stdio host adapters, distributed JWKS invalidation, and external
  identity-provider claim mapping remain deployment policy.

## Verification

`tests/test_mcp_deployment.py` covers ASGI authentication responses, context
injection, OIDC discovery/JWKS caching, RS256 verification, and claim failure
paths. `tests/test_mcp_host.py` covers TLS policy and Uvicorn host settings.
