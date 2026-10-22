"""`visio-ai handoff`: let the user's own AI coding app draw the diagram through the MCP server."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from visio_mcp import repo
from visio_mcp.cli import coding_apps, prompts, ui


def launch(tool: coding_apps.Tool, paths: list[Path], diagram_type: str, focus: str = "") -> int:
    """Register the server with tool, then run it on paths; returns its exit code."""
    changed, argv, cwd = coding_apps.handoff(tool, paths, diagram_type, focus)
    ui.ok(changed)
    ui.info(f"Launching {tool.name} in {cwd} — it will explore the code and draw in Visio.")
    return subprocess.call(argv, cwd=cwd)


def run(args: Any) -> int:
    tools = coding_apps.installed_tools()
    if args.tool:
        tool = coding_apps.TOOLS[args.tool]
    elif tools:
        tool = tools[0] if len(tools) == 1 or not ui.interactive() else prompts.select(
            "Which app?", [prompts.choice(t.name, t) for t in tools])
    else:
        ui.fail("No AI coding app found on PATH.", "Install Claude Code, Gemini CLI, Codex or Copilot CLI.")
        return 1
    return launch(tool, [r.path for r in repo.discover(args.path)], args.type, args.focus)
