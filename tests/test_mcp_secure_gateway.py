from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys
import types
from unittest.mock import Mock, patch

from compilableworld.compiler import compile_world
from compilableworld_mcp import (
    BearerPrincipalResolver,
    HMACKeyRing,
    PrincipalTokenCodec,
    RequestAuthContext,
    RequestSecurityError,
    RequestSecurityPipeline,
    ReadOnlyWorldService,
    SessionLifecycleStore,
    SessionTokenCodec,
    SecureReadOnlyMCPGateway,
    AuditStore,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"


class SecureReadOnlyGatewayTests(unittest.TestCase):
    NOW = 1_800_000_000

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        package_path = compile_world(EXAMPLE, Path(self.temp.name) / "build")
        from compilableworld_mcp import ReadOnlyWorldService

        self.service = ReadOnlyWorldService()
        self.world_id = self.service.register_package(package_path, runtime_instance_id="runtime_secure")
        ring = HMACKeyRing({"k1": b"s" * 32}, active_kid="k1")
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
            client_id="secure-client",
            roles=["player"],
            now=self.NOW,
            ttl_seconds=300,
            token_id="principal-secure-1",
        )
        self.authorization = f"Bearer {principal_token}"
        self.pipeline = RequestSecurityPipeline(
            BearerPrincipalResolver(self.principal_codec),
            self.session_codec,
        )
        self.gateway = SecureReadOnlyMCPGateway(
            self.service,
            self.pipeline,
            self.session_codec,
            session_ttl_seconds=120,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _context(self, *, session_token: str | None = None) -> RequestAuthContext:
        return RequestAuthContext(
            request_id="secure-request-1",
            transport="http",
            client_id="secure-client",
            authorization=self.authorization,
            session_token=session_token,
        )

    def test_open_issues_server_signed_session_and_read_requires_it(self) -> None:
        opened = self.gateway.open_world_session(
            self._context(),
            self.world_id,
            now=self.NOW,
        )
        self.assertTrue(opened["session_token"])
        self.assertEqual(opened["session"]["user_id"], "user-1")
        self.assertEqual(opened["audit"]["operation"], "session.open")
        self.assertNotIn(opened["session_token"], json.dumps(opened["audit"]))

        status = self.gateway.get_world_status(
            self._context(session_token=opened["session_token"]),
            now=self.NOW,
        )
        self.assertEqual(status["session_id"], opened["session"]["session_id"])
        self.assertEqual(status["audit"]["operation"], "world.status")
        self.assertEqual(status["audit"]["session_id"], opened["session"]["session_id"])

        with self.assertRaisesRegex(RequestSecurityError, "session token"):
            self.gateway.get_world_status(self._context(), now=self.NOW)

    def test_close_invalidates_the_live_session_even_when_token_is_unexpired(self) -> None:
        opened = self.gateway.open_world_session(self._context(), self.world_id, now=self.NOW)
        session_context = self._context(session_token=opened["session_token"])
        closed = self.gateway.close_world_session(session_context, now=self.NOW)
        self.assertTrue(closed["closed"])
        with self.assertRaisesRegex(RequestSecurityError, "closed"):
            self.gateway.get_world_status(session_context, now=self.NOW)

    def test_rotation_replaces_the_active_token_without_changing_the_live_session(self) -> None:
        opened = self.gateway.open_world_session(self._context(), self.world_id, now=self.NOW)
        old_context = self._context(session_token=opened["session_token"])
        rotated = self.gateway.rotate_session(old_context, now=self.NOW + 1)
        self.assertTrue(rotated["rotated"])
        self.assertNotEqual(rotated["session_token"], opened["session_token"])
        self.assertEqual(rotated["session"]["session_id"], opened["session"]["session_id"])

        with self.assertRaises(RequestSecurityError) as error:
            self.gateway.get_world_status(old_context, now=self.NOW + 1)
        self.assertEqual(error.exception.code, "SESSION_ROTATED")
        status = self.gateway.get_world_status(
            self._context(session_token=rotated["session_token"]),
            now=self.NOW + 1,
        )
        self.assertEqual(status["session_id"], opened["session"]["session_id"])

    def test_sqlite_session_and_service_rehydrate_after_host_restart(self) -> None:
        database = Path(self.temp.name) / "sessions.sqlite3"
        lifecycle = SessionLifecycleStore(database)
        gateway = SecureReadOnlyMCPGateway(
            self.service,
            self.pipeline,
            self.session_codec,
            session_ttl_seconds=120,
            session_store=lifecycle,
        )
        opened = gateway.open_world_session(
            self._context(),
            self.world_id,
            model_id="model-rehydrate-test",
            now=self.NOW,
        )

        package_path = compile_world(EXAMPLE, Path(self.temp.name) / "restart-build")
        restarted_service = ReadOnlyWorldService()
        restarted_service.register_package(package_path, runtime_instance_id="runtime_secure")
        restarted_gateway = SecureReadOnlyMCPGateway(
            restarted_service,
            self.pipeline,
            self.session_codec,
            session_ttl_seconds=120,
            session_store=SessionLifecycleStore(database),
        )

        restored = restarted_gateway.rehydrate_sessions(now=self.NOW + 1)
        self.assertEqual(restored["restored"], 1)
        restored_session = restarted_service.session_for_security(opened["session"]["session_id"])
        self.assertEqual(restored_session.model_id, "model-rehydrate-test")
        status = restarted_gateway.get_world_status(
            self._context(session_token=opened["session_token"]),
            now=self.NOW + 1,
        )
        self.assertEqual(status["session_id"], opened["session"]["session_id"])

    def test_sqlite_audit_sink_persists_session_and_status_operations(self) -> None:
        database = Path(self.temp.name) / "audit.sqlite3"
        gateway = SecureReadOnlyMCPGateway(
            self.service,
            self.pipeline,
            self.session_codec,
            session_ttl_seconds=120,
            audit_store=AuditStore(database),
        )
        opened = gateway.open_world_session(self._context(), self.world_id, now=self.NOW)
        gateway.get_world_status(self._context(session_token=opened["session_token"]), now=self.NOW)

        records = AuditStore(database).query(session_id=opened["session"]["session_id"])
        operations = {record["operation"] for record in records}
        self.assertTrue(all(record["audit_id"] for record in records))
        self.assertIn("session.open", operations)
        self.assertIn("world.status", operations)

    def test_open_rejects_a_role_missing_from_the_principal(self) -> None:
        with self.assertRaisesRegex(RequestSecurityError, "requested session role"):
            self.gateway.open_world_session(
                self._context(),
                self.world_id,
                role="reviewer",
                now=self.NOW,
            )


class SecureServerOptionalDependencyTests(unittest.TestCase):
    def test_secure_server_import_is_lazy_without_mcp_sdk(self) -> None:
        from compilableworld_mcp.secure_server import build_secure_mcp_server

        self.assertTrue(callable(build_secure_mcp_server))

    def test_streamable_http_builder_wraps_fastmcp_app_with_asgi_auth(self) -> None:
        from compilableworld_mcp.secure_server import build_secure_mcp_streamable_http_app

        class FakeFastMCP:
            def __init__(self, name: str, **_: object) -> None:
                self.tools: dict[str, object] = {}

            def tool(self):
                def decorator(function):
                    self.tools[function.__name__] = function
                    return function

                return decorator

            def streamable_http_app(self):
                async def app(scope, receive, send):
                    return None

                return app

        fastmcp_module = types.ModuleType("mcp.server.fastmcp")
        fastmcp_module.Context = type("Context", (), {})
        fastmcp_module.FastMCP = FakeFastMCP
        types_module = types.ModuleType("mcp.types")
        types_module.CallToolResult = type("CallToolResult", (), {})
        types_module.TextContent = type("TextContent", (), {})
        server_module = types.ModuleType("mcp.server")
        mcp_module = types.ModuleType("mcp")
        mcp_module.server = server_module
        mcp_module.types = types_module
        server_module.fastmcp = fastmcp_module

        gateway = Mock()
        gateway.pipeline = object()
        with patch.dict(
            sys.modules,
            {
                "mcp": mcp_module,
                "mcp.server": server_module,
                "mcp.server.fastmcp": fastmcp_module,
                "mcp.types": types_module,
            },
        ):
            app = build_secure_mcp_streamable_http_app(
                gateway,
                trusted_client_id="trusted-client",
                streamable_http_path="/mcp",
            )

        from compilableworld_mcp import ASGIAuthMiddleware

        self.assertIsInstance(app, ASGIAuthMiddleware)

    def test_secure_server_keeps_session_token_out_of_visible_tool_result(self) -> None:
        from compilableworld_mcp.secure_server import build_secure_mcp_server

        class FakeFastMCP:
            def __init__(self, name: str, **_: object) -> None:
                self.tools: dict[str, object] = {}

            def tool(self):
                def decorator(function):
                    self.tools[function.__name__] = function
                    return function

                return decorator

        class FakeContext:
            def __init__(self) -> None:
                self.request_id = "request-1"
                self.request_context = types.SimpleNamespace(
                    request=types.SimpleNamespace(
                        headers={},
                        client=types.SimpleNamespace(host="127.0.0.1"),
                    )
                )

        class FakeTextContent:
            def __init__(self, **values: object) -> None:
                self.values = values

        class FakeCallToolResult:
            def __init__(self, **values: object) -> None:
                self.values = values

        fastmcp_module = types.ModuleType("mcp.server.fastmcp")
        fastmcp_module.Context = FakeContext
        fastmcp_module.FastMCP = FakeFastMCP
        types_module = types.ModuleType("mcp.types")
        types_module.CallToolResult = FakeCallToolResult
        types_module.TextContent = FakeTextContent
        server_module = types.ModuleType("mcp.server")
        mcp_module = types.ModuleType("mcp")
        mcp_module.server = server_module
        mcp_module.types = types_module
        server_module.fastmcp = fastmcp_module

        gateway = Mock()
        gateway.pipeline = object()
        gateway.open_world_session.return_value = {
            "session": {"session_id": "session-1"},
            "session_token": "secret-session-token",
        }
        action_gateway = Mock()
        action_gateway.submit_action.return_value = {"accepted": True}
        with patch.dict(
            sys.modules,
            {
                "mcp": mcp_module,
                "mcp.server": server_module,
                "mcp.server.fastmcp": fastmcp_module,
                "mcp.types": types_module,
            },
        ):
            server = build_secure_mcp_server(
                gateway,
                trusted_client_id="trusted-client",
                action_gateway=action_gateway,
            )
            result = server.tools["open_world_session"](FakeContext(), "gray-crown")
            action_result = server.tools["submit_action"](
                FakeContext(),
                {"verb": "look"},
                "idempotency-1",
            )

        self.assertNotIn("session_token", result.values["structuredContent"])
        self.assertNotIn("secret-session-token", result.values["content"][0].values["text"])
        self.assertEqual(
            result.values["meta"]["compilableworld.session-token"],
            "secret-session-token",
        )
        self.assertEqual(action_result, {"accepted": True})
        action_gateway.submit_action.assert_called_once()


if __name__ == "__main__":
    unittest.main()
