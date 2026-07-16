from __future__ import annotations

import base64
import json
import unittest

from compilableworld_mcp.request_security import RequestSecurityError
from compilableworld_mcp.security import (
    BearerPrincipalResolver,
    HMACKeyRing,
    PrincipalTokenCodec,
    SessionTokenCodec,
)


class SecurityTokenTests(unittest.TestCase):
    NOW = 1_700_000_000

    def setUp(self) -> None:
        self.keys = HMACKeyRing(
            {"k1": b"a" * 32, "k0": b"b" * 32},
            active_kid="k1",
        )
        self.principal_codec = PrincipalTokenCodec(
            self.keys,
            issuer="compilableworld-host",
            audience="compilableworld-mcp",
            max_lifetime=900,
        )
        self.session_codec = SessionTokenCodec(
            self.keys,
            issuer="compilableworld-host",
            audience="compilableworld-mcp",
            max_lifetime=900,
        )

    def _principal(self, *, ttl_seconds: int = 300) -> tuple[str, object]:
        token = self.principal_codec.issue(
            user_id="user-1",
            client_id="studio",
            roles=["player", "reviewer"],
            ttl_seconds=ttl_seconds,
            now=self.NOW,
        )
        return token, self.principal_codec.verify(token, expected_client_id="studio", now=self.NOW + 1)

    def test_principal_round_trip_and_bearer_resolution(self) -> None:
        token, principal = self._principal()
        resolved = BearerPrincipalResolver(self.principal_codec).resolve(
            f"Bearer {token}",
            expected_client_id="studio",
            now=self.NOW + 1,
        )
        self.assertEqual(resolved, principal)
        self.assertEqual(principal.user_id, "user-1")
        self.assertEqual(principal.roles, ("player", "reviewer"))

    def test_tampered_token_and_unknown_key_fail_closed(self) -> None:
        token, _ = self._principal()
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps({"tampered": True}).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        with self.assertRaisesRegex(RequestSecurityError, "signature"):
            self.principal_codec.verify(
                f"{encoded_header}.{tampered_payload}.{encoded_signature}",
                now=self.NOW + 1,
            )

        unknown_header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "kid": "missing", "typ": "CW-Principal"}).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        with self.assertRaisesRegex(RequestSecurityError, "not trusted"):
            self.principal_codec.verify(
                f"{unknown_header}.{encoded_payload}.{encoded_signature}",
                now=self.NOW + 1,
            )

    def test_wrong_algorithm_and_bearer_scheme_are_rejected(self) -> None:
        token, _ = self._principal()
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        none_header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "kid": "k1", "typ": "CW-Principal"}).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        with self.assertRaisesRegex(RequestSecurityError, "algorithm"):
            self.principal_codec.verify(
                f"{none_header}.{encoded_payload}.{encoded_signature}",
                now=self.NOW + 1,
            )
        with self.assertRaisesRegex(RequestSecurityError, "Bearer"):
            BearerPrincipalResolver(self.principal_codec).resolve(token, now=self.NOW + 1)

    def test_expired_future_and_client_mismatch_are_rejected(self) -> None:
        token, _ = self._principal(ttl_seconds=5)
        with self.assertRaisesRegex(RequestSecurityError, "expired"):
            self.principal_codec.verify(token, now=self.NOW + 5)
        with self.assertRaisesRegex(RequestSecurityError, "client"):
            self.principal_codec.verify(token, expected_client_id="other", now=self.NOW + 1)
        future = self.principal_codec.issue(
            user_id="user-1",
            client_id="studio",
            roles=["player"],
            now=self.NOW + 10,
        )
        with self.assertRaisesRegex(RequestSecurityError, "not valid yet"):
            self.principal_codec.verify(future, now=self.NOW)

    def test_key_rotation_keeps_old_tokens_verifiable(self) -> None:
        old_token, _ = self._principal()
        rotated = HMACKeyRing({"k1": b"a" * 32, "k2": b"c" * 32}, active_kid="k2")
        rotated_codec = PrincipalTokenCodec(
            rotated,
            issuer="compilableworld-host",
            audience="compilableworld-mcp",
        )
        old_principal = rotated_codec.verify(old_token, now=self.NOW + 1)
        new_token = rotated_codec.issue(
            user_id="user-2",
            client_id="studio",
            roles=["player"],
            now=self.NOW,
        )
        new_principal = rotated_codec.verify(new_token, now=self.NOW + 1)
        self.assertEqual(old_principal.key_id, "k1")
        self.assertEqual(new_principal.key_id, "k2")

    def test_session_scope_and_lifetime_are_bound_to_principal(self) -> None:
        principal_token, principal = self._principal(ttl_seconds=120)
        session_token = self.session_codec.issue(
            principal=principal,
            session_id="session-1",
            world_id="world-1",
            runtime_instance_id="runtime-1",
            timeline_id="main",
            actor_id="player-1",
            role="player",
            ttl_seconds=60,
            now=self.NOW + 1,
        )
        grant = self.session_codec.verify(
            session_token,
            principal=principal,
            expected_world_id="world-1",
            expected_runtime_instance_id="runtime-1",
            expected_timeline_id="main",
            expected_actor_id="player-1",
            expected_role="player",
            now=self.NOW + 2,
        )
        self.assertEqual(grant.principal_token_id, principal.token_id)
        self.assertTrue(principal_token)

        with self.assertRaisesRegex(RequestSecurityError, "world_id"):
            self.session_codec.verify(
                session_token,
                principal=principal,
                expected_world_id="other-world",
                now=self.NOW + 2,
            )
        with self.assertRaisesRegex(RequestSecurityError, "outlive"):
            self.session_codec.issue(
                principal=principal,
                session_id="session-2",
                world_id="world-1",
                runtime_instance_id="runtime-1",
                timeline_id="main",
                actor_id="player-1",
                role="player",
                ttl_seconds=120,
                now=self.NOW + 1,
            )

        forged_lifetime = self.session_codec._encode({
            "aud": "compilableworld-mcp",
            "cid": principal.client_id,
            "exp": principal.expires_at + 1,
            "iat": principal.issued_at,
            "iss": "compilableworld-host",
            "jti": "session-forged-lifetime",
            "nbf": principal.issued_at,
            "pid": principal.token_id,
            "role": "player",
            "sid": "session-forged",
            "uid": principal.user_id,
            "world_id": "world-1",
            "runtime_instance_id": "runtime-1",
            "timeline_id": "main",
            "actor_id": "player-1",
            "ver": "compilableworld.mcp-session-token/v0.1",
        })
        with self.assertRaisesRegex(RequestSecurityError, "exceeds"):
            self.session_codec.verify(forged_lifetime, principal=principal, now=self.NOW + 2)

    def test_session_cannot_be_rebound_to_another_principal(self) -> None:
        token, principal = self._principal()
        other_token = self.principal_codec.issue(
            user_id="user-2",
            client_id="studio",
            roles=["player"],
            now=self.NOW,
        )
        other = self.principal_codec.verify(other_token, now=self.NOW + 1)
        session = self.session_codec.issue(
            principal=principal,
            session_id="session-1",
            world_id="world-1",
            runtime_instance_id="runtime-1",
            timeline_id="main",
            actor_id="player-1",
            role="player",
            now=self.NOW,
        )
        with self.assertRaisesRegex(RequestSecurityError, "not bound"):
            self.session_codec.verify(session, principal=other, now=self.NOW + 1)
        self.assertTrue(token)


if __name__ == "__main__":
    unittest.main()
