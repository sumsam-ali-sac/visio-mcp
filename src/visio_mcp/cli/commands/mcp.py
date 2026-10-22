"""`visio-ai mcp`: run the MCP server on stdio."""

from __future__ import annotations

from typing import Any


def run(args: Any) -> int:
    from visio_mcp.mcp import server

    server.main()
    return 0
