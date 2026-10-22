"""Connectors glued between shapes, their routing and label style, and free lines."""

from __future__ import annotations

from typing import Any

from visio_mcp.output.visio import formatting, text
from visio_mcp.output.visio.backend import ArrowMode, LinePattern
from visio_mcp.output.visio.cells import ARROW_SIZE_MEDIUM, LINE_PATTERNS, inch, pt, rgb, set_cell
from visio_mcp.output.visio.names import set_name
from visio_mcp.output.visio.text import FontFormula
from visio_mcp.style import EdgeStyle

STENCIL, MASTER = "BASFLO_U.VSSX", "Dynamic connector"
ROUTE_RIGHT_ANGLE = 1  # visLORouteRightAngle (ShapeRouteStyle)
ROUTE_EXT_STRAIGHT = 1  # visLORouteExtStraight (ConLineRouteExt; 2 = curved)
JUMP_ARC = 1  # visLOJumpStyleArc (ConLineJumpStyle)


def connect(page: Any, name: str, source: Any, target: Any, master: Any, label: str,
            pattern: LinePattern, arrow: ArrowMode) -> Any:
    """Drop a dynamic connector glued to both shapes as a whole (it picks the sides)."""
    conn = page.Drop(master, 0, 0)
    conn.CellsU("BeginX").GlueTo(source.CellsU("PinX"))
    conn.CellsU("EndX").GlueTo(target.CellsU("PinX"))
    set_name(conn, name)
    conn.Text = label
    conn.CellsU("LinePattern").FormulaU = str(LINE_PATTERNS[pattern])
    formatting.arrows(conn, arrow)
    return conn


def style(conn: Any, st: EdgeStyle, color: str | None, font: FontFormula, restyle_text: bool = True) -> None:
    """Line color/weight, right-angle routing with rounded corners, label font and backdrop."""
    set_cell(conn, "LineColor", rgb(color or st.color))
    set_cell(conn, "LineWeight", pt(st.weight))
    set_cell(conn, "LineColorTrans", "0%")
    set_cell(conn, "Rounding", inch(st.corner))
    set_cell(conn, "ShapeRouteStyle", str(ROUTE_RIGHT_ANGLE))
    set_cell(conn, "ConLineRouteExt", str(ROUTE_EXT_STRAIGHT))
    set_cell(conn, "ConLineJumpStyle", str(JUMP_ARC))
    set_cell(conn, "BeginArrowSize", str(ARROW_SIZE_MEDIUM))
    set_cell(conn, "EndArrowSize", str(ARROW_SIZE_MEDIUM))
    formatting.shadow(conn, False)
    if restyle_text:
        text.text_style(conn, st.text, font)
    text.paragraphs(conn, "center")
    if st.label_bg:  # TextBkgnd 0 is transparent, so pure black becomes RGB(1,1,1)
        bg = rgb(st.label_bg)
        set_cell(conn, "TextBkgnd", "RGB(1,1,1)" if bg == "RGB(0,0,0)" else bg)
        set_cell(conn, "TextBkgndTrans", "0%")
    else:
        set_cell(conn, "TextBkgnd", "0")


def line(page: Any, name: str, x1: float, y1: float, x2: float, y2: float, st: EdgeStyle,
         pattern: LinePattern, arrow: ArrowMode) -> Any:
    """A free line not glued to shapes (legend samples)."""
    shape = page.DrawLine(x1, y1, x2, y2)
    set_name(shape, name)
    set_cell(shape, "LineColor", rgb(st.color))
    set_cell(shape, "LineWeight", pt(st.weight))
    set_cell(shape, "LinePattern", str(LINE_PATTERNS[pattern]))
    set_cell(shape, "BeginArrowSize", str(ARROW_SIZE_MEDIUM))
    set_cell(shape, "EndArrowSize", str(ARROW_SIZE_MEDIUM))
    formatting.shadow(shape, False)
    formatting.arrows(shape, arrow)
    return shape
