"""Primitive shapes (box, text block, line) and the cell groups they are made of."""

from __future__ import annotations

from visio_mcp.layout import Rect
from visio_mcp.style import TextRun
from visio_mcp.output.vsdx.cells import (
    ARROW_FILLED,
    ARROW_SIZE,
    LINE_PATTERNS,
    OBJ_IGNORE,
    OBJ_PLACEABLE,
    OBJ_ROUTABLE,
    V_MIDDLE,
    cell,
    color,
    length,
    points,
)
from visio_mcp.output.vsdx.geometry import Row, Section, geometry, geometry_xml, rect
from visio_mcp.output.vsdx.page import STYLE_CONNECTOR, STYLE_TEXT, Page, Shape
from visio_mcp.output.vsdx.text import text_xml
from visio_mcp.style import ShapeStyle

Margins = tuple[float, float, float, float]  # left, right, top, bottom in points
DEFAULT_MARGINS: Margins = (4, 4, 2, 2)


def xform(x: float, y: float, w: float, h: float) -> list[str]:
    return [
        length("PinX", x), length("PinY", y), length("Width", w), length("Height", h),
        length("LocPinX", w / 2, "Width*0.5"), length("LocPinY", h / 2, "Height*0.5"),
        cell("Angle", 0.0), cell("FlipX", 0), cell("FlipY", 0), cell("ResizeMode", 0),
    ]


def line_cells(style: ShapeStyle) -> list[str]:
    if not style.line:
        return [cell("LinePattern", 0), points("LineWeight", 0.75), cell("LineColor", "#000000")]
    return [
        points("LineWeight", style.line_weight),
        cell("LineColor", color(style.line)),
        cell("LinePattern", LINE_PATTERNS.get(style.line_pattern, 1)),
        length("Rounding", 0.0),
        cell("LineCap", 0),
        cell("BeginArrow", 0),
        cell("EndArrow", 0),
    ]


def fill_cells(style: ShapeStyle) -> list[str]:
    if not style.fill:
        return [cell("FillPattern", 0), cell("FillForegnd", "#FFFFFF")]
    cells = [cell("FillForegnd", color(style.fill)), cell("FillBkgnd", color(style.fill)),
             cell("FillPattern", 1), cell("FillForegndTrans", 0), cell("FillBkgndTrans", 0)]
    if style.shadow:
        cells += [cell("ShdwForegnd", "#000000"), cell("ShdwForegndTrans", 0.82), cell("ShdwPattern", 1),
                  cell("ShapeShdwType", 1), length("ShapeShdwOffsetX", 0.03), length("ShapeShdwOffsetY", -0.03)]
    else:
        cells.append(cell("ShdwPattern", 0))
    return cells


def text_block(w: float, h: float, *, valign: int = V_MIDDLE, margins_pt: Margins = DEFAULT_MARGINS,
               bkgnd: str | None = None, txt: tuple[float, float, float, float] | None = None,
               txt_f: tuple[str | None, str | None, str | None, str | None] | None = None) -> list[str]:
    """Text block cells. txt = (TxtPinX, TxtPinY, TxtWidth, TxtHeight) in local inches; default
    is the whole shape."""
    left, right, top, bottom = margins_pt
    if txt is None:
        txt = (w / 2, h / 2, w, h)
        txt_f = ("Width*0.5", "Height*0.5", "Width*1", "Height*1")
    txt_f = txt_f or (None, None, None, None)
    tx, ty, tw, th = txt
    return [
        points("LeftMargin", left), points("RightMargin", right), points("TopMargin", top),
        points("BottomMargin", bottom),
        cell("VerticalAlign", valign),
        *([cell("TextBkgnd", color(bkgnd)), cell("TextBkgndTrans", 0)] if bkgnd else []),
        cell("TextDirection", 0),
        length("TxtPinX", tx, txt_f[0]), length("TxtPinY", ty, txt_f[1]),
        length("TxtWidth", tw, txt_f[2]), length("TxtHeight", th, txt_f[3]),
        length("TxtLocPinX", tw / 2, "TxtWidth*0.5"), length("TxtLocPinY", th / 2, "TxtHeight*0.5"),
        cell("TxtAngle", 0.0),
    ]


