from __future__ import annotations

import unittest

from compilableworld_mcp import (
    BearerPrincipalResolver,
    HMACKeyRing,
    HTTPRequestContextAdapter,
    PrincipalTokenCodec,
    RequestSecurityError,
    RequestSecurityPipeline,
    SessionTokenCodec,
)


class HTTPRequestContextAdapterTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        ring = HMACKeyRing({"k1": b"h" * 32}, active_kid="k1")
        self.principal_codec = PrincipalTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        self.session_codec = SessionTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
        )
        principal_token = self.principal_codec.issue(
            user_id="user-1",
            client_id="trusted-http-client",
            roles=["player"],
            now=self.NOW,
            ttl_seconds=300,
            token_id="principal-http-1",
        )
        principal = self.principal_codec.verify(principal_token, now=self.NOW)
        session_token = self.session_codec.issue(
            principal=principal,
            session_id="session-http-1",
            world_id="gray-crown",
            runtime_instance_id="runtime-http-1",
            timeline_id="timeline-http-1",
            actor_id="player.newcomer",
            role="player",
            now=self.NOW,
            ttl_seconds=120,
            token_id="session-http-token-1",
        )
        self.headers = {
            "authorization": f"Bearer {principal_token}",
            "x-compilableworld-session": session_token,
        }
        self.adapter = HTTPRequestContextAdapter(
            RequestSecurityPipeline(
                BearerPrincipalResolver(self.principal_codec),
                self.session_codec,
            ),
            trusted_client_id="trusted-http-client",
        )

    def test_header_extraction_is_case_insensitive_and_dispatch_verifies(self) -> None:
        context = self.adapter.context_from_headers(
            self.headers,
            request_id="http-request-1",
            peer="127.0.0.1",
        )
        self.assertEqual(context.transport, "http")
        self.assertEqual(context.client_id, "trusted-http-client")
        self.assertTrue(context.safe_metadata()["authorization_present"])
        with self.adapter.dispatch(
            self.headers,
            request_id="http-request-1",
            peer="127.0.0.1",
            expected_world_id="gray-crown",
            now=self.NOW,
        ) as request:
            self.assertEqual(request.session.session_id, "session-http-1")

    def test_client_id_is_host_supplied_not_taken_from_headers(self) -> None:
        headers = dict(self.headers)
        headers["X-CW-Client-ID"] = "attacker-controlled"
        with self.adapter.dispatch(headers, request_id="http-request-2", now=self.NOW):
            pass

        wrong_adapter = HTTPRequestContextAdapter(
            RequestSecurityPipeline(
                BearerPrincipalResolver(self.principal_codec),
                self.session_codec,
            ),
            trusted_client_id="wrong-client",
        )
        with self.assertRaisesRegex(RequestSecurityError, "client"):
            with wrong_adapter.dispatch(self.headers, request_id="http-request-3", now=self.NOW):
                pass

    def test_missing_headers_and_invalid_host_metadata_fail_closed(self) -> None:
        with self.assertRaisesRegex(RequestSecurityError, "client_id"):
            HTTPRequestContextAdapter(
                RequestSecurityPipeline(
                    BearerPrincipalResolver(self.principal_codec),
                    self.session_codec,
                ),
                trusted_client_id=" ",
            )

        with self.assertRaisesRegex(RequestSecurityError, "authorization"):
            with self.adapter.dispatch({}, request_id="http-request-4", require_session=False, now=self.NOW):
                pass

        with self.assertRaisesRegex(RequestSecurityError, "session token"):
            with self.adapter.dispatch(
                {"Authorization": self.headers["authorization"]},
                request_id="http-request-5",
                now=self.NOW,
            ):
                pass


if __name__ == "__main__":
    unittest.main()
