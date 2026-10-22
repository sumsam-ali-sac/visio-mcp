"""Fill, line, shadow and arrowhead formatting of a shape."""

from __future__ import annotations

from typing import Any

from visio_mcp.output.visio.backend import ArrowMode
from visio_mcp.output.visio.cells import ARROW_FILLED, LINE_PATTERNS, inch, pt, rgb, set_cell, set_cells
from visio_mcp.style import ShapeStyle

SHADOW = {
    "ShdwPattern": "1",
    "ShdwForegnd": "RGB(15,23,42)",
    "ShdwForegndTrans": "85%",
    "ShapeShdwType": "1",  # simple offset shadow
    "ShapeShdwOffsetX": "0.03 in",
    "ShapeShdwOffsetY": "-0.03 in",
}


def frame(shape: Any, style: ShapeStyle) -> None:
    """Fill, line and rounding as explicit local formulas (they override master/theme values)."""
    if style.fill is None:
        set_cell(shape, "FillPattern", "0")
    else:
        for cell in ("FillForegnd", "FillBkgnd"):
            set_cell(shape, cell, rgb(style.fill))
        set_cell(shape, "FillForegndTrans", "0%")
        set_cell(shape, "FillPattern", "1")
        set_cell(shape, "FillGradientEnabled", "FALSE")
    if style.line is None:
        set_cell(shape, "LinePattern", "0")
    else:
        set_cell(shape, "LineColor", rgb(style.line))
        set_cell(shape, "LineColorTrans", "0%")
        set_cell(shape, "LinePattern", str(LINE_PATTERNS[style.line_pattern]))
        set_cell(shape, "LineWeight", pt(style.line_weight))
        set_cell(shape, "LineGradientEnabled", "FALSE")
    set_cell(shape, "Rounding", inch(style.rounding))


def shadow(shape: Any, on: bool) -> None:
    if on:
        set_cells(shape, SHADOW)
    else:
        set_cell(shape, "ShdwPattern", "0")


def arrows(shape: Any, arrow: ArrowMode) -> None:
    shape.CellsU("BeginArrow").FormulaU = str(ARROW_FILLED if arrow == "both" else 0)
    shape.CellsU("EndArrow").FormulaU = str(0 if arrow == "none" else ARROW_FILLED)
