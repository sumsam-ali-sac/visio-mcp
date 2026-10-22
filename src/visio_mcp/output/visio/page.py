"""Page size, the page background rectangle and z-order above it."""

from __future__ import annotations

from typing import Any

from visio_mcp.output.visio.cells import OBJ_TYPE_NONE, rgb, set_cell, set_cells
from visio_mcp.output.visio.names import find_opt, set_name

BACKGROUND = "__background"
DRAWING_SIZE_CUSTOM = 3  # DrawingSizeType: custom page size
DRAWING_NO_AUTO_RESIZE = 2  # DrawingResizeType: do not grow the page as shapes move


def set_size(page: Any, width: float, height: float, background: str | None) -> None:
    """Fixed page size in inches; background '#RRGGBB' covers the page (None removes it)."""
    sheet = page.PageSheet
    set_cell(sheet, "DrawingSizeType", str(DRAWING_SIZE_CUSTOM))
    set_cell(sheet, "DrawingResizeType", str(DRAWING_NO_AUTO_RESIZE))
    sheet.CellsU("PageWidth").ResultIU = width
    sheet.CellsU("PageHeight").ResultIU = height
    bg = find_opt(page, BACKGROUND)
    if background is None:
        if bg is not None:
            bg.Delete()
    else:
        draw_background(page, rgb(background), bg)


def draw_background(page: Any, fill_formula: str, bg: Any | None) -> None:
    """A locked page-sized rectangle at the very back that layout and routing ignore."""
    sheet = page.PageSheet
    w, h = sheet.CellsU("PageWidth").ResultIU, sheet.CellsU("PageHeight").ResultIU
    if bg is None:
        bg = page.DrawRectangle(0, 0, w, h)
        set_name(bg, BACKGROUND)
    else:
        for cell, v in (("Width", w), ("Height", h), ("PinX", w / 2), ("PinY", h / 2)):
            bg.CellsU(cell).ResultIU = v
    set_cells(bg, {
        "FillForegnd": fill_formula,
        "FillBkgnd": fill_formula,
        "FillPattern": "1",
        "LinePattern": "0",
        "ShdwPattern": "0",
        "ObjType": str(OBJ_TYPE_NONE),
        "ShapePermeableX": "TRUE",  # connectors route straight across it
        "ShapePermeableY": "TRUE",
        "ShapePermeablePlace": "TRUE",
        "LockSelect": "1",
        "LockTextEdit": "1",
    })
    bg.SendToBack()


def to_back(page: Any, shape: Any) -> None:
    """Send a shape to the back, but keep it in front of the page background."""
    shape.SendToBack()
    if shape.NameU != BACKGROUND:
        bg = find_opt(page, BACKGROUND)
        if bg is not None:
            bg.SendToBack()
