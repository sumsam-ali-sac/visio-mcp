"""Themes, typography, text casing and node sizing: how a diagram looks.

model    style dataclasses and the Theme that bundles them
themes   built-in themes and get_theme
text     label casing, text width, word wrap
sizing   node footprints
"""

from dataclasses import replace

from visio_mcp.style.model import (
    CATEGORIES,
    EdgeStyle,
    GroupStyle,
    LinePattern,
    ShapeStyle,
    TextStyle,
    Theme,
)
from visio_mcp.style.sizing import GEOMETRY_MIN, ICON_SIZE, NodeSize, node_size
from visio_mcp.style.text import sentence_case, text_width, title_case, wrap
from visio_mcp.style.themes import (
    AWS,
    AZURE,
    BLUEPRINT,
    C4,
    DARK,
    GCP,
    MONO,
    PROFESSIONAL,
    THEMES,
    get_theme,
)

__all__ = [
    "AWS", "AZURE", "BLUEPRINT", "C4", "CATEGORIES", "DARK", "GCP", "GEOMETRY_MIN", "ICON_SIZE", "MONO",
    "PROFESSIONAL", "THEMES", "EdgeStyle", "GroupStyle", "LinePattern", "NodeSize", "ShapeStyle", "TextStyle",
    "Theme", "get_theme", "node_size", "replace", "sentence_case", "text_width", "title_case", "wrap",
]
