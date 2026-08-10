from __future__ import annotations

import time
import types
import unittest

from compilableworld_mcp import (
    BearerPrincipalResolver,
    FastMCPContextAdapter,
    HMACKeyRing,
    PrincipalTokenCodec,
    RequestSecurityError,
    RequestSecurityPipeline,
    StdioContextAdapter,
)


class StdioTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = int(time.time())
        ring = HMACKeyRing({"k1": b"s" * 32}, active_kid="k1")
        principal_codec = PrincipalTokenCodec(ring, issuer="https://issuer.example", audience="compilableworld")
        self.session_codec = __import__("compilableworld_mcp", fromlist=["SessionTokenCodec"]).SessionTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        principal = principal_codec.issue(
            user_id="stdio-user",
            client_id="stdio-host",
            roles=["player"],
            now=self.now,
            ttl_seconds=300,
            token_id="principal-stdio-1",
        )
        self.authorization = f"Bearer {principal}"
        self.pipeline = RequestSecurityPipeline(
            BearerPrincipalResolver(principal_codec),
            self.session_codec,
        )

    def test_stdio_adapter_binds_host_credentials_without_tool_arguments(self) -> None:
        adapter = StdioContextAdapter(
            self.pipeline,
            trusted_client_id="stdio-host",
            authorization=self.authorization,
        )
        with adapter.dispatch("stdio-request-1", require_session=False, now=self.now) as request:
            self.assertEqual(request.context.transport, "stdio")
            self.assertEqual(request.principal.user_id, "stdio-user")

    def test_fastmcp_adapter_falls_back_to_trusted_stdio_provider(self) -> None:
        adapter = FastMCPContextAdapter(
            self.pipeline,
            trusted_client_id="stdio-host",
            stdio_credentials=lambda _: (self.authorization, None),
        )
        context = types.SimpleNamespace(request_id="stdio-request-2", request_context=None)
        request_context = adapter.context_from_fastmcp(context)
        self.assertEqual(request_context.transport, "stdio")
        self.assertTrue(request_context.safe_metadata()["authorization_present"])

    def test_stdio_without_host_provider_fails_closed(self) -> None:
        adapter = FastMCPContextAdapter(self.pipeline, trusted_client_id="stdio-host")
        context = types.SimpleNamespace(request_id="stdio-request-3", request_context=None)
        with self.assertRaisesRegex(RequestSecurityError, "no HTTP request"):
            adapter.context_from_fastmcp(context)


if __name__ == "__main__":
    unittest.main()
