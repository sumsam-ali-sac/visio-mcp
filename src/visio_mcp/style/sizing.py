"""Node footprints: how much room the layout reserves for a node and its text."""

from __future__ import annotations

import math
from dataclasses import dataclass

from visio_mcp.style.model import Theme
from visio_mcp.style.text import text_width, wrap
from visio_mcp.style.themes import PROFESSIONAL


@dataclass(frozen=True)
class NodeSize:
    """Footprint the layout reserves for a node, and where the Visio shape sits inside it."""

    w: float
    h: float
    shape_w: float
    shape_h: float
    dy: float = 0.0  # shape center = footprint center + (0, dy); icons sit above their label


GEOMETRY_MIN = {  # (min width, min height) in inches per catalog geometry
    "rect": (1.6, 0.75),
    "rounded": (1.6, 0.75),
    "terminator": (1.5, 0.6),
    "decision": (1.7, 1.1),
    "parallelogram": (1.8, 0.75),
    "document": (1.6, 0.85),
    "cylinder": (1.2, 1.0),
    "queue": (1.7, 0.75),
    "hexagon": (1.7, 0.8),
    "ellipse": (1.5, 0.8),
    "circle": (0.9, 0.9),
    "cloud": (1.8, 1.1),
    "person": (1.2, 1.2),
    "note": (1.6, 0.8),
    "entity": (1.8, 0.9),
    "subprocess": (1.7, 0.75),
    "trapezoid": (1.7, 0.75),
    "icon": (0.7, 0.7),
}
ICON_SIZE = 0.7  # inches, square icon masters (cloud services, network gear, people)


def node_size(geometry: str, label: str, technology: str = "", description: str = "",
              theme: Theme = PROFESSIONAL, category: str = "generic") -> NodeSize:
    """Size a node so its text fits on at most a few lines, never smaller than the geometry minimum."""
    st = theme.node_style(category).text
    sec = theme.secondary
    if geometry in ("icon", "person"):
        # icon on top, label (and tech) below it, inside a footprint wide enough for the text
        max_w = 1.7
        lines = wrap(label, st.size, max_w, st.bold)
        tlines = wrap(f"[{technology}]", sec.size, max_w) if technology else []
        text_h = len(lines) * st.size * 1.25 / 72 + len(tlines) * sec.size * 1.25 / 72
        w = max(ICON_SIZE + 0.4, min(max_w, max(text_width(s, st.size, st.bold) for s in lines + [""])) + 0.25)
        h = ICON_SIZE + 0.12 + text_h
        return NodeSize(w=round(w, 2), h=round(h, 2), shape_w=ICON_SIZE, shape_h=ICON_SIZE,
                        dy=round((h - ICON_SIZE) / 2, 3))
    min_w, min_h = GEOMETRY_MIN.get(geometry, (1.6, 0.75))
    inner = {"decision": 0.55, "hexagon": 0.75, "ellipse": 0.7, "circle": 0.7, "cloud": 0.6,
             "parallelogram": 0.75, "trapezoid": 0.75}.get(geometry, 0.88)
    max_w = 2.6
    text_w = max_w * inner
    lines = wrap(label, st.size, text_w, st.bold)
    widest = max(text_width(s, st.size, st.bold) for s in lines)
    extra: list[str] = []
    if technology:
        extra += wrap(f"[{technology}]", sec.size, text_w)
    if description:
        extra += wrap(description, sec.size, text_w)[:3]
    widest = max([widest] + [text_width(s, sec.size) for s in extra])
    text_h = len(lines) * st.size * 1.3 / 72 + len(extra) * sec.size * 1.3 / 72
    w = max(min_w, min(max_w, widest / inner + 0.3))
    h = max(min_h, text_h / (inner if geometry in ("decision", "ellipse", "circle", "hexagon") else 1) + 0.3)
    if geometry == "circle":
        w = h = max(w, h)
    w, h = math.ceil(w * 8 - 1e-6) / 8, math.ceil(h * 8 - 1e-6) / 8  # snap up to 1/8 inch so rows line up
    return NodeSize(w=w, h=h, shape_w=w, shape_h=h)
