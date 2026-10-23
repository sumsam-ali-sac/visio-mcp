"""Interactive prompts (questionary) styled to match the terminal app."""

from __future__ import annotations

from typing import Any

import questionary

from visio_mcp.cli.ui import ACCENT, ACCENT2, MUTED

QSTYLE = questionary.Style([
    ("qmark", f"fg:{ACCENT} bold"),
    ("question", "bold"),
    ("answer", f"fg:{ACCENT2} bold"),
    ("pointer", f"fg:{ACCENT} bold"),
    ("highlighted", f"fg:{ACCENT} bold"),
    ("selected", f"fg:{ACCENT2}"),
    ("separator", f"fg:{MUTED}"),
    ("instruction", f"fg:{MUTED} italic"),
    ("text", ""),
    ("disabled", f"fg:{MUTED} italic"),
])


class Cancelled(Exception):
    """The user pressed Ctrl+C / Esc in a prompt."""


def _ask(q: questionary.Question) -> Any:
    ans = q.ask()
    if ans is None:
        raise Cancelled
    return ans


def select(message: str, choices: list[questionary.Choice | str], default: Any = None,
           instruction: str = "↑↓ move · enter select") -> Any:
    return _ask(questionary.select(message, choices=choices, default=default, style=QSTYLE,
                                   qmark="◆", instruction=instruction, use_shortcuts=False))


def checkbox(message: str, choices: list[questionary.Choice], instruction: str = "space toggle · enter confirm") -> list:
    return _ask(questionary.checkbox(message, choices=choices, style=QSTYLE, qmark="◆", instruction=instruction))


def text(message: str, default: str = "", instruction: str | None = None) -> str:
    return _ask(questionary.text(message, default=default, style=QSTYLE, qmark="◆", instruction=instruction))


def password(message: str, instruction: str | None = None) -> str:
    return _ask(questionary.password(message, style=QSTYLE, qmark="◆", instruction=instruction))


def confirm(message: str, default: bool = True) -> bool:
    return _ask(questionary.confirm(message, default=default, style=QSTYLE, qmark="◆"))


def path(message: str, default: str = "") -> str:
    return _ask(questionary.path(message, default=default, only_directories=True, style=QSTYLE, qmark="◆"))


def choice(title: str, value: Any, description: str = "", disabled: str | None = None) -> questionary.Choice:
    label = [("class:text", title)]
    if description:
        label.append(("class:instruction", f"  {description}"))
    return questionary.Choice(title=label, value=value, disabled=disabled)
