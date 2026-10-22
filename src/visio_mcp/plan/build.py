"""build_plan: normalize a spec, resolve and size its nodes, lay it out and style every element."""

from __future__ import annotations

from dataclasses import replace

from visio_mcp import lint
from visio_mcp.layout import Rect, compute_layout
from visio_mcp.output.visio.backend import TextRun
from visio_mcp.plan.kinds import HasMaster, resolve_nodes
from visio_mcp.plan.legend import legend_entries, legend_size, place_legend
from visio_mcp.plan.model import (
    DiagramPlan,
    LegendEntry,
    PlannedEdge,
    PlannedGroup,
    PlannedNode,
    TextBlock,
)
from visio_mcp.plan.runs import label_text, line_width, node_runs
from visio_mcp.spec import DiagramSpec, Group, edge_name
from visio_mcp.style import get_theme

MARGIN = 0.6  # inches around everything
TITLE_GAP = 0.35  # between the title block and the diagram
LEGEND_GAP = 0.5  # between the diagram and the legend


def build_plan(spec: DiagramSpec, has_master: HasMaster | None = None) -> DiagramPlan:
    """Normalize, size, lay out and style the whole diagram.

    has_master: the Visio backend's lookup, so kinds resolve to real stencil masters and
    icon masters get icon-sized footprints. None plans for the non-Visio renderers.
    """
    spec, notes = lint.normalize(spec)
    theme = get_theme(spec.theme)
    nodes_resolved = resolve_nodes(spec, theme, has_master)
    resolved, images, geometries, sizes = (nodes_resolved.kinds, nodes_resolved.images,
                                           nodes_resolved.geometries, nodes_resolved.sizes)
    warnings = nodes_resolved.warnings

    group_styles = {g.id: theme.group_style(g.kind) for g in spec.groups}
    layout = compute_layout(spec, sizes, group_styles, spec.layout)

    # page frame: title on top, diagram, legend below or to the right
    title = None
    top_band = 0.0
    if spec.title:
        runs = [TextRun(spec.title, theme.title)]
        h = theme.title.size * 1.35 / 72
        if spec.subtitle:
            runs.append(TextRun("\n" + spec.subtitle, theme.subtitle))
            h += theme.subtitle.size * 1.5 / 72
        top_band = h + TITLE_GAP
        title_h = h
    else:
        title_h = 0.0

    nodes, groups, edges = [], [], []
    ox, oy = MARGIN, MARGIN  # diagram offset; legend may push it up
    entries = legend_entries(spec, theme, resolved) if spec.legend else []
    legend_w, legend_h = legend_size(entries, theme)
    legend_below = layout.width >= layout.height * 1.2 or legend_h > layout.height
    if entries and legend_below:
        oy += legend_h + LEGEND_GAP

    def shift(r: Rect) -> Rect:
        return Rect(r.x + ox, r.y + oy, r.w, r.h)

    for n in spec.nodes:
        kind, master, icon = resolved[n.id]
        size = sizes[n.id]
        rect = shift(layout.nodes[n.id])
        shape = Rect(rect.x, rect.y + size.dy, size.shape_w, size.shape_h)
        category = kind.category if kind else "generic"
        style = theme.node_style(category)
        if n.fill:
            style = replace(style, fill=n.fill)
        if n.emphasis:
            style = replace(style, line=theme.accent, line_weight=max(2.0, style.line_weight * 2))
        nodes.append(PlannedNode(
            id=n.id,
            kind=kind.name if kind else "box",
            category=category,
            geometry=geometries[n.id],
            label=n.label,
            runs=node_runs(n.label, n.technology, n.description, label_text(style.text, theme, icon, kind),
                            theme, on_page=icon or bool(kind and kind.geometry == "person")),
            rect=rect,
            shape=shape,
            style=style,
            icon=icon,
            master=master,
            glyph=kind.glyph if kind else "",
            provider=kind.provider if kind else None,
            emphasis=n.emphasis,
            image=images[n.id],
        ))

    for g in _parents_first(spec.groups):
        if g.id not in layout.groups:
            warnings.append(f"group {g.id!r} has no members; skipped")
            continue
        st = group_styles[g.id]
        if g.fill:
            st = replace(st, shape=replace(st.shape, fill=g.fill))
        members = [n.id for n in spec.nodes if n.group == g.id] + [
            c.id for c in spec.groups if c.parent == g.id and c.id in layout.groups
        ]
        groups.append(PlannedGroup(g.id, g.label, g.kind, shift(layout.groups[g.id]), st,
                                   _depth(g, spec.groups), g.parent, members))

    taken: set[str] = set()
    for i, e in enumerate(spec.edges):
        name = edge_name(f"{e.source}->{e.target}", taken)
        taken.add(name)
        pts = [(x + ox, y + oy) for x, y in layout.routes.get(i, [])]
        edges.append(PlannedEdge(name, e.source, e.target, e.label, e.style, e.arrow,
                                 e.color or theme.edge.color, theme.edge, pts))

    content_w = layout.width + 2 * MARGIN
    content_top = oy + layout.height
    width = max(content_w, (legend_w + 2 * MARGIN) if legend_below else content_w + legend_w + LEGEND_GAP)
    if spec.title:
        tw = max(line_width(spec.title, theme.title), line_width(spec.subtitle, theme.subtitle)) + 0.2
        width = max(width, tw + 2 * MARGIN)
        title = TextBlock(Rect(MARGIN + tw / 2, content_top + TITLE_GAP + title_h / 2, tw, title_h), runs)
    height = content_top + top_band + MARGIN

    legend = legend_title = None
    placed: list[tuple[Rect, Rect, LegendEntry]] = []
    if entries:
        if legend_below:
            lx, ly = MARGIN, MARGIN
        else:
            lx, ly = MARGIN + layout.width + LEGEND_GAP, oy
        legend = Rect(lx + legend_w / 2, ly + legend_h / 2, legend_w, legend_h)
        legend_title, placed = place_legend(legend, entries, theme)

    suggestions = lint.lint(spec)
    return DiagramPlan(
        spec=spec, theme=theme, width=round(width, 3), height=round(height, 3),
        nodes=nodes, groups=groups, edges=edges, title=title, legend=legend,
        legend_title=legend_title, legend_entries=placed,
        warnings=list(dict.fromkeys(warnings)), suggestions=suggestions, notes=notes,
    )


def _depth(g: Group, groups: list[Group]) -> int:
    parents = {x.id: x.parent for x in groups}
    d, cur = 0, g.parent
    while cur:
        d += 1
        cur = parents.get(cur)
    return d


def _parents_first(groups: list[Group]) -> list[Group]:
    return sorted(groups, key=lambda g: _depth(g, groups))
