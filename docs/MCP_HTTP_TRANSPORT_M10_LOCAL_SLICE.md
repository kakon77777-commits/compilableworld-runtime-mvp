# MCP HTTP Transport — Local M10 Slice

`HTTPRequestContextAdapter` is the first concrete transport adapter for the
local security pipeline.

## Boundary

- The server supplies `trusted_client_id` from its configured connection or
  identity mapping.
- `Authorization` is read as an opaque Bearer credential.
- `X-CompilableWorld-Session` is read as an opaque session credential.
- Header names are matched case-insensitively.
- `request_id` and optional peer metadata are supplied by the HTTP host.
- Verification and ACL decisions are delegated to `RequestSecurityPipeline`.

The adapter deliberately ignores a client-provided `X-CW-Client-ID` header.
The HTTP client cannot change the identity against which the Principal token
is verified.

## Still pending

`ASGIAuthMiddleware` now wires this context adapter into a real ASGI ingress,
and `OIDCDiscoveryClient`／`OIDCPrincipalResolver` provide the local OIDC
discovery/JWKS and RS256 boundary. Streamable HTTP host wiring, TLS
termination, SSE/stdio adapters, rate limits, and action reservation remain
deployment-specific. Session lifecycle rotation is implemented by the secure
gateway and is not implied merely by the presence of this header adapter.
