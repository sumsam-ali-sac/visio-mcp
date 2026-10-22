"""Page decorations: the locked background, the title block and the legend."""

from __future__ import annotations

from visio_mcp.layout import Rect
from visio_mcp.output.visio.backend import TextRun
from visio_mcp.output.vsdx import shapes
from visio_mcp.output.vsdx.cells import OBJ_IGNORE, cell
from visio_mcp.output.vsdx.page import Page, Shape
from visio_mcp.plan import DiagramPlan, LegendEntry, TextBlock
from visio_mcp.style import ShapeStyle, replace

LOCKS = ("LockMoveX", "LockMoveY", "LockWidth", "LockHeight", "LockRotate", "LockDelete", "LockSelect",
         "LockTextEdit")


def draw_background(page: Page, plan: DiagramPlan) -> None:
    r = Rect(plan.width / 2, plan.height / 2, plan.width, plan.height)
    s = shapes.box(page, "__background", r, ShapeStyle(fill=plan.theme.background, line=None), obj=OBJ_IGNORE)
    s.cells += [cell(c, 1) for c in LOCKS]
    page.add(s)


def draw_title(page: Page, title: TextBlock) -> None:
    page.add(shapes.text(page, "__title", title.rect, title.runs, title.align))


def draw_legend(page: Page, plan: DiagramPlan) -> None:
    theme, frame = plan.theme, plan.legend
    assert frame is not None
    page.add(shapes.box(page, "__legend", frame, theme.legend, "rect", obj=OBJ_IGNORE))
    if plan.legend_title:
        t = plan.legend_title
        page.add(shapes.text(page, "__legend_title", t.rect, t.runs, t.align))
    text_style = replace(theme.legend.text, size=9)
    for i, (sample, text, entry) in enumerate(plan.legend_entries):
        name = f"__legend_{i}"
        page.add(_legend_sample(page, f"{name}_sample", sample, entry, plan))
        page.add(shapes.text(page, f"{name}_text", text, [TextRun(entry.label, text_style)], "left"))


def _legend_sample(page: Page, name: str, r: Rect, entry: LegendEntry, plan: DiagramPlan) -> Shape:
    theme = plan.theme
    if entry.sample == "edge":
        return shapes.line(page, name, [(r.left, r.y), (r.right, r.y)], entry.color or theme.edge.color,
                           theme.edge.weight, entry.pattern, "end", arrow_size=1)
    style = entry.style or ShapeStyle()
    if entry.sample == "group":
        return shapes.box(page, name, r, replace(style, rounding=min(style.rounding, 0.04)), "rect", obj=OBJ_IGNORE)
    geom = entry.geometry if entry.geometry not in ("icon", "person") else "rounded"
    return shapes.box(page, name, r, style, geom, obj=OBJ_IGNORE, rounding=min(style.rounding, 0.05))
