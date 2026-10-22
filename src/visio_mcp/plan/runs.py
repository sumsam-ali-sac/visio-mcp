"""Styled text runs for node labels and the text-width helper for plan frames."""

from __future__ import annotations

from dataclasses import replace

from visio_mcp import catalog
from visio_mcp.style import TextRun
from visio_mcp.style import TextStyle, Theme, text_width


def label_text(text: TextStyle, theme: Theme, icon: bool, kind: catalog.Kind | None) -> TextStyle:
    """Labels drawn under icons and people sit on the page, so they take the page's text color."""
    if icon or (kind is not None and kind.geometry == "person"):
        return replace(text, color=theme.title.color)
    return text


def node_runs(label: str, technology: str, description: str, text: TextStyle, theme: Theme,
               on_page: bool = False) -> list[TextRun]:
    color = theme.subtitle.color if on_page else secondary_color(text, theme)
    sec = replace(theme.secondary, color=color)
    runs = [TextRun(label, text)]
    if technology:
        runs.append(TextRun(f"\n[{technology}]", replace(sec, italic=False)))
    if description:
        runs.append(TextRun(f"\n{description}", sec))
    return runs


def secondary_color(text: TextStyle, theme: Theme) -> str:
    """Secondary text matches light-on-dark nodes (C4) instead of the theme default."""
    r, g, b = (int(text.color[i:i + 2], 16) for i in (1, 3, 5))
    light_text = (r * 299 + g * 587 + b * 114) / 1000 > 160
    if light_text and not theme.dark:
        return "#E8F1FB"
    return theme.secondary.color


def line_width(text: str, st: TextStyle) -> float:
    return text_width(text, st.size, st.bold) if text else 0.0
