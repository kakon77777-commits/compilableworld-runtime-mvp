"""Read-only Model Context Protocol adapter for CompilableWorld.

The core service has no dependency on the MCP SDK.  ``server.py`` adds the
optional FastMCP transport adapter when the ``mcp`` extra is installed.
"""

from .contracts import MCP_READONLY_CONTRACT, MCPWorldError
from .service import ReadOnlyWorldService

__all__ = ["MCP_READONLY_CONTRACT", "MCPWorldError", "ReadOnlyWorldService"]
