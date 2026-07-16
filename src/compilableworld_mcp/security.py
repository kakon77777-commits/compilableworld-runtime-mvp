"""Dependency-free HMAC Principal and Session token primitives.

This is the next local M9/M10 slice.  It signs and verifies opaque tokens but
does not issue HTTP credentials, persist revocation state, or call Runtime.
Those boundaries remain explicit so token verification cannot be mistaken for
full transport security.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from .request_security import RequestSecurityError


TOKEN_ALGORITHM = "HS256"
PRINCIPAL_TOKEN_TYPE = "CW-Principal"
SESSION_TOKEN_TYPE = "CW-Session"
PRINCIPAL_TOKEN_CONTRACT = "compilableworld.mcp-principal-token/v0.1"
SESSION_TOKEN_CONTRACT = "compilableworld.mcp-session-token/v0.1"


def _token_error(code: str, message: str) -> RequestSecurityError:
    return RequestSecurityError(code, message)


def _non_empty(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise _token_error("INVALID_TOKEN_POLICY", f"token policy requires {field_name}")
    return normalized


def _b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise _token_error("TOKEN_MALFORMED", "token encoding is malformed")
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, UnicodeEncodeError) as exc:
        raise _token_error("TOKEN_MALFORMED", "token encoding is malformed") from exc


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _token_error("TOKEN_MALFORMED", "token claims are not serializable") from exc


def _now_seconds(value: int | None) -> int:
    return int(time.time()) if value is None else int(value)


def _validate_ttl(ttl_seconds: int, *, max_lifetime: int) -> int:
    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError) as exc:
        raise _token_error("INVALID_TOKEN_POLICY", "token lifetime must be an integer") from exc
    if ttl <= 0 or ttl > max_lifetime:
        raise _token_error("INVALID_TOKEN_POLICY", "token lifetime is outside the host policy")
    return ttl


@dataclass(frozen=True, slots=True)
class HMACKeyRing:
    """Signing key ring with an explicit active key and rotation support."""

    keys: Mapping[str, bytes] = field(repr=False)
    active_kid: str
    minimum_secret_bytes: int = 32

    def __post_init__(self) -> None:
        active = _non_empty(self.active_kid, "active_kid")
        if self.minimum_secret_bytes < 32:
            raise _token_error("INVALID_TOKEN_POLICY", "minimum HMAC secret must be at least 32 bytes")
        normalized: dict[str, bytes] = {}
        for kid, secret in dict(self.keys).items():
            key_id = _non_empty(kid, "key id")
            if not isinstance(secret, bytes) or len(secret) < self.minimum_secret_bytes:
                raise _token_error("TOKEN_KEY_INVALID", "HMAC key must be at least 32 bytes")
            normalized[key_id] = bytes(secret)
        if active not in normalized:
            raise _token_error("TOKEN_KEY_INVALID", "active HMAC key is not present in the key ring")
        object.__setattr__(self, "active_kid", active)
        object.__setattr__(self, "keys", normalized)

    def active(self) -> tuple[str, bytes]:
        return self.active_kid, self.keys[self.active_kid]

    def get(self, kid: str) -> bytes:
        try:
            return self.keys[kid]
        except KeyError as exc:
            raise _token_error("TOKEN_KEY_UNKNOWN", "token key is not trusted by this host") from exc


@dataclass(frozen=True, slots=True)
class TrustedPrincipal:
    issuer: str
    audience: str
    subject: str
    user_id: str
    client_id: str
    roles: tuple[str, ...]
    token_id: str
    issued_at: int
    not_before: int
    expires_at: int
    key_id: str
    contract_version: str = PRINCIPAL_TOKEN_CONTRACT

    def to_claims(self) -> dict[str, Any]:
        return {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": self.subject,
            "uid": self.user_id,
            "cid": self.client_id,
            "roles": list(self.roles),
            "iat": self.issued_at,
            "nbf": self.not_before,
            "exp": self.expires_at,
            "jti": self.token_id,
            "ver": self.contract_version,
        }


@dataclass(frozen=True, slots=True)
class SessionGrant:
    session_id: str
    user_id: str
    client_id: str
    principal_token_id: str
    world_id: str
    runtime_instance_id: str
    timeline_id: str
    actor_id: str
    role: str
    token_id: str
    issued_at: int
    not_before: int
    expires_at: int
    key_id: str
    contract_version: str = SESSION_TOKEN_CONTRACT

    def to_claims(self) -> dict[str, Any]:
        return {
            "sid": self.session_id,
            "uid": self.user_id,
            "cid": self.client_id,
            "pid": self.principal_token_id,
            "world_id": self.world_id,
            "runtime_instance_id": self.runtime_instance_id,
            "timeline_id": self.timeline_id,
            "actor_id": self.actor_id,
            "role": self.role,
            "iat": self.issued_at,
            "nbf": self.not_before,
            "exp": self.expires_at,
            "jti": self.token_id,
            "ver": self.contract_version,
        }


class _SignedTokenCodec:
    def __init__(
        self,
        key_ring: HMACKeyRing,
        *,
        issuer: str,
        audience: str,
        token_type: str,
        contract_version: str,
        max_lifetime: int,
    ) -> None:
        self.key_ring = key_ring
        self.issuer = _non_empty(issuer, "issuer")
        self.audience = _non_empty(audience, "audience")
        self.token_type = _non_empty(token_type, "token_type")
        self.contract_version = _non_empty(contract_version, "contract_version")
        if max_lifetime <= 0:
            raise _token_error("INVALID_TOKEN_POLICY", "max_lifetime must be positive")
        self.max_lifetime = int(max_lifetime)

    def _encode(self, claims: Mapping[str, Any]) -> str:
        kid, secret = self.key_ring.active()
        header = {"alg": TOKEN_ALGORITHM, "kid": kid, "typ": self.token_type}
        encoded_header = _b64_encode(_json_bytes(header))
        encoded_payload = _b64_encode(_json_bytes(claims))
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
        return f"{encoded_header}.{encoded_payload}.{_b64_encode(signature)}"

    def _decode(self, token: str, *, now: int | None = None) -> tuple[dict[str, Any], str]:
        if not isinstance(token, str) or token.count(".") != 2:
            raise _token_error("TOKEN_MALFORMED", "token must contain three encoded segments")
        encoded_header, encoded_payload, encoded_signature = token.split(".")
        try:
            header = json.loads(_b64_decode(encoded_header).decode("utf-8"))
            payload = json.loads(_b64_decode(encoded_payload).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _token_error("TOKEN_MALFORMED", "token JSON is malformed") from exc
        if not isinstance(header, dict) or not isinstance(payload, dict):
            raise _token_error("TOKEN_MALFORMED", "token header and claims must be objects")
        if header.get("alg") != TOKEN_ALGORITHM or header.get("typ") != self.token_type:
            raise _token_error("TOKEN_INVALID", "token algorithm or type is not accepted")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid.strip():
            raise _token_error("TOKEN_INVALID", "token key id is missing")
        secret = self.key_ring.get(kid)
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
        actual = _b64_decode(encoded_signature)
        if not hmac.compare_digest(expected, actual):
            raise _token_error("TOKEN_INVALID", "token signature is invalid")
        self._validate_claims(payload, now=_now_seconds(now))
        return payload, kid

    def _validate_claims(self, claims: Mapping[str, Any], *, now: int) -> None:
        required = {"iat", "nbf", "exp", "jti", "ver"}
        if not required.issubset(claims):
            raise _token_error("TOKEN_INVALID", "token claims are incomplete")
        if claims.get("ver") != self.contract_version:
            raise _token_error("TOKEN_CONTRACT_MISMATCH", "token contract version is not accepted")
        try:
            issued_at = int(claims["iat"])
            not_before = int(claims["nbf"])
            expires_at = int(claims["exp"])
        except (TypeError, ValueError) as exc:
            raise _token_error("TOKEN_INVALID", "token timestamps are invalid") from exc
        if not isinstance(claims["jti"], str) or not claims["jti"].strip():
            raise _token_error("TOKEN_INVALID", "token id is missing")
        if issued_at > now or not_before > now:
            raise _token_error("TOKEN_NOT_YET_VALID", "token is not valid yet")
        if expires_at <= now:
            raise _token_error("TOKEN_EXPIRED", "token has expired")
        if expires_at <= issued_at or expires_at - issued_at > self.max_lifetime:
            raise _token_error("TOKEN_INVALID", "token lifetime is invalid")


class PrincipalTokenCodec(_SignedTokenCodec):
    def __init__(
        self,
        key_ring: HMACKeyRing,
        *,
        issuer: str,
        audience: str,
        max_lifetime: int = 900,
    ) -> None:
        super().__init__(
            key_ring,
            issuer=issuer,
            audience=audience,
            token_type=PRINCIPAL_TOKEN_TYPE,
            contract_version=PRINCIPAL_TOKEN_CONTRACT,
            max_lifetime=max_lifetime,
        )

    def issue(
        self,
        *,
        user_id: str,
        client_id: str,
        roles: tuple[str, ...] | list[str],
        subject: str | None = None,
        ttl_seconds: int = 300,
        now: int | None = None,
        token_id: str | None = None,
    ) -> str:
        issued_at = _now_seconds(now)
        ttl = _validate_ttl(ttl_seconds, max_lifetime=self.max_lifetime)
        user = _non_empty(user_id, "user_id")
        client = _non_empty(client_id, "client_id")
        normalized_roles = tuple(sorted({_non_empty(role, "role") for role in roles}))
        if not normalized_roles:
            raise _token_error("INVALID_TOKEN_POLICY", "principal requires at least one role")
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": _non_empty(subject or user, "subject"),
            "uid": user,
            "cid": client,
            "roles": list(normalized_roles),
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + ttl,
            "jti": token_id or f"principal_{uuid4().hex}",
            "ver": self.contract_version,
        }
        return self._encode(claims)

    def verify(
        self,
        token: str,
        *,
        expected_client_id: str | None = None,
        now: int | None = None,
    ) -> TrustedPrincipal:
        claims, kid = self._decode(token, now=now)
        self._validate_identity_claims(claims)
        client_id = claims["cid"]
        if expected_client_id is not None and client_id != expected_client_id:
            raise _token_error("CLIENT_MISMATCH", "token client does not match the trusted transport client")
        return TrustedPrincipal(
            issuer=claims["iss"],
            audience=claims["aud"],
            subject=claims["sub"],
            user_id=claims["uid"],
            client_id=client_id,
            roles=tuple(claims["roles"]),
            token_id=claims["jti"],
            issued_at=int(claims["iat"]),
            not_before=int(claims["nbf"]),
            expires_at=int(claims["exp"]),
            key_id=kid,
        )

    def _validate_identity_claims(self, claims: Mapping[str, Any]) -> None:
        if claims.get("iss") != self.issuer or claims.get("aud") != self.audience:
            raise _token_error("TOKEN_SCOPE_MISMATCH", "token issuer or audience is not accepted")
        for key in ("sub", "uid", "cid"):
            if not isinstance(claims.get(key), str) or not claims[key].strip():
                raise _token_error("TOKEN_INVALID", "principal identity claims are incomplete")
        roles = claims.get("roles")
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or not role.strip() for role in roles):
            raise _token_error("TOKEN_INVALID", "principal roles are invalid")


class SessionTokenCodec(_SignedTokenCodec):
    def __init__(
        self,
        key_ring: HMACKeyRing,
        *,
        issuer: str,
        audience: str,
        max_lifetime: int = 900,
    ) -> None:
        super().__init__(
            key_ring,
            issuer=issuer,
            audience=audience,
            token_type=SESSION_TOKEN_TYPE,
            contract_version=SESSION_TOKEN_CONTRACT,
            max_lifetime=max_lifetime,
        )

    def issue(
        self,
        *,
        principal: TrustedPrincipal,
        session_id: str,
        world_id: str,
        runtime_instance_id: str,
        timeline_id: str,
        actor_id: str,
        role: str,
        ttl_seconds: int = 300,
        now: int | None = None,
        token_id: str | None = None,
    ) -> str:
        issued_at = _now_seconds(now)
        ttl = _validate_ttl(ttl_seconds, max_lifetime=self.max_lifetime)
        remaining = principal.expires_at - issued_at
        if remaining <= 0 or ttl > remaining:
            raise _token_error("SESSION_LIFETIME_INVALID", "session token cannot outlive its principal token")
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sid": _non_empty(session_id, "session_id"),
            "uid": _non_empty(principal.user_id, "user_id"),
            "cid": _non_empty(principal.client_id, "client_id"),
            "pid": _non_empty(principal.token_id, "principal_token_id"),
            "world_id": _non_empty(world_id, "world_id"),
            "runtime_instance_id": _non_empty(runtime_instance_id, "runtime_instance_id"),
            "timeline_id": _non_empty(timeline_id, "timeline_id"),
            "actor_id": _non_empty(actor_id, "actor_id"),
            "role": _non_empty(role, "role"),
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + ttl,
            "jti": token_id or f"session_{uuid4().hex}",
            "ver": self.contract_version,
        }
        return self._encode(claims)

    def verify(
        self,
        token: str,
        *,
        principal: TrustedPrincipal,
        expected_world_id: str | None = None,
        expected_runtime_instance_id: str | None = None,
        expected_timeline_id: str | None = None,
        expected_actor_id: str | None = None,
        expected_role: str | None = None,
        now: int | None = None,
    ) -> SessionGrant:
        claims, kid = self._decode(token, now=now)
        self._validate_session_claims(claims, principal)
        expected = {
            "world_id": expected_world_id,
            "runtime_instance_id": expected_runtime_instance_id,
            "timeline_id": expected_timeline_id,
            "actor_id": expected_actor_id,
            "role": expected_role,
        }
        for key, value in expected.items():
            if value is not None and claims[key] != value:
                raise _token_error("SESSION_SCOPE_MISMATCH", f"session token does not match {key}")
        return SessionGrant(
            session_id=claims["sid"],
            user_id=claims["uid"],
            client_id=claims["cid"],
            principal_token_id=claims["pid"],
            world_id=claims["world_id"],
            runtime_instance_id=claims["runtime_instance_id"],
            timeline_id=claims["timeline_id"],
            actor_id=claims["actor_id"],
            role=claims["role"],
            token_id=claims["jti"],
            issued_at=int(claims["iat"]),
            not_before=int(claims["nbf"]),
            expires_at=int(claims["exp"]),
            key_id=kid,
        )

    def _validate_session_claims(
        self,
        claims: Mapping[str, Any],
        principal: TrustedPrincipal,
    ) -> None:
        if claims.get("iss") != self.issuer or claims.get("aud") != self.audience:
            raise _token_error("TOKEN_SCOPE_MISMATCH", "session issuer or audience is not accepted")
        if claims.get("uid") != principal.user_id or claims.get("cid") != principal.client_id:
            raise _token_error("SESSION_PRINCIPAL_MISMATCH", "session token is not bound to the principal")
        if claims.get("pid") != principal.token_id:
            raise _token_error("SESSION_PRINCIPAL_MISMATCH", "session token was not issued by this principal token")
        required = ("sid", "uid", "cid", "pid", "world_id", "runtime_instance_id", "timeline_id", "actor_id", "role")
        if any(not isinstance(claims.get(key), str) or not claims[key].strip() for key in required):
            raise _token_error("TOKEN_INVALID", "session scope claims are incomplete")
        if int(claims["iat"]) < principal.issued_at or int(claims["exp"]) > principal.expires_at:
            raise _token_error("SESSION_LIFETIME_INVALID", "session token lifetime exceeds its principal token")


class BearerPrincipalResolver:
    """Resolve a Principal token from a strict ``Bearer`` header value."""

    def __init__(self, codec: PrincipalTokenCodec) -> None:
        self.codec = codec

    def resolve(
        self,
        authorization: str,
        *,
        expected_client_id: str | None = None,
        now: int | None = None,
    ) -> TrustedPrincipal:
        if not isinstance(authorization, str):
            raise _token_error("AUTHORIZATION_MISSING", "authorization header is missing")
        parts = authorization.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise _token_error("AUTHORIZATION_INVALID", "authorization must use the Bearer scheme")
        return self.codec.verify(parts[1], expected_client_id=expected_client_id, now=now)


__all__ = [
    "BearerPrincipalResolver",
    "HMACKeyRing",
    "PRINCIPAL_TOKEN_CONTRACT",
    "PRINCIPAL_TOKEN_TYPE",
    "PrincipalTokenCodec",
    "SESSION_TOKEN_CONTRACT",
    "SESSION_TOKEN_TYPE",
    "SessionGrant",
    "SessionTokenCodec",
    "TrustedPrincipal",
]
