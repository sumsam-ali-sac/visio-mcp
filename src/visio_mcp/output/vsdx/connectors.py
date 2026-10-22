"""Edge shapes glued to their nodes with dynamic glue, plus the page's <Connect> records."""

from __future__ import annotations

import math

from visio_mcp.output.visio.backend import TextRun
from visio_mcp.output.vsdx import shapes
from visio_mcp.output.vsdx.cells import V_MIDDLE, attrs, cell, length
from visio_mcp.output.vsdx.page import Page
from visio_mcp.output.vsdx.text import text_height, text_xml
from visio_mcp.plan import DiagramPlan, PlannedEdge
from visio_mcp.style import text_width

# Connect parts: begin/end of a 1-D shape glued to the whole target (dynamic glue)
PART_BEGIN, PART_END, PART_WHOLE_SHAPE = 9, 12, 3
ENDPOINTS = ('<Cell N="BeginX"', '<Cell N="BeginY"', '<Cell N="EndX"', '<Cell N="EndY"')
BEGIN_GLUE = "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
END_GLUE = "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"


def draw_edge(page: Page, plan: DiagramPlan, e: PlannedEdge) -> None:
    pts = _route(plan, e)
    st = e.style
    s = shapes.line(page, e.name, pts, e.color, st.weight, e.pattern, e.arrow, rounding=st.corner, routable=True)
    src, dst = page.ids.get(e.source), page.ids.get(e.target)
    # dynamic glue: endpoints follow the shapes (Visio's own connector formulas)
    s.cells = [c for c in s.cells if not c.startswith(ENDPOINTS)]
    (bx, by), (ex, ey) = pts[0], pts[-1]
    if src is not None and dst is not None:
        s.cells += [
            length("BeginX", bx, BEGIN_GLUE), length("BeginY", by, BEGIN_GLUE),
            length("EndX", ex, END_GLUE), length("EndY", ey, END_GLUE),
            cell("BegTrigger", 2, None, f"_XFTRIGGER(Sheet.{src}!EventXFMod)"),
            cell("EndTrigger", 2, None, f"_XFTRIGGER(Sheet.{dst}!EventXFMod)"),
        ]
    else:
        s.cells += [length("BeginX", bx), length("BeginY", by), length("EndX", ex), length("EndY", ey)]
    s.cells += [
        cell("ShapeRouteStyle", 1),  # right angle
        cell("ConFixedCode", 1),  # keep our route; reroute only when a glued shape moves
        cell("ConLineJumpCode", 1),  # no line jumps (the preview has none)
        cell("ConLineRouteExt", 1),  # straight segments
        cell("GlueType", 0),
        cell("WalkPreference", 0),
    ]
    if e.label:
        runs = [TextRun(e.label, st.text)]
        mx, my = _midpoint(pts)
        tw = max(text_width(line, st.text.size, st.text.bold) for line in e.label.split("\n")) * 1.2 + 0.18
        th = text_height(runs) + 0.06
        s.cells += shapes.text_block(0, 0, valign=V_MIDDLE, margins_pt=(2, 2, 1, 1), bkgnd=st.label_bg,
                                     txt=(mx - bx, my - by, tw, th), txt_f=(None, None, None, None))
        page.fonts_of(runs)
        s.set_text(*text_xml(runs, "center"))
    page.add(s)
    if src is not None:
        page.connects.append(_connect(s.id, "BeginX", PART_BEGIN, src))
    if dst is not None:
        page.connects.append(_connect(s.id, "EndX", PART_END, dst))


def _connect(sheet: int, from_cell: str, part: int, to: int) -> str:
    return (f"<Connect{attrs(FromSheet=sheet, FromCell=from_cell, FromPart=part, ToSheet=to, ToCell='PinX', ToPart=PART_WHOLE_SHAPE)}/>")


def _route(plan: DiagramPlan, e: PlannedEdge) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in e.points]
    if len(pts) < 2:
        a, b = plan.node(e.source).shape, plan.node(e.target).shape
        pts = [(a.x, a.y), (b.x, b.y)]
    out = [pts[0]]
    for p in pts[1:]:  # drop repeated points (zero-length segments confuse renderers)
        if abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) < 2:
        out.append((out[0][0] + 1e-3, out[0][1]))
    return out


def _midpoint(pts: list[tuple[float, float]]) -> tuple[float, float]:
    segs = [(a, b, math.dist(a, b)) for a, b in zip(pts, pts[1:])]
    half = sum(s[2] for s in segs) / 2
    for a, b, d in segs:
        if half <= d and d > 0:
            t = half / d
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        half -= d
    return pts[-1]
