"""Node shapes: drop masters and images, draw boxes and text blocks, style, move, delete, list."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pywintypes

from visio_mcp.output.visio import formatting, text
from visio_mcp.output.visio.backend import Align, ShapeInfo
from visio_mcp.style import TextRun
from visio_mcp.output.visio.cells import VERT_MIDDLE, inch, set_cell
from visio_mcp.output.visio.names import is_container, set_name
from visio_mcp.output.visio.text import FontFormula
from visio_mcp.style import ShapeStyle

TEXT_MARGIN = "2 pt"
MARGINS = ("LeftMargin", "RightMargin", "TopMargin", "BottomMargin")


def drop(page: Any, name: str, master: Any, x: float, y: float,
         width: float | None = None, height: float | None = None) -> Any:
    shape = page.Drop(master, x, y)
    set_name(shape, name)
    if width is not None:
        shape.CellsU("Width").ResultIU = width
    if height is not None:
        shape.CellsU("Height").ResultIU = height
    return shape


def image_file(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"icon file not found: {p}")
    return p


def import_image(page: Any, name: str, path: Path, x: float, y: float, width: float, height: float) -> Any:
    """Page.Import an .svg/.png (Visio 2016+) and fit it, aspect kept, into width x height at (x, y).

    An SVG may arrive as a picture or as a group of converted shapes; either takes text, so
    the label is set on the imported shape itself. Nothing is left on the page on failure.
    """
    shape = page.Import(str(path))
    try:
        set_name(shape, name)
        w0 = float(shape.CellsU("Width").ResultIU) or width
        h0 = float(shape.CellsU("Height").ResultIU) or height
        k = min(width / w0, height / h0) if w0 > 0 and h0 > 0 else 1.0
        set_cell(shape, "LockAspect", "0")
        set_cell(shape, "Width", inch(round(w0 * k, 4)))
        set_cell(shape, "Height", inch(round(h0 * k, 4)))
        set_cell(shape, "PinX", inch(x))
        set_cell(shape, "PinY", inch(y))
        set_cell(shape, "LockAspect", "1")
        set_cell(shape, "LockTextEdit", "0")
    except pywintypes.com_error:
        try:
            shape.Delete()
        except pywintypes.com_error:
            pass
        raise
    return shape


def fill(shape: Any, formula: str) -> None:
    shape.CellsU("FillForegnd").FormulaU = formula
    shape.CellsU("FillPattern").FormulaU = "1"


def style(shape: Any, st: ShapeStyle, font: FontFormula, keep_fill: bool = False,
          label_below: bool = False, restyle_text: bool = True) -> None:
    """Frame, shadow and centered text; restyle_text=False keeps styled runs' character rows."""
    if not keep_fill:
        formatting.frame(shape, st)
    formatting.shadow(shape, st.shadow and not keep_fill)
    if restyle_text:
        text.text_style(shape, st.text, font)
    text.paragraphs(shape, "center")
    for cell in MARGINS:
        set_cell(shape, cell, TEXT_MARGIN)
    set_cell(shape, "TextBkgnd", "0")  # transparent text block
    if label_below:
        text.label_below(shape)
    else:
        set_cell(shape, "VerticalAlign", str(VERT_MIDDLE))


def _rectangle(page: Any, name: str, x: float, y: float, width: float, height: float) -> Any:
    shape = page.DrawRectangle(x - width / 2, y - height / 2, x + width / 2, y + height / 2)
    set_name(shape, name)
    return shape


def box(page: Any, name: str, x: float, y: float, width: float, height: float,
        st: ShapeStyle, font: FontFormula) -> Any:
    shape = _rectangle(page, name, x, y, width, height)
    formatting.frame(shape, st)
    formatting.shadow(shape, st.shadow)
    text.text_style(shape, st.text, font)
    return shape


def text_block(page: Any, name: str, x: float, y: float, width: float, height: float,
               runs: list[TextRun], align: Align, font: FontFormula) -> Any:
    """A borderless, transparent, margin-free rectangle holding styled runs."""
    shape = _rectangle(page, name, x, y, width, height)
    set_cell(shape, "FillPattern", "0")
    set_cell(shape, "LinePattern", "0")
    formatting.shadow(shape, False)
    for cell in MARGINS:
        set_cell(shape, cell, "0 pt")
    set_cell(shape, "TextBkgnd", "0")
    set_cell(shape, "VerticalAlign", str(VERT_MIDDLE))
    text.write_runs(shape, runs, font)
    text.paragraphs(shape, align)
    return shape


def move(shape: Any, x: float, y: float) -> None:
    shape.CellsU("PinX").ResultIU = x
    shape.CellsU("PinY").ResultIU = y


def delete(page: Any, shape: Any, name: str) -> None:
    """Delete the shape and every connector glued to it."""
    doomed = [shape]
    for other in page.Shapes:
        if other.OneD and any(c.ToSheet.NameU == name for c in other.Connects):
            doomed.append(other)
    for s in doomed:
        s.Delete()


def infos(page: Any) -> list[ShapeInfo]:
    return [
        ShapeInfo(
            name=s.NameU,
            text=s.Text,
            master=s.Master.NameU if s.Master is not None else None,
            x=s.CellsU("PinX").ResultIU,
            y=s.CellsU("PinY").ResultIU,
            width=s.CellsU("Width").ResultIU,
            height=s.CellsU("Height").ResultIU,
            is_connector=bool(s.OneD),
            is_container=is_container(s),
        )
        for s in page.Shapes
    ]
