"""Dependency-free OIDC discovery, JWKS caching, and RS256 principal resolver."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .request_security import RequestSecurityError
from .security import TrustedPrincipal


OIDC_CONTRACT = "compilableworld.mcp-oidc-principal/v0.1"
OIDC_ALGORITHM = "RS256"
OIDCFetcher = Callable[[str], Mapping[str, Any] | bytes | str]


def _error(code: str, message: str) -> RequestSecurityError:
    return RequestSecurityError(code, message)


def _required(value: Any, field_name: str) -> str:
    if value is None:
        raise _error("OIDC_CONFIGURATION_INVALID", f"OIDC {field_name} must be non-empty")
    normalized = str(value).strip()
    if not normalized:
        raise _error("OIDC_CONFIGURATION_INVALID", f"OIDC {field_name} must be non-empty")
    return normalized


def _b64decode(value: str) -> bytes:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise _error("OIDC_TOKEN_INVALID", "OIDC token encoding is malformed")
    try:
        return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
    except (ValueError, UnicodeEncodeError) as exc:
        raise _error("OIDC_TOKEN_INVALID", "OIDC token encoding is malformed") from exc


def _b64int(value: Any, field_name: str) -> int:
    if not isinstance(value, str):
        raise _error("OIDC_JWKS_INVALID", f"JWKS {field_name} is invalid")
    raw = _b64decode(value)
    if not raw:
        raise _error("OIDC_JWKS_INVALID", f"JWKS {field_name} is empty")
    return int.from_bytes(raw, "big")


def _json_object(value: Mapping[str, Any] | bytes | str, *, error_code: str) -> dict[str, Any]:
    try:
        if isinstance(value, Mapping):
            decoded = dict(value)
        elif isinstance(value, bytes):
            decoded = json.loads(value.decode("utf-8"))
        elif isinstance(value, str):
            decoded = json.loads(value)
        else:
            raise TypeError("unsupported JSON response")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _error(error_code, "OIDC response is not a JSON object") from exc
    if not isinstance(decoded, dict):
        raise _error(error_code, "OIDC response is not a JSON object")
    return decoded


def _validate_url(url: str, *, allow_insecure_http: bool) -> str:
    normalized = _required(url, "URL").rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" and not (allow_insecure_http and parsed.scheme == "http"):
        raise _error("OIDC_CONFIGURATION_INVALID", "OIDC discovery and JWKS URLs must use HTTPS")
    if not parsed.netloc:
        raise _error("OIDC_CONFIGURATION_INVALID", "OIDC URL has no host")
    return normalized


@dataclass(frozen=True, slots=True)
class OIDCDiscoveryDocument:
    issuer: str
    jwks_uri: str


class OIDCDiscoveryClient:
    """Fetch and cache one configured issuer's discovery document and JWKS."""

    def __init__(
        self,
        issuer: str,
        *,
        fetcher: OIDCFetcher | None = None,
        cache_seconds: int = 300,
        allow_insecure_http: bool = False,
    ) -> None:
        self.issuer = _validate_url(issuer, allow_insecure_http=allow_insecure_http)
        if int(cache_seconds) <= 0:
            raise _error("OIDC_CONFIGURATION_INVALID", "OIDC cache_seconds must be positive")
        self.cache_seconds = int(cache_seconds)
        self.allow_insecure_http = bool(allow_insecure_http)
        self._fetcher = fetcher or self._default_fetch
        self._discovery: tuple[OIDCDiscoveryDocument, int] | None = None
        self._jwks: tuple[dict[str, dict[str, Any]], int] | None = None
        self._lock = threading.RLock()

    def discovery(self, *, now: int | None = None) -> OIDCDiscoveryDocument:
        current = int(time.time()) if now is None else int(now)
        with self._lock:
            if self._discovery is not None and self._discovery[1] > current:
                return self._discovery[0]
            response = _json_object(
                self._fetcher(f"{self.issuer}/.well-known/openid-configuration"),
                error_code="OIDC_DISCOVERY_FAILED",
            )
            discovered_issuer = _required(response.get("issuer"), "issuer")
            if discovered_issuer.rstrip("/") != self.issuer:
                raise _error("OIDC_DISCOVERY_FAILED", "discovery issuer does not match configured issuer")
            jwks_uri = _validate_url(
                response.get("jwks_uri"),
                allow_insecure_http=self.allow_insecure_http,
            )
            document = OIDCDiscoveryDocument(self.issuer, jwks_uri)
            self._discovery = (document, current + self.cache_seconds)
            self._jwks = None
            return document

    def jwk(self, kid: str, *, now: int | None = None) -> dict[str, Any]:
        key_id = _required(kid, "kid")
        current = int(time.time()) if now is None else int(now)
        with self._lock:
            if self._jwks is None or self._jwks[1] <= current:
                document = self.discovery(now=current)
                response = _json_object(self._fetcher(document.jwks_uri), error_code="OIDC_JWKS_FAILED")
                raw_keys = response.get("keys")
                if not isinstance(raw_keys, list):
                    raise _error("OIDC_JWKS_INVALID", "JWKS response has no key list")
                keys: dict[str, dict[str, Any]] = {}
                for raw in raw_keys:
                    if isinstance(raw, Mapping) and isinstance(raw.get("kid"), str):
                        keys[raw["kid"]] = dict(raw)
                self._jwks = (keys, current + self.cache_seconds)
            try:
                return self._jwks[0][key_id]
            except KeyError as exc:
                raise _error("OIDC_JWK_NOT_FOUND", "OIDC signing key is not available") from exc

    @staticmethod
    def _default_fetch(url: str) -> bytes:
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=5, context=ssl.create_default_context()) as response:
                return response.read()
        except OSError as exc:
            raise _error("OIDC_DISCOVERY_FAILED", "OIDC metadata request failed") from exc


