"""SVG for group frames, the title block and the legend."""

from __future__ import annotations

from visio_mcp.layout import Rect
from visio_mcp.output.svg.canvas import Canvas
from visio_mcp.output.svg.markup import PT, PX, esc, num, shape_attrs, snap, stroke_attrs
from visio_mcp.output.svg.shapes import shape
from visio_mcp.output.svg.text import block_h, layout_text, single_line, text_svg
from visio_mcp.output.visio.backend import TextRun
from visio_mcp.plan import LegendEntry, PlannedGroup, TextBlock
from visio_mcp.style import ShapeStyle, replace


def group(c: Canvas, g: PlannedGroup, idx: int) -> str:
    x0, y0, x1, y1 = c.box(g.rect)
    st = g.style.shape
    rx = min(max(0.0, st.rounding * PX), (y1 - y0) / 2, (x1 - x0) / 2)
    out = [f'<g id="group-{idx}" class="group" data-id="{esc(g.id)}" data-kind="{esc(g.kind)}" data-depth="{g.depth}">',
           f'<rect x="{num(x0)}" y="{num(y0)}" width="{num(x1 - x0)}" height="{num(y1 - y0)}" rx="{num(rx)}"{shape_attrs(st)}/>']
    if g.label:
        hs = g.style.header
        line = single_line(g.label, hs, hs.size * PT)
        top = y0 + (g.style.header_height * PX - line.height) / 2 + 2
        out.append(text_svg([line], x0 + 12 + min(rx, 8), top, "start"))
    out.append("</g>")
    return "".join(out)


def text_block(c: Canvas, tb: TextBlock) -> str:
    """Title/subtitle text, recolored to read on the page background."""
    r = tb.rect
    x0, x1 = c.X(r.left), c.X(r.right)
    runs = [TextRun(t.text, c.readable(t.style, secondary=i > 0)) for i, t in enumerate(tb.runs)]
    lines = layout_text(runs, (x1 - x0) + 80)
    top = (c.Y(r.top) + c.Y(r.bottom)) / 2 - block_h(lines) / 2
    if tb.align == "left":
        return text_svg(lines, x0, top, "start")
    if tb.align == "right":
        return text_svg(lines, x1, top, "end")
    return text_svg(lines, (x0 + x1) / 2, top, "middle")


def legend(c: Canvas) -> str:
    p = c.plan
    assert p.legend is not None
    x0, y0, x1, y1 = c.box(p.legend)
    ls = c.theme.legend
    rx = min(ls.rounding * PX, 10)
    out = ['<g id="legend" class="legend" data-id="legend">',
           f'<rect x="{num(x0)}" y="{num(y0)}" width="{num(x1 - x0)}" height="{num(y1 - y0)}" rx="{num(rx)}"'
           f'{shape_attrs(replace(ls, shadow=False))}/>']
    if p.legend_title:
        r = p.legend_title.rect
        lines = layout_text(p.legend_title.runs, 200)
        top = (c.Y(r.top) + c.Y(r.bottom)) / 2 - block_h(lines) / 2
        out.append(text_svg(lines, x0 + (0.18 * PX), top, "start"))
    text_style = replace(ls.text, size=9)
    for i, (srect, trect, entry) in enumerate(p.legend_entries):
        out.append(f'<g class="legend-entry" data-id="legend-{i}" data-sample="{esc(entry.sample)}">')
        out.append(_legend_sample(c, srect, entry))
        cy = (c.Y(trect.top) + c.Y(trect.bottom)) / 2
        ln = single_line(entry.label, text_style, text_style.size * PT)
        out.append(text_svg([ln], c.X(trect.left), cy - ln.height / 2, "start"))
        out.append("</g>")
    out.append("</g>")
    return "".join(out)


def _legend_sample(c: Canvas, r: Rect, e: LegendEntry) -> str:
    x0, y0, x1, y1 = c.box(r)
    if e.sample == "edge":
        cy = snap((y0 + y1) / 2)
        color = e.color or c.theme.edge.color
        wt = c.theme.edge.weight
        mid = c.marker(color, wt)
        return (f'<path d="M{num(x0 + 1)} {num(cy)}H{num(x1 - 1)}" fill="none"'
                f'{stroke_attrs(color, wt, e.pattern)} marker-end="url(#{mid})"/>')
    st = e.style or ShapeStyle()
    st = replace(st, line_weight=min(st.line_weight, 1.0))
    if e.sample == "group":
        return f'<rect x="{num(x0)}" y="{num(y0)}" width="{num(x1 - x0)}" height="{num(y1 - y0)}" rx="3"{shape_attrs(st)}/>'
    markup, _ = shape(e.geometry, x0, y0, x1, y1, st)
    return markup
