# FastMCP Context Adapter — Local M10 Slice

The optional FastMCP v1.x SDK injects a `Context` into tools. Its underlying
request is available at `ctx.request_context.request` for transports that
carry an HTTP request. `FastMCPContextAdapter` bridges that request to the
dependency-free CompilableWorld security pipeline without importing the SDK at
module load time.

## Security boundary

- reads `request.headers` only for opaque `Authorization` and session values;
- uses the server-configured `trusted_client_id`;
- ignores the SDK convenience `ctx.client_id`, because it is derived from MCP
  request metadata rather than the trusted HTTP identity source;
- fails closed for stdio or contexts without an HTTP request;
- restores the request context after dispatch through the existing pipeline.
- returns the issued Session token through MCP `CallToolResult._meta`, while
  leaving it out of visible `content` and `structuredContent`.

This is an adapter contract, not a complete FastMCP server authentication
deployment. `secure_gateway.py` and `secure_server.py` now provide the
explicit secure tool facade and server-side session-token issuance boundary;
the optional SDK must still be installed to run the actual FastMCP process.