def user_section(rows: dict[str, tuple[str, str | None, str | None]]) -> str:
    """User-defined cells: name -> (value, unit, formula)."""
    out = []
    for name, (v, u, f) in rows.items():
        out.append(f'<Row N="{name}">{cell("Value", v, u, f)}{cell("Prompt", "", "STR")}</Row>')
    return '<Section N="User">' + "".join(out) + "</Section>"


def box(page: Page, name: str, r: Rect, style: ShapeStyle, geom: str = "rect", runs: list[TextRun] | None = None,
        align: str = "center", valign: int = V_MIDDLE, obj: int = OBJ_PLACEABLE, rounding: float | None = None,
        margins_pt: Margins = DEFAULT_MARGINS) -> Shape:
    """A 2-D shape of geometry geom filling r, optionally with text."""
    s = Shape(page.new_id(), name)
    s.cells += xform(r.x, r.y, r.w, r.h)
    s.cells += line_cells(style) + fill_cells(style)
    s.cells.append(cell("ObjType", obj))
    s.cells += text_block(r.w, r.h, valign=valign, margins_pt=margins_pt)
    rnd = style.rounding if rounding is None else rounding
    s.sections.append(geometry_xml(geometry(geom, r.w, r.h, rnd), r.w, r.h))
    if runs:
        page.fonts_of(runs)
        s.set_text(*text_xml(runs, align))
    return s


def text(page: Page, name: str, r: Rect, runs: list[TextRun], align: str = "left", valign: int = V_MIDDLE) -> Shape:
    """A borderless, transparent, margin-free text block that connectors ignore."""
    s = Shape(page.new_id(), name, style=STYLE_TEXT)
    s.cells += xform(r.x, r.y, r.w, r.h)
    s.cells += [cell("LinePattern", 0), cell("FillPattern", 0), cell("ObjType", OBJ_IGNORE)]
    s.cells += text_block(r.w, r.h, valign=valign, margins_pt=(0, 0, 0, 0))
    s.sections.append(geometry_xml([Section(rect().rows, no_fill=True, no_line=True)], r.w, r.h))
    page.fonts_of(runs)
    s.set_text(*text_xml(runs, align))
    return s


def line(page: Page, name: str, pts: list[tuple[float, float]], line_color: str, weight_pt: float, pattern: str,
         arrow: str, rounding: float = 0.0, routable: bool = False, arrow_size: int = ARROW_SIZE) -> Shape:
    """A 1-D shape following pts (page inches): connector-style transform, begin at local (0, 0)."""
    (bx, by), (ex, ey) = pts[0], pts[-1]
    w, h = ex - bx, ey - by
    s = Shape(page.new_id(), name, style=STYLE_CONNECTOR)
    s.cells += [
        length("PinX", (bx + ex) / 2, "GUARD((BeginX+EndX)/2)"),
        length("PinY", (by + ey) / 2, "GUARD((BeginY+EndY)/2)"),
        length("Width", w, "GUARD(EndX-BeginX)"),
        length("Height", h, "GUARD(EndY-BeginY)"),
        length("LocPinX", w / 2, "GUARD(Width*0.5)"),
        length("LocPinY", h / 2, "GUARD(Height*0.5)"),
        cell("Angle", 0.0, None, "GUARD(0DEG)"),
        cell("FlipX", 0, None, "GUARD(FALSE)"),
        cell("FlipY", 0, None, "GUARD(FALSE)"),
        cell("ResizeMode", 0),
        length("BeginX", bx), length("BeginY", by), length("EndX", ex), length("EndY", ey),
        points("LineWeight", weight_pt),
        cell("LineColor", color(line_color)),
        cell("LinePattern", LINE_PATTERNS.get(pattern, 1)),
        length("Rounding", rounding),
        cell("BeginArrow", ARROW_FILLED if arrow == "both" else 0),
        cell("EndArrow", 0 if arrow == "none" else ARROW_FILLED),
        cell("BeginArrowSize", arrow_size),
        cell("EndArrowSize", arrow_size),
        cell("LineCap", 0),
        cell("FillPattern", 0),
        cell("ObjType", OBJ_ROUTABLE if routable else OBJ_IGNORE),
    ]
    rows: list[Row] = [("MoveTo", {"X": 0.0, "Y": 0.0})]
    for x, y in pts[1:]:
        rows.append(("LineTo", {"X": x - bx, "Y": y - by}))
    s.sections.append(geometry_xml([Section(rows, no_fill=True)], w, h))
    return s
