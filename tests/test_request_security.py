from __future__ import annotations

import json
import unittest
from pathlib import Path

from compilableworld_mcp.request_security import (
    MCP_REQUEST_SECURITY_CONTRACT,
    RequestAuthContext,
    RequestContextProvider,
    RequestSecurityError,
)


ROOT = Path(__file__).resolve().parents[1]


class RequestSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = RequestContextProvider()

    def test_missing_context_fails_closed_with_versioned_error(self) -> None:
        with self.assertRaises(RequestSecurityError) as raised:
            self.provider.require()

        self.assertEqual(raised.exception.code, "REQUEST_CONTEXT_MISSING")
        payload = raised.exception.to_dict()
        self.assertEqual(payload["format"], MCP_REQUEST_SECURITY_CONTRACT)
        self.assertFalse(payload["world_state_changed"])
        json.dumps(payload)

    def test_bind_and_reset_are_context_local(self) -> None:
        context = RequestAuthContext(
            request_id="req-1",
            transport="HTTP",
            client_id="studio",
            peer="127.0.0.1",
            authorization="Bearer secret-principal",
            session_token="secret-session",
        )
        token = self.provider.bind(context)
        try:
            self.assertIs(self.provider.require(), context)
            self.assertEqual(self.provider.require().transport, "http")
        finally:
            self.provider.reset(token)

        with self.assertRaisesRegex(RequestSecurityError, "not bound"):
            self.provider.require()

    def test_nested_bind_restores_outer_context(self) -> None:
        outer = RequestAuthContext("outer", "stdio", "host")
        inner = RequestAuthContext("inner", "sse", "host")
        outer_token = self.provider.bind(outer)
        try:
            inner_token = self.provider.bind(inner)
            try:
                self.assertEqual(self.provider.require().request_id, "inner")
            finally:
                self.provider.reset(inner_token)
            self.assertEqual(self.provider.require().request_id, "outer")
        finally:
            self.provider.reset(outer_token)

    def test_safe_metadata_never_contains_credential_values(self) -> None:
        context = RequestAuthContext(
            "req-2",
            "streamable-http",
            "studio",
            authorization="Bearer do-not-log",
            session_token="do-not-log-session",
        )
        metadata = context.safe_metadata()
        rendered = json.dumps(metadata, sort_keys=True)

        self.assertTrue(metadata["authorization_present"])
        self.assertTrue(metadata["session_token_present"])
        self.assertNotIn("do-not-log", rendered)
        self.assertNotIn("do-not-log-session", rendered)
        self.assertNotIn("do-not-log", repr(context))

    def test_credentials_are_operation_specific_and_fail_closed(self) -> None:
        context = RequestAuthContext("req-3", "stdio", "host")
        with self.assertRaisesRegex(RequestSecurityError, "authorization credential"):
            context.require_authorization()
        with self.assertRaisesRegex(RequestSecurityError, "session token"):
            context.require_session_token()

    def test_context_rejects_missing_dispatch_metadata(self) -> None:
        with self.assertRaisesRegex(RequestSecurityError, "request_id"):
            RequestAuthContext("", "stdio", "host")
        with self.assertRaisesRegex(RequestSecurityError, "transport"):
            RequestAuthContext("req", "", "host")
        with self.assertRaisesRegex(RequestSecurityError, "client_id"):
            RequestAuthContext("req", "stdio", "")

    def test_context_metadata_schema_is_versioned(self) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "mcp-request-context.v0.1.schema.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(schema["$id"], "compilableworld.schema/mcp-request-context/v0.1")
        self.assertEqual(
            schema["properties"]["format"]["const"],
            MCP_REQUEST_SECURITY_CONTRACT,
        )


if __name__ == "__main__":
    unittest.main()
