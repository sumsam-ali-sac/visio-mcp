"""SVG units and attribute markup: escaping, numbers, fonts, colors, strokes."""

from __future__ import annotations

import math
import re

from visio_mcp.style import ShapeStyle

PX = 96.0  # px per inch
PT = 96.0 / 72.0  # px per point
LINE_H = 1.25  # line height / font size

_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def esc(s: object) -> str:
    """Escape text for XML content and attribute values."""
    t = _BAD_XML.sub("", str(s))
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def snap(v: float) -> float:
    """Put a coordinate on a pixel center so 1px strokes stay crisp."""
    return math.floor(v) + 0.5


def font_stack(font: str) -> str:
    f = font.strip().replace("'", "")
    low = f.lower()
    if low in ("arial", "helvetica"):
        return f"{f}, 'Helvetica Neue', Helvetica, 'Liberation Sans', sans-serif"
    return (f"'{f}', 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, "
            "'Liberation Sans', sans-serif")


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 128, 128, 128


def lum(c: str) -> float:
    """Perceived brightness 0..255."""
    r, g, b = _rgb(c)
    return (r * 299 + g * 587 + b * 114) / 1000


def _dash(pattern: str, weight_px: float) -> str:
    s = max(1.0, weight_px)
    if pattern == "dashed":
        return f"{num(4.5 * s + 1.5)} {num(2.5 * s + 1.5)}"
    if pattern == "dotted":
        return f"0.1 {num(2 * s + 2)}"
    return ""


def stroke_attrs(color: str | None, weight_pt: float, pattern: str = "solid") -> str:
    if not color:
        return ' stroke="none"'
    w = weight_pt * PT
    out = f' stroke="{esc(color)}" stroke-width="{num(w)}"'
    d = _dash(pattern, w)
    if d:
        out += f' stroke-dasharray="{d}"'
        if pattern == "dotted":
            out += ' stroke-linecap="round"'
    return out


def shape_attrs(st: ShapeStyle, shadow: bool = False) -> str:
    fill = esc(st.fill) if st.fill else "none"
    a = f' fill="{fill}"' + stroke_attrs(st.line, st.line_weight, st.line_pattern) + ' stroke-linejoin="round"'
    if shadow:
        a += ' filter="url(#shadow)"'
    return a
