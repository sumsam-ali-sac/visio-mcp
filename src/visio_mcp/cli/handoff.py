"""Hand a repo to the user's own AI coding app (Claude Code, Gemini CLI, Codex, Copilot CLI)
with the visio MCP server registered, so that app explores the code and draws in Visio."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from visio_mcp.mcp import guide as prompts


def server_command() -> list[str]:
    """How an MCP client starts this server: the installed script, else this Python."""
    exe = shutil.which("visio-mcp")
    return [exe] if exe else [sys.executable, "-m", "visio_mcp.mcp"]


@dataclass(frozen=True)
class Tool:
    key: str
    name: str
    binary: str
    register: Callable[[list[str]], str]  # returns a short description of what changed
    launch: Callable[[str, str], list[str]]  # (binary path, prompt) -> argv

    def installed(self) -> str | None:
        return shutil.which(self.binary)


def _claude_register(cmd: list[str]) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("claude is not on PATH")
    subprocess.run([exe, "mcp", "remove", "visio", "-s", "user"], capture_output=True)
    subprocess.run([exe, "mcp", "add", "-s", "user", "visio", "--", *cmd], check=True, capture_output=True)
    return "registered 'visio' with `claude mcp add -s user`"


def _json_register(file: Path, key: str, entry: dict) -> str:
    file.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(file.read_text(encoding="utf-8")) if file.exists() and file.read_text().strip() else {}
    data.setdefault(key, {})["visio"] = entry
    file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f"added 'visio' to {file}"


def _gemini_register(cmd: list[str]) -> str:
    return _json_register(Path.home() / ".gemini" / "settings.json", "mcpServers",
                          {"command": cmd[0], "args": cmd[1:], "timeout": 600000})


def _copilot_register(cmd: list[str]) -> str:
    return _json_register(Path.home() / ".copilot" / "mcp-config.json", "mcpServers",
                          {"type": "local", "command": cmd[0], "args": cmd[1:], "tools": ["*"]})


def _codex_register(cmd: list[str]) -> str:
    file = Path.home() / ".codex" / "config.toml"
    file.parent.mkdir(parents=True, exist_ok=True)
    text = file.read_text(encoding="utf-8") if file.exists() else ""
    block = (f"[mcp_servers.visio]\ncommand = {json.dumps(cmd[0])}\nargs = {json.dumps(cmd[1:])}\n"
             "startup_timeout_sec = 60\ntool_timeout_sec = 600\n")
    lines, out, skip = text.splitlines(keepends=True), [], False
    for line in lines:  # drop an older [mcp_servers.visio] table
        if line.strip().startswith("["):
            skip = line.strip() == "[mcp_servers.visio]"
        if not skip:
            out.append(line)
    new = "".join(out).rstrip() + ("\n\n" if out else "") + block
    file.write_text(new, encoding="utf-8")
    return f"added [mcp_servers.visio] to {file}"


TOOLS: dict[str, Tool] = {t.key: t for t in (
    Tool("claude", "Claude Code", "claude", _claude_register, lambda exe, p: [exe, p]),
    Tool("gemini", "Gemini CLI", "gemini", _gemini_register, lambda exe, p: [exe, "-i", p]),
    Tool("codex", "OpenAI Codex CLI", "codex", _codex_register, lambda exe, p: [exe, p]),
    Tool("copilot", "GitHub Copilot CLI", "copilot", _copilot_register, lambda exe, p: [exe, "-i", p]),
)}


def installed_tools() -> list[Tool]:
    return [t for t in TOOLS.values() if t.installed()]


def build_prompt(paths: list[Path], diagram_type: str, focus: str = "") -> str:
    where = paths[0] if len(paths) == 1 else ", ".join(str(p) for p in paths)
    body = prompts.diagram_prompt(str(where), "repo", diagram_type)
    if focus:
        body += f"\nFocus: {focus}\n"
    return body + "\nUse the visio MCP tools (get_authoring_guide, get_diagram_rules, render_diagram, patch_diagram)."


def handoff(tool: Tool, paths: list[Path], diagram_type: str, focus: str = "") -> tuple[str, list[str], Path]:
    """Register the server with tool, and return (what changed, argv to launch, cwd)."""
    changed = tool.register(server_command())
    exe = tool.installed()
    if not exe:
        raise RuntimeError(f"{tool.name} is not installed (no '{tool.binary}' on PATH)")
    cwd = paths[0] if len(paths) == 1 else Path(paths[0]).parent
    return changed, tool.launch(exe, build_prompt(paths, diagram_type, focus)), cwd
