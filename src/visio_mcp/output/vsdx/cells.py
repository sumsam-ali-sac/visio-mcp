"""ShapeSheet <Cell> XML: number, color and text formatting plus the shared cell constants."""

from __future__ import annotations

from xml.sax.saxutils import quoteattr

ARROW_FILLED = 13  # same arrowhead the COM backend uses
ARROW_SIZE = 2  # medium
LINE_PATTERNS = {"solid": 1, "dashed": 2, "dotted": 3}
H_ALIGN = {"left": 0, "center": 1, "right": 2}
V_TOP, V_MIDDLE = 0, 1

# ObjType: 1 placeable (connectors route around it), 2 routable (a connector),
# 4 neither (backgrounds, frames, decorations: connectors ignore them)
OBJ_PLACEABLE, OBJ_ROUTABLE, OBJ_IGNORE = 1, 2, 4


def num(v: float) -> str:
    """Compact number for a V attribute."""
    if abs(v) < 5e-10:
        return "0"
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def color(c: str | None, default: str = "#000000") -> str:
    """'#RGB' or '#RRGGBB' (any case) -> '#RRGGBB'."""
    c = (c or default).strip()
    if len(c) == 4 and c.startswith("#"):
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c.upper()


def clean(text: str) -> str:
    """Drop characters XML 1.0 cannot hold; Visio's paragraph separator is LF."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 0x20)


def attrs(**kw: object) -> str:
    """XML attributes, skipping None values."""
    return "".join(f" {k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


def cell(name: str, v: object, u: str | None = None, f: str | None = None) -> str:
    if isinstance(v, float):
        v = num(v)
    return f"<Cell{attrs(N=name, V=v, U=u, F=f)}/>"


def length(name: str, inches: float, f: str | None = None) -> str:
    return cell(name, float(inches), None, f)


def points(name: str, pt: float) -> str:
    """A length shown in points; V is always inches."""
    return cell(name, pt / 72.0, "PT")
