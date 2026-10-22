"""Terminal output: palette, banner, status lines, panels, tables and spinners."""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

ACCENT = "#7C9CFF"
ACCENT2 = "#5EEAD4"
MUTED = "#8B93A7"
GOOD = "#4ADE80"
WARN = "#FBBF24"
BAD = "#F87171"

console = Console(
    theme=Theme({
        "accent": f"bold {ACCENT}", "accent2": ACCENT2, "muted": MUTED, "good": GOOD,
        "warn": WARN, "bad": BAD, "key": f"bold {ACCENT2}", "title": "bold white",
    }),
    highlight=False,
)

_LOGO = [
    "██╗   ██╗██╗███████╗██╗ ██████╗      █████╗ ██╗",
    "██║   ██║██║██╔════╝██║██╔═══██╗    ██╔══██╗██║",
    "██║   ██║██║███████╗██║██║   ██║    ███████║██║",
    "╚██╗ ██╔╝██║╚════██║██║██║   ██║    ██╔══██║██║",
    " ╚████╔╝ ██║███████║██║╚██████╔╝    ██║  ██║██║",
    "  ╚═══╝  ╚═╝╚══════╝╚═╝ ╚═════╝     ╚═╝  ╚═╝╚═╝",
]
_GRADIENT = ["#7C9CFF", "#7AA8FA", "#74B6F2", "#6CC5E6", "#64D6DA", "#5EEAD4"]


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("CI")


def banner(subtitle: str = "Professional Visio diagrams from your code, drawn live.") -> None:
    if console.width >= 60:
        logo = Text()
        for line, color in zip(_LOGO, _GRADIENT):
            logo.append(line + "\n", style=f"bold {color}")
        console.print(logo, end="")
    else:
        console.print(Text("visio·ai", style="accent"))
    console.print(Text(f"  {subtitle}", style="muted"))
    console.print()


def step(n: int, total: int, title: str) -> None:
    console.print()
    console.print(Rule(Text.assemble((f" {n}/{total} ", f"bold black on {ACCENT}"), "  ", (title, "title")),
                       style=MUTED, align="left"))


def ok(msg: str) -> None:
    console.print(Text.assemble(("  ✔ ", "good"), msg))


def warn(msg: str) -> None:
    console.print(Text.assemble(("  ▲ ", "warn"), msg))


def fail(msg: str, hint: str = "") -> None:
    console.print(Text.assemble(("  ✖ ", "bad"), msg))
    if hint:
        console.print(Text(f"    {hint}", style="muted"))


def info(msg: str) -> None:
    """A bullet line; msg may use rich markup like [bold]…[/]."""
    console.print(Text.assemble(("  • ", "muted"), Text.from_markup(msg)))


def hint(msg: str) -> None:
    console.print(Text(f"  {msg}", style="muted"))


def kv_table(rows: Sequence[tuple[str, Any]]) -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="muted", no_wrap=True)
    t.add_column()
    for k, v in rows:
        t.add_row(k, v if isinstance(v, Text) else Text(str(v)))
    return t


def panel(body: Any, title: str = "", style: str = ACCENT, subtitle: str = "") -> Panel:
    return Panel(body, title=Text(f" {title} ", style=f"bold {style}") if title else None,
                 subtitle=Text(subtitle, style="muted") if subtitle else None,
                 border_style=style, box=box.ROUNDED, padding=(1, 2))


def table(*columns: str, title: str | None = None) -> Table:
    t = Table(box=box.SIMPLE_HEAD, header_style=f"bold {ACCENT}", title=title, title_style="bold",
              title_justify="left", pad_edge=False, expand=False)
    for c in columns:
        t.add_column(c)
    return t


def print_json(data: Any) -> None:
    console.print(Syntax(json.dumps(data, indent=2), "json", theme="ansi_dark"))


@contextmanager
def spinner(message: str) -> Iterator[Any]:
    with console.status(Text(message, style="muted"), spinner="dots12", spinner_style=ACCENT) as status:
        yield status
