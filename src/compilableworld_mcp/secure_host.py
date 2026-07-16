"""Optional Uvicorn host runner with explicit TLS configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import MCPWorldError
from .secure_gateway import SecureReadOnlyMCPGateway
from .secure_server import build_secure_mcp_streamable_http_app


SECURE_HOST_CONTRACT = "compilableworld.mcp-secure-host/v0.1"


class SecureHostConfigError(MCPWorldError):
    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["format"] = SECURE_HOST_CONTRACT
        return payload


def _required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise SecureHostConfigError("INVALID_MCP_HOST_CONFIG", f"{field_name} must be non-empty")
    return normalized


def _env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SecureHostConfigError("INVALID_MCP_HOST_CONFIG", "boolean environment value is invalid")


@dataclass(frozen=True, slots=True)
class SecureMCPHostSettings:
    host: str = "127.0.0.1"
    port: int = 8443
    streamable_http_path: str = "/mcp"
    stateless_http: bool = False
    json_response: bool = True
    require_tls: bool = True
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    log_level: str = "info"
    timeout_keep_alive: int = 30

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None, *, prefix: str = "CW_MCP_") -> "SecureMCPHostSettings":
        source = os.environ if environ is None else environ
        defaults = cls()
        try:
            port = int(source.get(f"{prefix}PORT", str(defaults.port)))
            timeout = int(source.get(f"{prefix}TIMEOUT_KEEP_ALIVE", str(defaults.timeout_keep_alive)))
        except (TypeError, ValueError) as exc:
            raise SecureHostConfigError("INVALID_MCP_HOST_CONFIG", "port and timeout must be integers") from exc
        return cls(
            host=source.get(f"{prefix}HOST", defaults.host),
            port=port,
            streamable_http_path=source.get(f"{prefix}STREAMABLE_HTTP_PATH", defaults.streamable_http_path),
            stateless_http=_env_bool(source.get(f"{prefix}STATELESS_HTTP"), defaults.stateless_http),
            json_response=_env_bool(source.get(f"{prefix}JSON_RESPONSE"), defaults.json_response),
            require_tls=_env_bool(source.get(f"{prefix}REQUIRE_TLS"), defaults.require_tls),
            ssl_certfile=source.get(f"{prefix}TLS_CERTFILE"),
            ssl_keyfile=source.get(f"{prefix}TLS_KEYFILE"),
            log_level=source.get(f"{prefix}LOG_LEVEL", defaults.log_level),
            timeout_keep_alive=timeout,
        )

    def validate(self) -> "SecureMCPHostSettings":
        host = _required(self.host, "host")
        path = _required(self.streamable_http_path, "streamable_http_path")
        if not path.startswith("/"):
            raise SecureHostConfigError("INVALID_MCP_HOST_CONFIG", "streamable_http_path must start with '/'")
        if not 1 <= int(self.port) <= 65535:
            raise SecureHostConfigError("INVALID_MCP_HOST_CONFIG", "port must be between 1 and 65535")
        if int(self.timeout_keep_alive) <= 0:
            raise SecureHostConfigError("INVALID_MCP_HOST_CONFIG", "timeout_keep_alive must be positive")
        if bool(self.require_tls) and (not self.ssl_certfile or not self.ssl_keyfile):
            raise SecureHostConfigError(
                "TLS_REQUIRED",
                "secure MCP host requires both TLS certificate and key files",
            )
        if bool(self.require_tls):
            for label, value in (("ssl_certfile", self.ssl_certfile), ("ssl_keyfile", self.ssl_keyfile)):
                if not Path(value or "").is_file():
                    raise SecureHostConfigError("TLS_FILE_MISSING", f"{label} does not point to a file")
        if not self.require_tls and host not in {"127.0.0.1", "localhost", "::1"}:
            raise SecureHostConfigError(
                "TLS_REQUIRED",
                "non-localhost MCP host cannot disable TLS",
            )
        return self


def serve_secure_mcp_streamable_http(
    gateway: SecureReadOnlyMCPGateway,
    *,
    trusted_client_id: str,
    settings: SecureMCPHostSettings,
    action_gateway: Any | None = None,
    uvicorn_runner: Callable[..., Any] | None = None,
) -> Any:
    """Build the authenticated ASGI app and hand it to Uvicorn or a test host."""
    settings.validate()
    app = build_secure_mcp_streamable_http_app(
        gateway,
        trusted_client_id=trusted_client_id,
        action_gateway=action_gateway,
        host=settings.host,
        port=settings.port,
        streamable_http_path=settings.streamable_http_path,
        stateless_http=settings.stateless_http,
        json_response=settings.json_response,
    )
    runner = uvicorn_runner
    if runner is None:
        try:
            import uvicorn
        except ImportError as exc:  # pragma: no cover - optional deployment dependency
            raise SecureHostConfigError(
                "HOST_DEPENDENCY_MISSING",
                "Uvicorn is required to run the secure HTTP host",
            ) from exc
        runner = uvicorn.run
    kwargs: dict[str, Any] = {
        "host": settings.host,
        "port": settings.port,
        "log_level": settings.log_level.lower(),
        "timeout_keep_alive": settings.timeout_keep_alive,
    }
    if settings.ssl_certfile and settings.ssl_keyfile:
        kwargs.update({"ssl_certfile": settings.ssl_certfile, "ssl_keyfile": settings.ssl_keyfile})
    return runner(app, **kwargs)


__all__ = [
    "SECURE_HOST_CONTRACT",
    "SecureHostConfigError",
    "SecureMCPHostSettings",
    "serve_secure_mcp_streamable_http",
]
