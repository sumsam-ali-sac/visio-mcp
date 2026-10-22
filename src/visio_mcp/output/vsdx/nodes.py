"""Node shapes: geometry, text (inside, or below icons and people) and icon tiles or pictures."""

from __future__ import annotations

from visio_mcp.layout import Rect
from visio_mcp.style import TextRun
from visio_mcp.output.vsdx import shapes
from visio_mcp.output.vsdx.cells import V_MIDDLE, V_TOP, cell, color, length, num
from visio_mcp.output.vsdx.geometry import H, geometry_xml, hline
from visio_mcp.output.vsdx.images import picture
from visio_mcp.output.vsdx.page import Page, Shape
from visio_mcp.output.vsdx.text import text_height, text_xml
from visio_mcp.plan import DiagramPlan, PlannedNode
from visio_mcp.style import TextStyle, replace

ICON_LABEL_GAP = 0.06  # inches between an icon tile and its label below
GROUP_CELLS = ("SelectMode", 0), ("DisplayMode", 2), ("IsTextEditTarget", 1), ("IsSnapTarget", 1), \
    ("DontMoveChildren", 0)


def draw_node(page: Page, plan: DiagramPlan, n: PlannedNode) -> None:
    st, sh = n.style, n.shape
    geom = n.geometry
    below = geom in ("icon", "person") or n.icon
    runs = _readable_below(n.runs, plan) if below else n.runs
    png = page.pngs.get(n.image) if n.image is not None else None
    if geom == "icon" and png is not None:
        # an invisible frame (glue target, label below) grouping the picture
        s = shapes.box(page, n.id, sh, replace(st, fill=None, line=None, shadow=False), "rect")
    elif geom == "icon":
        tile = replace(st, fill=st.line or st.fill or "#64748B", line=None, line_weight=0)
        s = shapes.box(page, n.id, sh, tile, "icon")
    else:
        s = shapes.box(page, n.id, sh, st, geom, valign=V_TOP if geom == "entity" else V_MIDDLE)
        if geom == "entity" and n.runs:
            band = sh.h - min(sh.h * 0.5, n.runs[0].style.size * 1.3 / 72 + 0.14)
            s.sections.append(geometry_xml([hline(H(1, band - sh.h))], sh.w, sh.h, start_ix=1))
    page.fonts_of(runs)
    s.set_text(*text_xml(runs, "center"))
    if below:
        _move_text_below(s, n)
    if geom != "icon":
        page.add(s)
        return
    # glyph (or picture) rides along inside a group, so it and the label move as one node
    s.type = "Group"
    s.cells += [cell(k, v) for k, v in GROUP_CELLS]
    inner = Rect(sh.w / 2, sh.h / 2, sh.w, sh.h)
    child = picture(page, f"__icon_{n.id}", inner, png) if png is not None else _glyph_text(page, n, inner)
    child.cells += [cell("LockSelect", 1), cell("LockTextEdit", 1)]
    s.children.append(child)
    page.add(s)


def _glyph_text(page: Page, n: PlannedNode, inner: Rect) -> Shape:
    glyph = _glyph(n)
    size = 16 if len(glyph) <= 1 else 13 if len(glyph) == 2 else 10
    size = min(size, n.shape.h * 72 * 0.38)
    gst = TextStyle(font=n.style.text.font, size=size, color="#FFFFFF", bold=True)
    return shapes.text(page, f"__glyph_{n.id}", inner, [TextRun(glyph, gst)], align="center")


def _move_text_below(s: Shape, n: PlannedNode) -> None:
    """Replace the default whole-shape text block with one under the shape."""
    tx, ty, tw, th = _label_below(n)
    s.cells = [c for c in s.cells if not c.startswith(('<Cell N="Txt', '<Cell N="VerticalAlign"'))]
    s.cells += [cell("VerticalAlign", V_TOP),
                length("TxtPinX", tx, "Width*0.5"), length("TxtPinY", ty, num(ty)),
                length("TxtWidth", tw), length("TxtHeight", th),
                length("TxtLocPinX", tw / 2, "TxtWidth*0.5"), length("TxtLocPinY", th / 2, "TxtHeight*0.5"),
                cell("TxtAngle", 0.0)]


def _label_below(n: PlannedNode) -> tuple[float, float, float, float]:
    """Text block under an icon/person shape, inside the node footprint (local coords)."""
    s, r = n.shape, n.rect
    top = s.bottom - ICON_LABEL_GAP
    bottom = min(r.bottom, top - text_height(n.runs) - 0.04)
    th = max(0.2, top - bottom)
    tw = max(r.w, s.w)
    return (s.w / 2, (top - th / 2) - s.bottom, tw, th)


def _luma(c: str) -> float:
    c = color(c)
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return (r * 299 + g * 587 + b * 114) / 1000


def _readable_below(runs: list[TextRun], plan: DiagramPlan) -> list[TextRun]:
    """A label under an icon sits on the page, not the shape: text styled for a dark node fill
    (C4 people: white) would vanish, so it takes the page's text colors instead."""
    bg = _luma(plan.theme.background)
    out = []
    for i, r in enumerate(runs):
        if abs(_luma(r.style.color) - bg) < 90:
            c = plan.theme.title.color if i == 0 else plan.theme.subtitle.color
            r = TextRun(r.text, replace(r.style, color=c))
        out.append(r)
    return out


def _glyph(n: PlannedNode) -> str:
    if n.glyph:
        return n.glyph
    words = [w for w in n.label.split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"
