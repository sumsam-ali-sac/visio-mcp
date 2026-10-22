"""`visio-ai --help`: the command overview screen."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from visio_mcp.cli import ui

COMMANDS = [
    ("visio-ai", "Interactive studio: point at code, pick a diagram, watch Visio draw it, refine by chatting"),
    ("visio-ai draw PATH", "Explore a repo (or a folder of repos) and draw — no questions asked"),
    ("visio-ai render SPEC.json", "Draw a saved diagram spec"),
    ("visio-ai scan PATH", "Profile repositories: stack, cloud, IaC, CI, suggested diagrams"),
    ("visio-ai setup", "Choose the AI: Claude, Gemini, Azure OpenAI, OpenAI or Ollama"),
    ("visio-ai handoff PATH", "Let Claude Code, Gemini CLI, Codex or Copilot CLI draw it via MCP"),
    ("visio-ai doctor", "Check Visio, the AI provider and preview renderers"),
    ("visio-ai icons [install|remove]", "Official Azure, AWS and Google Cloud icons for cloud diagrams"),
    ("visio-ai themes | kinds | rules TYPE", "Browse themes, shape kinds and diagramming rules"),
    ("visio-ai examples", "Draw the bundled example diagrams"),
    ("visio-ai mcp", "Run the MCP server (for any MCP client)"),
]


def run(args: Any = None) -> int:
    ui.banner()
    t = ui.table("Command", "What it does")
    for cmd, desc in COMMANDS:
        t.add_row(Text(cmd, style="key"), Text(desc, style="muted"))
    ui.console.print(t)
    ui.hint("Common flags: --type architecture  --theme azure  --focus \"payments flow\"  --attach  --native  --out DIR")
    return 0
