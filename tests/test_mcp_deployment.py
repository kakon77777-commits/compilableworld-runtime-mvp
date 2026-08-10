from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import time
import unittest

from compilableworld_mcp import (
    ASGIAuthMiddleware,
    HMACKeyRing,
    HTTPRequestContextAdapter,
    OIDCDiscoveryClient,
    OIDCPrincipalResolver,
    PrincipalTokenCodec,
    RequestAuthContext,
    RequestSecurityError,
    RequestSecurityPipeline,
    SessionTokenCodec,
    BearerPrincipalResolver,
)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _probable_prime(rng: random.Random) -> int:
    while True:
        candidate = rng.getrandbits(256) | (1 << 255) | 1
        if any(candidate % divisor == 0 for divisor in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)):
            continue
        if all(
            pow(base, candidate - 1, candidate) == 1
            for base in (2, 3, 5, 7, 11, 13, 17)
        ):
            return candidate


def _rsa_fixture() -> tuple[dict[str, str], int, int]:
    rng = random.Random(7)
    p = _probable_prime(rng)
    q = _probable_prime(rng)
    while q == p:
        q = _probable_prime(rng)
    exponent = 65537
    modulus = p * q
    private_exponent = pow(exponent, -1, (p - 1) * (q - 1))
    jwk = {
        "kid": "oidc-key-1",
        "kty": "RSA",
        "alg": "RS256",
        "use": "sig",
        "n": _b64(modulus.to_bytes((modulus.bit_length() + 7) // 8, "big")),
        "e": _b64(exponent.to_bytes((exponent.bit_length() + 7) // 8, "big")),
    }
    return jwk, modulus, private_exponent


def _oidc_token(claims: dict[str, object], modulus: int, private_exponent: int) -> str:
    header = {"alg": "RS256", "kid": "oidc-key-1", "typ": "JWT"}
    encoded_header = _b64(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    encoded_payload = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input).digest()
    size = (modulus.bit_length() + 7) // 8
    encoded_message = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded_message, "big"), private_exponent, modulus).to_bytes(size, "big")
    return f"{encoded_header}.{encoded_payload}.{_b64(signature)}"


class ASGIAuthMiddlewareTests(unittest.TestCase):
    NOW = int(time.time())

    def setUp(self) -> None:
        ring = HMACKeyRing({"k1": b"s" * 32}, active_kid="k1")
        principal_codec = PrincipalTokenCodec(ring, issuer="https://issuer.example", audience="compilableworld")
        self.session_codec = SessionTokenCodec(ring, issuer="https://issuer.example", audience="compilableworld")
        token = principal_codec.issue(
            user_id="user-1",
            client_id="trusted-client",
            roles=["player"],
            now=self.NOW,
            ttl_seconds=300,
            token_id="principal-asgi-1",
        )
        self.authorization = f"Bearer {token}"
        pipeline = RequestSecurityPipeline(BearerPrincipalResolver(principal_codec), self.session_codec)
        self.adapter = HTTPRequestContextAdapter(pipeline, trusted_client_id="trusted-client")
        self.seen_scope = None

    def test_http_request_is_authenticated_and_context_is_exposed_to_app(self) -> None:
        async def app(scope, receive, send):
            self.seen_scope = scope
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = ASGIAuthMiddleware(app, trusted_client_id="trusted-client", adapter=self.adapter)
        sent: list[dict[str, object]] = []
        scope = {
            "type": "http",
            "headers": [(b"authorization", self.authorization), (b"x-request-id", b"request-1")],
            "client": ("127.0.0.1", 1234),
            "state": {},
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(middleware(scope, receive, send))

        self.assertEqual(sent[0]["status"], 200)
        context = self.seen_scope["state"]["compilableworld.request_auth_context"]
        self.assertIsInstance(context, RequestAuthContext)
        self.assertEqual(context.request_id, "request-1")
        self.assertTrue(context.safe_metadata()["authorization_present"])

    def test_missing_authorization_fails_before_app(self) -> None:
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        middleware = ASGIAuthMiddleware(app, trusted_client_id="trusted-client", adapter=self.adapter)
        sent: list[dict[str, object]] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        asyncio.run(middleware({"type": "http", "headers": [], "state": {}}, receive, send))

        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 401)
        self.assertIn(b"AUTHORIZATION_MISSING", sent[1]["body"])


class OIDCResolverTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        jwk, self.modulus, self.private_exponent = _rsa_fixture()
        issuer = "https://issuer.example"
        self.calls: list[str] = []
        responses = {
            f"{issuer}/.well-known/openid-configuration": {
                "issuer": issuer,
                "jwks_uri": f"{issuer}/jwks.json",
            },
            f"{issuer}/jwks.json": {"keys": [jwk]},
        }

        def fetch(url: str):
            self.calls.append(url)
            return responses[url]

        self.client = OIDCDiscoveryClient(issuer, fetcher=fetch, cache_seconds=300)
        self.resolver = OIDCPrincipalResolver(self.client, audience="compilableworld", max_lifetime=900)

    def _token(self, **overrides: object) -> str:
        claims: dict[str, object] = {
            "iss": "https://issuer.example",
            "aud": "compilableworld",
            "sub": "subject-1",
            "roles": ["player"],
            "iat": self.NOW - 10,
            "nbf": self.NOW - 10,
            "exp": self.NOW + 300,
            "jti": "oidc-jti-1",
        }
        claims.update(overrides)
        return _oidc_token(claims, self.modulus, self.private_exponent)

    def test_discovery_jwks_and_rs256_principal_are_cached_and_verified(self) -> None:
        token = self._token()
        principal = self.resolver.resolve(f"Bearer {token}", expected_client_id="oidc-client", now=self.NOW)
        second = self.resolver.resolve(f"Bearer {token}", expected_client_id="oidc-client", now=self.NOW)

        self.assertEqual(principal.user_id, "subject-1")
        self.assertEqual(principal.roles, ("player",))
        self.assertEqual(second.token_id, "oidc-jti-1")
        self.assertEqual(len(self.calls), 2)

    def test_oidc_rejects_wrong_audience_and_invalid_signature(self) -> None:
        with self.assertRaisesRegex(RequestSecurityError, "audience"):
            self.resolver.resolve(
                f"Bearer {self._token(aud='other-audience')}",
                expected_client_id="oidc-client",
                now=self.NOW,
            )
        valid = self._token()
        invalid = valid[:-1] + ("A" if valid[-1] != "A" else "B")
        with self.assertRaisesRegex(RequestSecurityError, "signature"):
            self.resolver.resolve(f"Bearer {invalid}", expected_client_id="oidc-client", now=self.NOW)


if __name__ == "__main__":
    unittest.main()
