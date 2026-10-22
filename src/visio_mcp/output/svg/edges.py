"""SVG for edges: rounded orthogonal paths, arrowheads and labels on the longest segment."""

from __future__ import annotations

import math

from visio_mcp.output.svg.canvas import Canvas
from visio_mcp.output.svg.markup import PX, esc, num, snap, stroke_attrs
from visio_mcp.output.svg.text import block_h, layout_text, text_svg
from visio_mcp.style import TextRun
from visio_mcp.plan import PlannedEdge

LABEL_MAX_W = 2.2 * PX
LABEL_PAD_X, LABEL_PAD_Y = 6.0, 2.5


def edge(c: Canvas, e: PlannedEdge, idx: int) -> str:
    st = e.style
    head = (f'<g id="edge-{idx}" class="edge" data-id="{esc(e.name)}" data-source="{esc(e.source)}" '
            f'data-target="{esc(e.target)}">')
    pts = [(snap(c.X(x)), snap(c.Y(y))) for x, y in e.points]
    if len(pts) < 2:
        return head + "</g>"
    attrs = stroke_attrs(e.color, st.weight, e.pattern) + ' stroke-linejoin="round"'
    if e.pattern != "dotted":
        attrs += ' stroke-linecap="round"'
    if e.arrow in ("end", "both"):
        mid = c.marker(e.color, st.weight)
        attrs += f' marker-end="url(#{mid})"'
        if e.arrow == "both":
            attrs += f' marker-start="url(#{mid})"'
    out = [head, f'<path d="{rounded_path(pts, st.corner * PX)}"{attrs}/>']
    if e.label:
        best = max(range(len(pts) - 1), key=lambda i: math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
        mx = (pts[best][0] + pts[best + 1][0]) / 2
        my = (pts[best][1] + pts[best + 1][1]) / 2
        lines = layout_text([TextRun(e.label, st.text)], LABEL_MAX_W)
        tw = max(ln.width for ln in lines)
        th = block_h(lines)
        if st.label_bg:
            out.append(f'<rect class="edge-label-bg" x="{num(mx - tw / 2 - LABEL_PAD_X)}" y="{num(my - th / 2 - LABEL_PAD_Y)}" '
                       f'width="{num(tw + 2 * LABEL_PAD_X)}" height="{num(th + 2 * LABEL_PAD_Y)}" rx="3" '
                       f'fill="{esc(st.label_bg)}" stroke="none"/>')
        out.append(text_svg(lines, mx, my - th / 2))
    out.append("</g>")
    return "".join(out)


def rounded_path(pts: list[tuple[float, float]], radius: float) -> str:
    """Path through pts with corners rounded by up to radius px (collinear points stay sharp)."""
    p = [pts[0]]
    for q in pts[1:]:
        if abs(q[0] - p[-1][0]) > 1e-6 or abs(q[1] - p[-1][1]) > 1e-6:
            p.append(q)
    if len(p) < 2:
        return ""
    d = [f"M{num(p[0][0])} {num(p[0][1])}"]
    for i in range(1, len(p) - 1):
        (ax, ay), (bx, by), (cx_, cy_) = p[i - 1], p[i], p[i + 1]
        l1, l2 = math.hypot(bx - ax, by - ay), math.hypot(cx_ - bx, cy_ - by)
        r = min(radius, l1 / 2, l2 / 2)
        cross = (bx - ax) * (cy_ - by) - (by - ay) * (cx_ - bx)
        if r < 0.5 or abs(cross) < 1e-6:
            d.append(f"L{num(bx)} {num(by)}")
            continue
        s1 = (bx - (bx - ax) / l1 * r, by - (by - ay) / l1 * r)
        s2 = (bx + (cx_ - bx) / l2 * r, by + (cy_ - by) / l2 * r)
        d.append(f"L{num(s1[0])} {num(s1[1])}Q{num(bx)} {num(by)} {num(s2[0])} {num(s2[1])}")
    d.append(f"L{num(p[-1][0])} {num(p[-1][1])}")
    return "".join(d)
