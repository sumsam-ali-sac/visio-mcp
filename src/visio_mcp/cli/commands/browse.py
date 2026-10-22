"""`visio-ai themes`, `kinds` and `rules`: browse what a spec can use."""

from __future__ import annotations

from typing import Any

from rich.markdown import Markdown
from rich.text import Text

from visio_mcp import catalog, rules, style
from visio_mcp.cli import ui


def themes(args: Any) -> int:
    t = ui.table("Theme", "Font", "Palette", "Use it for")
    for th in style.THEMES.values():
        sw = Text()
        for cat in ("compute", "data", "integration", "network", "security"):
            sw.append("■ ", style=th.node_style(cat).line or "white")
        t.add_row(Text(th.name, style="key"), th.title.font, sw, Text(th.description, style="muted"))
    ui.console.print(t)
    return 0


def kinds(args: Any) -> int:
    ui.console.print(Markdown(catalog.describe_kinds(args.provider)))
    return 0


def rules_(args: Any) -> int:
    ui.console.print(Markdown(rules.get_rules(args.type, args.provider)))
    return 0
