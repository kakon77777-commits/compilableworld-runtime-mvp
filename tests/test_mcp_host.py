from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld_mcp import (
    SecureHostConfigError,
    SecureMCPHostSettings,
    serve_secure_mcp_streamable_http,
)


class SecureHostSettingsTests(unittest.TestCase):
    def test_tls_is_required_by_default_and_local_dev_can_be_explicitly_insecure(self) -> None:
        with self.assertRaisesRegex(SecureHostConfigError, "requires both TLS"):
            SecureMCPHostSettings().validate()
        self.assertEqual(
            SecureMCPHostSettings(require_tls=False, host="127.0.0.1").validate().host,
            "127.0.0.1",
        )
        with self.assertRaisesRegex(SecureHostConfigError, "cannot disable TLS"):
            SecureMCPHostSettings(require_tls=False, host="0.0.0.0").validate()

    def test_environment_settings_parse_and_tls_files_validate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / "server.crt"
            key = Path(directory) / "server.key"
            cert.write_text("certificate", encoding="utf-8")
            key.write_text("key", encoding="utf-8")
            settings = SecureMCPHostSettings.from_env(
                {
                    "CW_MCP_HOST": "0.0.0.0",
                    "CW_MCP_PORT": "9443",
                    "CW_MCP_TLS_CERTFILE": str(cert),
                    "CW_MCP_TLS_KEYFILE": str(key),
                    "CW_MCP_STATELESS_HTTP": "true",
                }
            )
            self.assertEqual(settings.port, 9443)
            self.assertTrue(settings.stateless_http)
            self.assertIs(settings.validate(), settings)


class SecureHostRunnerTests(unittest.TestCase):
    def test_runner_passes_tls_and_host_settings_to_uvicorn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / "server.crt"
            key = Path(directory) / "server.key"
            cert.write_text("certificate", encoding="utf-8")
            key.write_text("key", encoding="utf-8")
            settings = SecureMCPHostSettings(
                host="127.0.0.1",
                port=9443,
                ssl_certfile=str(cert),
                ssl_keyfile=str(key),
            )
            calls: list[tuple[object, dict[str, object]]] = []

            def runner(app, **kwargs):
                calls.append((app, kwargs))
                return "served"

            with patch(
                "compilableworld_mcp.secure_host.build_secure_mcp_streamable_http_app",
                return_value="asgi-app",
            ):
                result = serve_secure_mcp_streamable_http(
                    object(),
                    trusted_client_id="trusted-client",
                    settings=settings,
                    uvicorn_runner=runner,
                )

        self.assertEqual(result, "served")
        self.assertEqual(calls[0][0], "asgi-app")
        self.assertEqual(calls[0][1]["ssl_certfile"], str(cert))
        self.assertEqual(calls[0][1]["ssl_keyfile"], str(key))
        self.assertEqual(calls[0][1]["port"], 9443)


if __name__ == "__main__":
    unittest.main()
