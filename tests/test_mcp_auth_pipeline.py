from __future__ import annotations

import unittest

from compilableworld_mcp import (
    BearerPrincipalResolver,
    HMACKeyRing,
    MCPWorldError,
    PrincipalJTIRevocationStore,
    PrincipalTokenCodec,
    RequestAuthContext,
    RequestSecurityError,
    RequestSecurityPipeline,
    RevocationCheckingPrincipalResolver,
    SessionTokenCodec,
    WorldACL,
)


class RequestSecurityPipelineTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        ring = HMACKeyRing({"k1": b"p" * 32}, active_kid="k1")
        self.principal_codec = PrincipalTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
            max_lifetime=900,
        )
        self.session_codec = SessionTokenCodec(
            ring,
            issuer="https://issuer.example",
            audience="compilableworld",
            max_lifetime=900,
        )
        self.principal = self.principal_codec.issue(
            user_id="user-1",
            client_id="client-1",
            roles=["player", "reviewer"],
            now=self.NOW,
            ttl_seconds=300,
            token_id="principal-1",
        )
        trusted = self.principal_codec.verify(self.principal, now=self.NOW)
        self.session = self.session_codec.issue(
            principal=trusted,
            session_id="session-1",
            world_id="gray-crown",
            runtime_instance_id="runtime-1",
            timeline_id="timeline-1",
            actor_id="player.newcomer",
            role="player",
            now=self.NOW,
            ttl_seconds=120,
            token_id="session-token-1",
        )
        self.context = RequestAuthContext(
            request_id="request-1",
            transport="HTTP",
            client_id="client-1",
            authorization=f"Bearer {self.principal}",
            session_token=self.session,
        )

    def test_dispatch_authenticates_only_host_context_and_restores_it(self) -> None:
        pipeline = RequestSecurityPipeline(
            RevocationCheckingPrincipalResolver(
                self.principal_codec,
                PrincipalJTIRevocationStore(),
            ),
            self.session_codec,
        )

        self.assertIsNone(pipeline.context_provider.current())
        with pipeline.dispatch(self.context, expected_world_id="gray-crown", now=self.NOW) as request:
            self.assertEqual(request.principal.user_id, "user-1")
            self.assertEqual(request.session.session_id, "session-1")
            self.assertEqual(request.safe_metadata()["principal_token_id"], "principal-1")
            rendered = repr(request.safe_metadata())
            self.assertNotIn(self.principal, rendered)
            self.assertNotIn(self.session, rendered)
        self.assertIsNone(pipeline.context_provider.current())

    def test_missing_context_and_credentials_fail_closed(self) -> None:
        pipeline = RequestSecurityPipeline(
            BearerPrincipalResolver(self.principal_codec),
            self.session_codec,
        )
        with self.assertRaisesRegex(RequestSecurityError, "context"):
            pipeline.authenticate()

        no_auth = RequestAuthContext(
            request_id="request-2",
            transport="stdio",
            client_id="client-1",
        )
        with self.assertRaisesRegex(RequestSecurityError, "authorization"):
            with pipeline.dispatch(no_auth, require_session=False):
                pass

        no_session = RequestAuthContext(
            request_id="request-3",
            transport="stdio",
            client_id="client-1",
            authorization=f"Bearer {self.principal}",
        )
        with self.assertRaisesRegex(RequestSecurityError, "session token"):
            with pipeline.dispatch(no_session, now=self.NOW):
                pass

    def test_client_scope_role_and_acl_are_verified(self) -> None:
        acl = WorldACL()
        acl.grant(
            "user-1",
            "gray-crown",
            roles=["player"],
            actor_ids=["player.newcomer"],
        )
        pipeline = RequestSecurityPipeline(
            BearerPrincipalResolver(self.principal_codec),
            self.session_codec,
            acl=acl,
        )
        with pipeline.dispatch(
            self.context,
            expected_world_id="gray-crown",
            expected_runtime_instance_id="runtime-1",
            expected_timeline_id="timeline-1",
            expected_actor_id="player.newcomer",
            expected_role="player",
            now=self.NOW,
        ) as request:
            self.assertEqual(request.session.world_id, "gray-crown")

        acl.revoke("user-1", "gray-crown")
        with self.assertRaisesRegex(MCPWorldError, "no grant"):
            with pipeline.dispatch(self.context, now=self.NOW):
                pass

    def test_revoked_principal_is_rejected_before_session_scope(self) -> None:
        store = PrincipalJTIRevocationStore()
        store.revoke("principal-1", expires_at=self.NOW + 100, now=self.NOW)
        pipeline = RequestSecurityPipeline(
            RevocationCheckingPrincipalResolver(self.principal_codec, store),
            self.session_codec,
        )
        with self.assertRaisesRegex(RequestSecurityError, "revoked"):
            with pipeline.dispatch(self.context, now=self.NOW):
                pass


if __name__ == "__main__":
    unittest.main()
