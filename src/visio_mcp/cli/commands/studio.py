"""`visio-ai` / `visio-ai studio`: the interactive studio."""

from __future__ import annotations

from typing import Any

from visio_mcp.cli import ui
from visio_mcp.cli.studio.flow import studio


def run(args: Any) -> int:
    if not ui.interactive():
        ui.fail("The studio needs an interactive terminal.", "Use `visio-ai draw PATH` in scripts and CI.")
        return 2
    return studio(args)
