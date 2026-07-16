from __future__ import annotations

from dataclasses import dataclass
import unittest

from compilableworld_mcp import (
    BearerPrincipalResolver,
    FastMCPContextAdapter,
    HMACKeyRing,
    PrincipalTokenCodec,
    RequestSecurityError,
    RequestSecurityPipeline,
    SessionTokenCodec,
)


@dataclass
class _Client:
    host: str


@dataclass
class _Request:
    headers: dict[str, str]
    client: _Client


@dataclass
class _RequestContext:
    request: _Request | None


@dataclass
class _FastMCPContext:
    request_id: str
    request_context: _RequestContext
    client_id: str | None = "model-controlled-meta"


class FastMCPContextAdapterTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        ring = HMACKeyRing({"k1": b"f" * 32}, active_kid="k1")
        principal_codec = PrincipalTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        session_codec = SessionTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        principal_token = principal_codec.issue(
            user_id="user-1",
            client_id="trusted-fastmcp-client",
            roles=["player"],
            now=self.NOW,
            ttl_seconds=300,
            token_id="principal-fastmcp-1",
        )
        principal = principal_codec.verify(principal_token, now=self.NOW)
        session_token = session_codec.issue(
            principal=principal,
            session_id="session-fastmcp-1",
            world_id="gray-crown",
            runtime_instance_id="runtime-fastmcp-1",
            timeline_id="timeline-fastmcp-1",
            actor_id="player.newcomer",
            role="player",
            now=self.NOW,
            ttl_seconds=120,
            token_id="session-fastmcp-token-1",
        )
        self.context = _FastMCPContext(
            request_id="fastmcp-request-1",
            request_context=_RequestContext(
                request=_Request(
                    headers={
                        "Authorization": f"Bearer {principal_token}",
                        "X-CompilableWorld-Session": session_token,
                    },
                    client=_Client("127.0.0.1"),
                )
            ),
        )
        self.adapter = FastMCPContextAdapter(
            RequestSecurityPipeline(
                BearerPrincipalResolver(principal_codec),
                session_codec,
            ),
            trusted_client_id="trusted-fastmcp-client",
        )

    def test_fastmcp_context_uses_http_headers_and_ignores_meta_client_id(self) -> None:
        context = self.adapter.context_from_fastmcp(self.context)
        self.assertEqual(context.request_id, "fastmcp-request-1")
        self.assertEqual(context.peer, "127.0.0.1")
        self.assertEqual(context.client_id, "trusted-fastmcp-client")
        with self.adapter.dispatch(
            self.context,
            expected_world_id="gray-crown",
            now=self.NOW,
        ) as request:
            self.assertEqual(request.session.session_id, "session-fastmcp-1")

    def test_stdio_or_missing_http_request_fails_closed(self) -> None:
        context = _FastMCPContext(
            request_id="fastmcp-request-2",
            request_context=_RequestContext(request=None),
        )
        with self.assertRaisesRegex(RequestSecurityError, "HTTP request"):
            self.adapter.context_from_fastmcp(context)

    def test_missing_request_id_and_headers_fail_closed(self) -> None:
        context = _FastMCPContext(
            request_id="",
            request_context=_RequestContext(
                request=_Request(headers={}, client=_Client("127.0.0.1"))
            ),
        )
        with self.assertRaisesRegex(RequestSecurityError, "request_id"):
            self.adapter.context_from_fastmcp(context)


if __name__ == "__main__":
    unittest.main()
