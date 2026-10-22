"""Exploring the code: scan folders, show what was found, and draft a spec (AI agent or offline)."""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from rich.console import Group
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from visio_mcp import repo
from visio_mcp.cli import ui
from visio_mcp.cli.studio.session import Session, provider_label
from visio_mcp.repo import RepoInfo
from visio_mcp.spec import DiagramSpec

TOOL_ICONS = {"list_dir": "📂", "read_file": "📄", "search": "🔎", "find_files": "🗂 ",
              "get_rules": "📐", "list_kinds": "🧩", "submit_diagram": "✏️ "}
TOOL_STATUS = {"read_file": "Reading code", "search": "Searching", "list_dir": "Browsing",
               "find_files": "Finding files", "submit_diagram": "Drafting the diagram"}


def scan_paths(raw: str) -> list[RepoInfo]:
    with ui.spinner("Scanning for repositories…"):
        t0 = time.perf_counter()
        repos = repo.discover(raw.strip().strip('"').strip("'"))
    if not repos:
        raise FileNotFoundError(f"no code found under {raw}")
    ui.ok(f"Found {len(repos)} repositor{'y' if len(repos) == 1 else 'ies'} in {time.perf_counter() - t0:.1f}s")
    return repos


def repo_table(repos: list[RepoInfo]) -> Table:
    t = ui.table("Repository", "Stack", "Infra", "Suggested")
    for r in repos:
        langs = ", ".join(list(r.languages)[:2])
        stack = " · ".join(x for x in [langs, ", ".join(r.frameworks[:2])] if x)
        infra = ", ".join(([c.upper() if c != "azure" else "Azure" for c in r.cloud]) +
                          (["Docker"] if r.containers else []) + (["CI"] if r.ci else [])) or "—"
        t.add_row(Text(r.name, style="bold"), Text(stack or "—", style="muted"), infra,
                  Text(r.suggested_types[0] if r.suggested_types else "architecture", style="accent2"))
    return t


def offline_draft(repos: list[RepoInfo], diagram_type: str) -> DiagramSpec:
    """A no-AI draft from manifests, compose files, IaC and CI."""
    return repo.heuristic_spec(repos, diagram_type)


def provider_hint(repos: list[RepoInfo]) -> str | None:
    """The cloud the repos use most, if any."""
    clouds = [c for r in repos for c in r.cloud]
    return max(set(clouds), key=clouds.count) if clouds else None


def run_agent(llm: Any, cfg: Any, s: Session) -> DiagramSpec:
    """Let the AI explore the code with a live activity feed; returns the drafted spec."""
    from visio_mcp.ai.agent import DiagramAgent

    feed: deque[Text] = deque(maxlen=9)
    state = {"status": "Reading the workspace", "steps": 0, "t0": time.perf_counter()}

    def render() -> Group:
        elapsed = time.perf_counter() - state["t0"]
        head = Text.assemble((f" {provider_label(cfg)} ", "bold black on #7C9CFF"), "  ",
                             (f"{state['steps']} steps · {elapsed:,.0f}s", "muted"))
        spin = Spinner("dots12", text=Text(state["status"], style="bold"), style=ui.ACCENT)
        return ui.panel(Group(head, Text(""), *feed, Text(""), spin), title="Exploring the code",
                        subtitle="Ctrl+C to stop")

    def on_event(ev: Any) -> None:
        kind, msg = ev.kind, ev.message
        if kind == "tool":
            state["steps"] += 1
            name = msg.split(" ", 1)[0]
            feed.append(Text.assemble(f"  {TOOL_ICONS.get(name, '•')} ", (msg, "default")))
            state["status"] = TOOL_STATUS.get(name, "Working")
        elif kind in ("thinking", "text") and msg.strip():
            line = " ".join(msg.split())
            feed.append(Text(f"  💭 {line[:110] + ('…' if len(line) > 110 else '')}", style="italic muted"))
        elif kind == "lint":
            feed.append(Text(f"  📐 {msg}", style="warn"))
            state["status"] = "Polishing against the diagram rules"
        elif kind == "status":
            state["status"] = msg
        elif kind == "error":
            feed.append(Text(f"  ✖ {msg}", style="bad"))
        live.update(render())

    agent = DiagramAgent(llm, s.repos, s.diagram_type, s.focus,
                         provider_hint=provider_hint(s.repos), on_event=on_event)
    s.agent = agent
    with Live(render(), console=ui.console, refresh_per_second=12, transient=True) as live:
        try:
            spec = agent.run()
        except KeyboardInterrupt:
            agent.cancel()
            raise
    ui.ok(f"Explored the code in {state['steps']} steps ({time.perf_counter() - state['t0']:.0f}s)")
    return spec


def explore(how: str, cfg: Any, s: Session) -> DiagramSpec | None:
    """Draft a spec the chosen way ("ai" or "offline"); None if stopped or failed."""
    if how == "offline":
        with ui.spinner("Drafting from the static scan…"):
            spec = offline_draft(s.repos, s.diagram_type)
        ui.ok(f"Drafted {len(spec.nodes)} nodes from manifests, compose files, IaC and CI")
        return spec
    from visio_mcp.ai import providers

    try:
        return run_agent(providers.make_llm(cfg.provider), cfg.provider, s)
    except KeyboardInterrupt:
        ui.warn("Stopped.")
        return None
    except Exception as e:  # LLMError carries a hint
        from visio_mcp.cli import prompts

        ui.fail(str(getattr(e, "message", e)), getattr(e, "hint", "") or "Try /setup or the quick draft.")
        if prompts.confirm("Use a quick draft from the static scan instead?", default=True):
            return explore("offline", cfg, s)
        return None
