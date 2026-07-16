from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compilableworld.compiler import compile_world
from compilableworld_mcp import RuntimeBindingStore
from compilableworld_mcp import server


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "gray_crown"


class _FakeServer:
    def __init__(self) -> None:
        self.transport: str | None = None

    def run(self, *, transport: str) -> None:
        self.transport = transport


class MCPServerCLITests(unittest.TestCase):
    def test_parser_supports_binding_only_startup(self) -> None:
        args = server.build_parser().parse_args(["--binding-db", "bindings.sqlite3"])
        self.assertEqual(args.packages, [])
        self.assertEqual(args.binding_db, "bindings.sqlite3")

    def test_cli_registers_and_then_rehydrates_a_binding_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = compile_world(EXAMPLE, root / "build")
            database = root / "bindings.sqlite3"

            first_server = _FakeServer()
            with patch.object(server, "build_mcp_server", return_value=first_server):
                self.assertEqual(
                    server.main(
                        [
                            "--binding-db",
                            str(database),
                            "--transport",
                            "stdio",
                            str(package),
                        ]
                    ),
                    0,
                )
            self.assertEqual(first_server.transport, "stdio")
            self.assertEqual(len(RuntimeBindingStore(database).list_enabled()), 1)

            second_server = _FakeServer()
            with patch.object(server, "build_mcp_server", return_value=second_server):
                self.assertEqual(server.main(["--binding-db", str(database)]), 0)
            self.assertEqual(second_server.transport, "stdio")


if __name__ == "__main__":
    unittest.main()
