"""`visio-ai doctor`: check Visio, the AI provider, coding apps and preview renderers."""

from __future__ import annotations

import platform
import shutil
from typing import Any

from rich.text import Text

from visio_mcp import icons
from visio_mcp.ai import config as aiconfig
from visio_mcp.cli import coding_apps, ui
from visio_mcp.output.drawer import default_out_dir, visio_available


def _mark(good: bool, text: str, fix: str = "") -> Text:
    return Text.assemble(("✔ " if good else "▲ ", "good" if good else "warn"), text,
                         (f"  — {fix}" if fix and not good else "", "muted"))


def _has_playwright() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def _provider_row() -> tuple[str, Text]:
    cfg = aiconfig.load_config()
    if cfg.provider:
        key = bool(aiconfig.resolve_key(cfg.provider)) or cfg.provider.provider == "ollama"
        return "AI provider", _mark(key, f"{cfg.provider.provider} · {cfg.provider.model}",
                                    "API key missing: run visio-ai setup")
    found = aiconfig.detect_providers(probe_ollama=True)
    return "AI provider", _mark(bool(found), "not set" + (
        f" (detected: {', '.join(p.provider for p in found)})" if found else ""), "run visio-ai setup")


def run(args: Any) -> int:
    ui.banner("Checking your setup.")
    has_visio = visio_available()
    png = _has_playwright() or has_visio
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    tools = coding_apps.installed_tools()
    packs = {p: st for p, st in icons.status().items() if st["count"]}
    rows: list[tuple[str, Any]] = [
        ("System", f"{platform.system()} {platform.release()} · Python {platform.python_version()}"),
        ("Visio desktop", _mark(has_visio, "installed — diagrams draw live" if has_visio else "not found",
                                "native .vsdx output will be used (opens in Visio / Visio for the web)")),
        ("Config", str(aiconfig.CONFIG_PATH)),
        _provider_row(),
        ("AI coding apps", _mark(bool(tools), ", ".join(t.name for t in tools) or "none",
                                 "optional: Claude Code, Gemini CLI, Codex, Copilot CLI")),
        ("PNG previews", _mark(png, "available" if png else "not available",
                               "optional: pip install playwright && playwright install chromium")),
        ("PDF without Visio", _mark(bool(soffice) or has_visio, "LibreOffice" if soffice else "not available",
                                    "optional: install LibreOffice")),
        ("Cloud icons", _mark(len(packs) == len(icons.PROVIDERS),
                              ", ".join(f"{icons.PROVIDER_NAMES[p]} ({st['count']})" for p, st in packs.items())
                              or "not installed", "visio-ai icons install")),
        ("Output folder", str(default_out_dir())),
    ]
    ui.console.print(ui.panel(ui.kv_table(rows), title="visio-ai doctor"))
    return 0
