"""visio-ai entry point: parse the command line and dispatch to a command module.

    visio-ai                      interactive studio (point at code, pick, watch it draw)
    visio-ai draw PATH            explore code and draw, no questions asked
    visio-ai render SPEC.json     draw a saved spec
    visio-ai scan PATH            profile repositories
    visio-ai setup                choose the AI provider
    visio-ai handoff PATH         let Claude Code / Gemini CLI / Codex / Copilot draw it
    visio-ai doctor               check Visio, providers and renderers
    visio-ai icons [install|remove] official Azure / AWS / Google Cloud icons
    visio-ai themes | kinds | rules TYPE | examples | mcp
"""

from __future__ import annotations

import sys
from importlib import import_module

from visio_mcp import __version__
from visio_mcp.cli import ui
from visio_mcp.cli.parser import build_parser

_COMMANDS = "visio_mcp.cli.commands"
# command -> (module in cli.commands, function)
COMMANDS: dict[str, tuple[str, str]] = {
    "studio": ("studio", "run"), "draw": ("draw", "run"), "render": ("draw", "render"),
    "examples": ("draw", "examples"), "scan": ("scan", "run"), "setup": ("setup", "run"),
    "handoff": ("handoff", "run"), "doctor": ("doctor", "run"), "icons": ("icons", "run"),
    "themes": ("browse", "themes"), "kinds": ("browse", "kinds"), "rules": ("browse", "rules_"),
    "mcp": ("mcp", "run"),
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        ui.console.print(f"visio-ai {__version__}")
        return 0
    if args.help:
        return import_module(f"{_COMMANDS}.help").run(args)
    module, func = COMMANDS[args.command or "studio"]
    try:
        return int(getattr(import_module(f"{_COMMANDS}.{module}"), func)(args) or 0)
    except KeyboardInterrupt:
        ui.console.print()
        return 130
    except (FileNotFoundError, NotADirectoryError, ValueError, RuntimeError) as e:
        ui.fail(str(e).strip("'\""), getattr(e, "hint", ""))
        return 1


if __name__ == "__main__":
    sys.exit(main())
