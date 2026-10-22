"""`visio-ai setup`: choose the AI provider."""

from __future__ import annotations

from typing import Any

from visio_mcp.ai import config as aiconfig
from visio_mcp.cli import ui
from visio_mcp.cli.studio.setup_wizard import setup_wizard


def run(args: Any) -> int:
    ui.banner("Set up the AI that explores your code.")
    setup_wizard(aiconfig.load_config())
    return 0
