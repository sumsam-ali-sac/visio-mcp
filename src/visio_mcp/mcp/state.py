"""The server's one lazily-created Drawer, configured from VISIO_MCP_* environment variables."""

from __future__ import annotations

import os

from visio_mcp.output.drawer import Drawer

_drawer: Drawer | None = None  # touched only on the COM thread


def env_flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def drawer() -> Drawer:
    """Create the Drawer on first use. Must be called on the COM thread.

    VISIO_MCP_TARGET      auto (default) | visio | native
    VISIO_MCP_LIVE        1 (default): draw in the visible Visio window, shape by shape
    VISIO_MCP_ATTACH      1: draw into the Visio window the user already has open
    VISIO_MCP_HEADLESS    1: hidden Visio (CI, servers)
    VISIO_MCP_LIVE_DELAY  seconds between live shapes (default 0.05)
    """
    global _drawer
    if _drawer is None:
        _drawer = Drawer(
            target=os.environ.get("VISIO_MCP_TARGET", "auto"),  # type: ignore[arg-type]
            live=env_flag("VISIO_MCP_LIVE", True) and not env_flag("VISIO_MCP_HEADLESS", False),
            attach=env_flag("VISIO_MCP_ATTACH", False),
            live_delay=float(os.environ.get("VISIO_MCP_LIVE_DELAY", "0.05")),
        )
    return _drawer


def close() -> None:
    """Quit a Visio we started so it doesn't linger holding files open."""
    if _drawer is not None:
        _drawer.close()
