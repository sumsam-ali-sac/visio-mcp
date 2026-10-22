"""Draw a DiagramPlan in Visio through the backend, in the order a person would watch it built."""

from __future__ import annotations

from typing import Callable

from visio_mcp import catalog
from visio_mcp.output.visio.backend import TextRun, VisioBackend
from visio_mcp.output.visio.inspect import find_overlaps
from visio_mcp.plan import DiagramPlan, PlannedNode, build_plan
from visio_mcp.spec import DiagramSpec, RenderResult
from visio_mcp.style import EdgeStyle, ShapeStyle, replace

Progress = Callable[[str], None]


def render_spec(backend: VisioBackend, spec: DiagramSpec, progress: Progress | None = None) -> RenderResult:
    """Plan the whole diagram, then build it in a fresh document. Does not save or export."""
    return emit_visio(backend, build_plan(spec, backend.has_master), progress)


def emit_visio(backend: VisioBackend, plan: DiagramPlan, progress: Progress | None = None) -> RenderResult:
    say = progress or (lambda _msg: None)
    spec, theme = plan.spec, plan.theme
    backend.new_document(spec.title)
    backend.set_page(plan.width, plan.height, theme.background)

    if plan.title:
        r = plan.title.rect
        backend.add_text("__title", r.x, r.y, r.w, r.h, plan.title.runs, plan.title.align)

    # nodes, one group at a time, so the drawing grows region by region
    say(f"Placing {len(plan.nodes)} shapes")
    for n in _by_group(plan):
        _draw_planned(backend, n)

    # containers wrap their members: innermost first, so parents can hold children
    for g in sorted(plan.groups, key=lambda g: -g.depth):
        say(f"Grouping {g.label}")
        r = g.rect
        backend.add_container(g.id, g.label, g.members, g.style, (r.x, r.y, r.w, r.h))

    say(f"Connecting {len(plan.edges)} flows")
    for e in plan.edges:
        backend.connect(e.name, e.source, e.target, e.label, e.pattern, e.arrow)
        backend.style_connector(e.name, e.style, e.color)

    if plan.legend:
        _draw_legend(backend, plan)

    backend.present()
    return RenderResult(
        shapes=len(plan.nodes) + len(plan.groups),
        connectors=len(plan.edges),
        warnings=plan.warnings,
        suggestions=plan.suggestions,
        overlaps=find_overlaps(backend.shapes()),
    )


def _draw_planned(backend: VisioBackend, n: PlannedNode) -> None:
    master = n.master or catalog.FALLBACK
    s = n.shape
    if n.image is not None and master == catalog.FALLBACK:
        # official cloud icon / custom icon file: imported as a picture, label below it
        try:
            backend.drop_image(n.id, str(n.image), s.x, s.y, s.w, s.h)
        except (RuntimeError, OSError, ValueError):  # drop_image leaves nothing behind when it fails
            backend.drop_shape(n.id, master.stencil, master.master, s.x, s.y, s.w, s.h)
            backend.style_shape(n.id, n.style, keep_fill=False, label_below=True)
        else:
            backend.style_shape(n.id, n.style, keep_fill=True, label_below=True)
        backend.set_rich_text(n.id, n.runs)
        return
    backend.drop_shape(n.id, master.stencil, master.master, s.x, s.y, s.w, s.h)
    backend.style_shape(n.id, n.style, keep_fill=n.icon, label_below=n.icon)
    backend.set_rich_text(n.id, n.runs)


def _by_group(plan: DiagramPlan) -> list[PlannedNode]:
    """Nodes ordered so each group's members are drawn together, ungrouped ones first."""
    order = {g.id: i for i, g in enumerate(plan.groups)}
    spec_group = {n.id: n.group for n in plan.spec.nodes}
    return sorted(plan.nodes, key=lambda n: -1 if spec_group[n.id] is None else order.get(spec_group[n.id], 0))


def _draw_legend(backend: VisioBackend, plan: DiagramPlan) -> None:
    theme, frame = plan.theme, plan.legend
    assert frame is not None
    backend.add_box("__legend", frame.x, frame.y, frame.w, frame.h, theme.legend)
    if plan.legend_title:
        r = plan.legend_title.rect
        backend.add_text("__legend_title", r.x, r.y, r.w, r.h, plan.legend_title.runs)
    text_style = replace(theme.legend.text, size=9)
    for i, (sample, text, entry) in enumerate(plan.legend_entries):
        name = f"__legend_{i}"
        if entry.sample == "edge":
            edge = EdgeStyle(color=entry.color or theme.edge.color, weight=theme.edge.weight)
            backend.add_line(f"{name}_sample", sample.left, sample.y, sample.right, sample.y, edge, entry.pattern)
        else:
            style = entry.style or ShapeStyle()
            if entry.sample == "node":
                style = replace(style, rounding=min(style.rounding, 0.05))
            backend.add_box(f"{name}_sample", sample.x, sample.y, sample.w, sample.h, style)
        backend.add_text(f"{name}_text", text.x, text.y, text.w, text.h, [TextRun(entry.label, text_style)])