class OIDCPrincipalResolver:
    """Resolve a signed OIDC JWT into the Runtime's TrustedPrincipal shape."""

    def __init__(
        self,
        discovery: OIDCDiscoveryClient,
        *,
        audience: str,
        max_lifetime: int = 900,
        roles_claim: str = "roles",
        user_id_claim: str = "sub",
    ) -> None:
        self.discovery = discovery
        self.audience = _required(audience, "audience")
        if int(max_lifetime) <= 0:
            raise _error("OIDC_CONFIGURATION_INVALID", "OIDC max_lifetime must be positive")
        self.max_lifetime = int(max_lifetime)
        self.roles_claim = _required(roles_claim, "roles_claim")
        self.user_id_claim = _required(user_id_claim, "user_id_claim")

    def resolve(
        self,
        authorization: str,
        *,
        expected_client_id: str | None = None,
        now: int | None = None,
    ) -> TrustedPrincipal:
        if not isinstance(authorization, str):
            raise _error("AUTHORIZATION_MISSING", "authorization header is missing")
        parts = authorization.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise _error("AUTHORIZATION_INVALID", "authorization must use the Bearer scheme")
        token = parts[1]
        encoded_header, encoded_payload, encoded_signature = self._token_parts(token)
        try:
            header = json.loads(_b64decode(encoded_header).decode("utf-8"))
            claims = json.loads(_b64decode(encoded_payload).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("OIDC_TOKEN_INVALID", "OIDC token JSON is malformed") from exc
        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise _error("OIDC_TOKEN_INVALID", "OIDC token header and claims must be objects")
        if header.get("alg") != OIDC_ALGORITHM:
            raise _error("OIDC_ALGORITHM_UNSUPPORTED", "only RS256 OIDC tokens are accepted")
        kid = _required(header.get("kid"), "kid")
        current = int(time.time()) if now is None else int(now)
        jwk = self.discovery.jwk(kid, now=current)
        self._verify_rs256(f"{encoded_header}.{encoded_payload}".encode("ascii"), _b64decode(encoded_signature), jwk)
        document = self.discovery.discovery(now=current)
        self._validate_claims(claims, document.issuer, current)
        roles = claims.get(self.roles_claim)
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or not role.strip() for role in roles):
            raise _error("OIDC_CLAIMS_INVALID", "OIDC roles claim is missing or invalid")
        subject = _required(claims.get("sub"), "sub")
        user_id = _required(claims.get(self.user_id_claim), self.user_id_claim)
        client_id = _required(expected_client_id or claims.get("azp") or claims.get("client_id"), "client_id")
        return TrustedPrincipal(
            issuer=document.issuer,
            audience=self.audience,
            subject=subject,
            user_id=user_id,
            client_id=client_id,
            roles=tuple(sorted(set(roles))),
            token_id=_required(claims.get("jti"), "jti"),
            issued_at=int(claims["iat"]),
            not_before=int(claims.get("nbf", claims["iat"])),
            expires_at=int(claims["exp"]),
            key_id=kid,
            contract_version=OIDC_CONTRACT,
        )

    @staticmethod
    def _token_parts(token: str) -> tuple[str, str, str]:
        if not isinstance(token, str) or token.count(".") != 2:
            raise _error("OIDC_TOKEN_INVALID", "OIDC token must contain three segments")
        parts = tuple(token.split("."))
        if any(not part for part in parts):
            raise _error("OIDC_TOKEN_INVALID", "OIDC token has an empty segment")
        return parts  # type: ignore[return-value]

    def _validate_claims(self, claims: Mapping[str, Any], issuer: str, now: int) -> None:
        if claims.get("iss") != issuer:
            raise _error("OIDC_ISSUER_MISMATCH", "OIDC issuer claim is not trusted")
        audience = claims.get("aud")
        if not (audience == self.audience or isinstance(audience, list) and self.audience in audience):
            raise _error("OIDC_AUDIENCE_MISMATCH", "OIDC audience claim is not trusted")
        try:
            issued_at = int(claims["iat"])
            not_before = int(claims.get("nbf", issued_at))
            expires_at = int(claims["exp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _error("OIDC_CLAIMS_INVALID", "OIDC token timestamps are invalid") from exc
        if issued_at > now or not_before > now:
            raise _error("TOKEN_NOT_YET_VALID", "OIDC token is not valid yet")
        if expires_at <= now or expires_at <= issued_at or expires_at - issued_at > self.max_lifetime:
            raise _error("OIDC_TOKEN_EXPIRED" if expires_at <= now else "OIDC_CLAIMS_INVALID", "OIDC token lifetime is invalid")

    @staticmethod
    def _verify_rs256(signing_input: bytes, signature: bytes, jwk: Mapping[str, Any]) -> None:
        if jwk.get("kty") != "RSA" or (jwk.get("alg") is not None and jwk.get("alg") != OIDC_ALGORITHM):
            raise _error("OIDC_JWKS_INVALID", "OIDC signing key is not an RS256 RSA key")
        if jwk.get("use") not in (None, "sig"):
            raise _error("OIDC_JWKS_INVALID", "OIDC signing key is not a signing key")
        modulus = _b64int(jwk.get("n"), "modulus")
        exponent = _b64int(jwk.get("e"), "exponent")
        size = (modulus.bit_length() + 7) // 8
        if len(signature) != size:
            raise _error("OIDC_SIGNATURE_INVALID", "OIDC signature length is invalid")
        encoded_message = pow(int.from_bytes(signature, "big"), exponent, modulus).to_bytes(size, "big")
        digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input).digest()
        padding_length = size - len(digest_info) - 3
        expected = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
        if padding_length < 8 or not hmac.compare_digest(encoded_message, expected):
            raise _error("OIDC_SIGNATURE_INVALID", "OIDC signature is invalid")


__all__ = [
    "OIDC_ALGORITHM",
    "OIDC_CONTRACT",
    "OIDCDiscoveryClient",
    "OIDCDiscoveryDocument",
    "OIDCPrincipalResolver",
]
