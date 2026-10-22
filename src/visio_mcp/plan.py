"""DiagramSpec -> DiagramPlan: every decision about how the diagram looks, made once.

A plan holds final geometry (inches, center pins, bottom-left origin), resolved
shapes, styles and text for every element. Emitters only draw it:

- render.emit_visio   drives Visio desktop over COM (live, editable, real stencils)
- vsdx_writer.write   writes a native .vsdx with no Visio installed
- svg.render_svg      draws an SVG preview (any OS, browser, terminal tools)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from visio_mcp import catalog, icons, lint
from visio_mcp.backend import TextRun
from visio_mcp.catalog import Shape
from visio_mcp.layout import Point, Rect, compute_layout
from visio_mcp.spec import DiagramSpec, Group
from visio_mcp.style import (
    EdgeStyle,
    GroupStyle,
    NodeSize,
    ShapeStyle,
    TextStyle,
    Theme,
    get_theme,
    node_size,
    replace,
    sentence_case,
    title_case,
)

HasMaster = Callable[[str, str], bool]

MARGIN = 0.6  # inches around everything
TITLE_GAP = 0.35  # between the title block and the diagram
LEGEND_GAP = 0.5  # between the diagram and the legend


@dataclass
class PlannedNode:
    id: str
    kind: str  # resolved kind name ('box' when unknown)
    category: str
    geometry: str  # how non-Visio renderers draw it (style.GEOMETRY_MIN key)
    label: str  # final, cased
    runs: list[TextRun]  # label + [technology] + description, styled
    rect: Rect  # footprint reserved by layout (icon + label for icons)
    shape: Rect  # where the actual shape sits
    style: ShapeStyle
    icon: bool  # Visio master is an icon: keep its colors, label below
    master: Shape | None  # Visio stencil master (None when planned without Visio)
    glyph: str = ""
    provider: str | None = None
    emphasis: bool = False
    image: Path | None = None  # official cloud icon or a custom icon (svg/png) drawn instead of the glyph tile


@dataclass
class PlannedGroup:
    id: str
    label: str
    kind: str
    rect: Rect
    style: GroupStyle
    depth: int  # 0 = top level
    parent: str | None
    members: list[str]  # direct member node ids and child group ids


@dataclass
class PlannedEdge:
    name: str  # 'source->target' (+ '#n' for repeats): the Visio shape name
    source: str
    target: str
    label: str
    pattern: Literal["solid", "dashed", "dotted"]
    arrow: Literal["end", "both", "none"]
    color: str
    style: EdgeStyle
    points: list[Point]  # orthogonal polyline, first/last on the shape borders


@dataclass
class LegendEntry:
    label: str
    sample: Literal["node", "edge", "group"]
    style: ShapeStyle | None = None  # node / group swatch
    geometry: str = "rect"
    pattern: Literal["solid", "dashed", "dotted"] = "solid"
    color: str | None = None  # edge sample


@dataclass
class TextBlock:
    rect: Rect
    runs: list[TextRun]
    align: Literal["left", "center", "right"] = "left"


@dataclass
class DiagramPlan:
    spec: DiagramSpec  # normalized spec (type, layout, theme resolved; labels cased)
    theme: Theme
    width: float  # page size, inches
    height: float
    nodes: list[PlannedNode]
    groups: list[PlannedGroup]  # parents before children
    edges: list[PlannedEdge]
    title: TextBlock | None = None
    legend: Rect | None = None
    legend_title: TextBlock | None = None
    legend_entries: list[tuple[Rect, Rect, LegendEntry]] = field(default_factory=list)  # (sample, text) rects
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # what normalize filled in (informational)

    def node(self, nid: str) -> PlannedNode:
        return next(n for n in self.nodes if n.id == nid)


def build_plan(spec: DiagramSpec, has_master: HasMaster | None = None) -> DiagramPlan:
    """Normalize, size, lay out and style the whole diagram.

    has_master: the Visio backend's lookup, so kinds resolve to real stencil masters and
    icon masters get icon-sized footprints. None plans for the non-Visio renderers.
    """
    spec, notes = lint.normalize(spec)
    theme = get_theme(spec.theme)
    warnings: list[str] = []

    # resolve kinds and size nodes
    resolved: dict[str, tuple[catalog.Kind | None, Shape | None, bool]] = {}
    images: dict[str, Path | None] = {}
    geometries: dict[str, str] = {}
    sizes: dict[str, NodeSize] = {}
    no_icon: dict[str, int] = {}  # provider -> cloud nodes drawn without an official icon
    for n in spec.nodes:
        kind = catalog.lookup(n.kind)
        master: Shape | None = None
        image = icons.resolve_image(n.icon, n.kind)
        if n.icon and image is None:
            warnings.append(f"icon for {n.id!r} not found or not .svg/.png: {n.icon}")
        if has_master is not None:
            r = catalog.resolve(n.kind, has_master)
            kind, master, icon = r.kind or kind, r.shape, r.icon
            # a real icon master from the kind's own stencil candidates beats the downloaded icon,
            # unless the spec names a custom icon; generic stand-ins (base kind, rectangle) lose
            own_icon = icon and kind is not None and master in kind.candidates
            if image is not None and (n.icon or not own_icon):
                master, icon = None, True
            else:
                image = None
                if r.warning:
                    warnings.append(r.warning)
            if image is None and not own_icon and kind is not None and kind.provider:
                no_icon[kind.provider] = no_icon.get(kind.provider, 0) + 1
        else:
            icon = image is not None or bool(kind and kind.geometry in ("icon", "person"))
            if image is None and kind is not None and kind.provider:
                no_icon[kind.provider] = no_icon.get(kind.provider, 0) + 1
        category = kind.category if kind else "generic"
        geometry = "icon" if image is not None else _geometry(kind, icon, has_master is not None)
        resolved[n.id] = (kind, master, icon)
        images[n.id] = image
        geometries[n.id] = geometry
        sizes[n.id] = node_size(geometry, n.label, n.technology, n.description, theme, category)
    if no_icon:
        count = sum(no_icon.values())
        names = ", ".join(icons.PROVIDER_NAMES[p] for p in icons.PROVIDERS if p in no_icon)
        warnings.append(f"{count} {names} service{'s' if count != 1 else ''} drawn without official icons; "
                        "install official icons: visio-ai icons install (MCP: install_icons)")

    group_styles = {g.id: theme.group_style(g.kind, _depth(g, spec.groups)) for g in spec.groups}
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
    legend_entries = _legend_entries(spec, theme, resolved) if spec.legend else []
    legend_w, legend_h = _legend_size(legend_entries, theme)
    legend_below = layout.width >= layout.height * 1.2 or legend_h > layout.height
    if legend_entries and legend_below:
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
            runs=_node_runs(n.label, n.technology, n.description, _label_text(style.text, theme, icon, kind),
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
        name = unique_edge_name(f"{e.source}->{e.target}", taken)
        taken.add(name)
        pts = [(x + ox, y + oy) for x, y in layout.routes.get(i, [])]
        edges.append(PlannedEdge(name, e.source, e.target, e.label, e.style, e.arrow,
                                 e.color or theme.edge.color, theme.edge, pts))

    content_w = layout.width + 2 * MARGIN
    content_top = oy + layout.height
    width = max(content_w, (legend_w + 2 * MARGIN) if legend_below else content_w + legend_w + LEGEND_GAP)
    if spec.title:
        tw = max(_text_w(spec.title, theme.title), _text_w(spec.subtitle, theme.subtitle)) + 0.2
        width = max(width, tw + 2 * MARGIN)
        title = TextBlock(Rect(MARGIN + tw / 2, content_top + TITLE_GAP + title_h / 2, tw, title_h), runs)
    height = content_top + top_band + MARGIN

    legend = legend_title = None
    placed: list[tuple[Rect, Rect, LegendEntry]] = []
    if legend_entries:
        if legend_below:
            lx, ly = MARGIN, MARGIN
        else:
            lx, ly = MARGIN + layout.width + LEGEND_GAP, oy
        legend = Rect(lx + legend_w / 2, ly + legend_h / 2, legend_w, legend_h)
        legend_title, placed = _place_legend(legend, legend_entries, theme)

    suggestions = lint.lint(spec)
    return DiagramPlan(
        spec=spec, theme=theme, width=round(width, 3), height=round(height, 3),
        nodes=nodes, groups=groups, edges=edges, title=title, legend=legend,
        legend_title=legend_title, legend_entries=placed,
        warnings=list(dict.fromkeys(warnings)), suggestions=suggestions, notes=notes,
    )


def unique_edge_name(base: str, taken: set[str]) -> str:
    """'a->b', then 'a->b#2', 'a->b#3' ... for repeated edges."""
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}#{n}"
    return name


# --- helpers ------------------------------------------------------------------------------


def _geometry(kind: catalog.Kind | None, icon: bool, visio: bool) -> str:
    """How the node is drawn. In Visio a non-icon master stands in for icon kinds, so use the
    geometry of the base kind it fell back to; without Visio icon kinds draw as glyph tiles."""
    if kind is None:
        return "rounded"
    if icon:
        return "person" if kind.geometry == "person" else "icon"
    if visio and kind.geometry in ("icon", "person"):
        base = kind
        while base.geometry in ("icon", "person") and base.base and (nxt := catalog.lookup(base.base)):
            base = nxt
        return base.geometry if base.geometry not in ("icon", "person") else "rounded"
    return kind.geometry


def _depth(g: Group, groups: list[Group]) -> int:
    parents = {x.id: x.parent for x in groups}
    d, cur = 0, g.parent
    while cur:
        d += 1
        cur = parents.get(cur)
    return d


def _parents_first(groups: list[Group]) -> list[Group]:
    return sorted(groups, key=lambda g: _depth(g, groups))


def _label_text(text: TextStyle, theme: Theme, icon: bool, kind: catalog.Kind | None) -> TextStyle:
    """Labels drawn under icons and people sit on the page, so they take the page's text color."""
    if icon or (kind is not None and kind.geometry == "person"):
        return replace(text, color=theme.title.color)
    return text


def _node_runs(label: str, technology: str, description: str, text: TextStyle, theme: Theme,
               on_page: bool = False) -> list[TextRun]:
    color = theme.subtitle.color if on_page else _secondary_color(text, theme)
    sec = replace(theme.secondary, color=color)
    runs = [TextRun(label, text)]
    if technology:
        runs.append(TextRun(f"\n[{technology}]", replace(sec, italic=False)))
    if description:
        runs.append(TextRun(f"\n{description}", sec))
    return runs


def _secondary_color(text: TextStyle, theme: Theme) -> str:
    """Secondary text matches light-on-dark nodes (C4) instead of the theme default."""
    r, g, b = (int(text.color[i:i + 2], 16) for i in (1, 3, 5))
    light_text = (r * 299 + g * 587 + b * 114) / 1000 > 160
    if light_text and not theme.dark:
        return "#E8F1FB"
    return theme.secondary.color


def _text_w(text: str, st: TextStyle) -> float:
    from visio_mcp.style import text_width

    return text_width(text, st.size, st.bold) if text else 0.0


_CATEGORY_NAMES = {
    "terminal": "Start / end", "flow": "Process step", "decision": "Decision", "data": "Data store",
    "compute": "Service / compute", "integration": "Messaging / integration", "client": "Client app",
    "person": "Person / actor", "external": "External system", "network": "Network", "security": "Security",
    "org": "Position", "entity": "Entity", "note": "Note", "generic": "Component",
}
_PATTERN_NAMES = {"solid": "Synchronous call", "dashed": "Asynchronous / event", "dotted": "Optional / weak"}


def _legend_entries(spec: DiagramSpec, theme: Theme, resolved: dict) -> list[LegendEntry]:
    """One entry per node category used, per line pattern used and per group kind used."""
    entries: list[LegendEntry] = []
    seen: set[str] = set()
    for n in spec.nodes:
        kind, _, icon = resolved[n.id]
        cat = kind.category if kind else "generic"
        if cat in seen or icon:
            continue  # icons explain themselves
        seen.add(cat)
        entries.append(LegendEntry(_CATEGORY_NAMES.get(cat, cat.title()), "node", theme.node_style(cat),
                                   kind.geometry if kind else "rounded"))
    patterns = list(dict.fromkeys(e.style for e in spec.edges))
    if len(patterns) > 1:
        for p in patterns:
            entries.append(LegendEntry(_PATTERN_NAMES[p], "edge", pattern=p, color=theme.edge.color))
    special = [g for g in spec.groups if g.kind in ("boundary", "external", "network", "subnet", "region", "zone")]
    for kind in dict.fromkeys(g.kind for g in special):
        entries.append(LegendEntry({"boundary": "Trust boundary", "external": "External", "network": "Virtual network",
                                    "subnet": "Subnet", "region": "Region", "zone": "Availability zone"}[kind],
                                   "group", theme.group_style(kind).shape))
    # a legend that only repeats one entry adds nothing
    return entries if len(entries) >= 2 else []


LEGEND_ROW = 0.32
LEGEND_SAMPLE_W = 0.5
LEGEND_PAD = 0.18


def _legend_size(entries: list[LegendEntry], theme: Theme) -> tuple[float, float]:
    if not entries:
        return 0.0, 0.0
    st = theme.legend.text
    text_w = max(_text_w(e.label, replace(st, size=9)) for e in entries)
    cols = 1 if len(entries) <= 5 else 2
    rows = -(-len(entries) // cols)
    col_w = LEGEND_SAMPLE_W + 0.15 + text_w + 0.2
    return round(cols * col_w + 2 * LEGEND_PAD, 3), round(rows * LEGEND_ROW + 0.35 + 2 * LEGEND_PAD, 3)


def _place_legend(frame: Rect, entries: list[LegendEntry], theme: Theme) -> tuple[TextBlock, list]:
    st = replace(theme.legend.text, size=9)
    head = TextBlock(Rect(frame.left + LEGEND_PAD + 0.6, frame.top - LEGEND_PAD - 0.12, 1.2, 0.24),
                     [TextRun("Legend", replace(st, bold=True))])
    cols = 1 if len(entries) <= 5 else 2
    rows = -(-len(entries) // cols)
    col_w = (frame.w - 2 * LEGEND_PAD) / cols
    out = []
    for i, e in enumerate(entries):
        c, r = divmod(i, rows)
        x0 = frame.left + LEGEND_PAD + c * col_w
        y = frame.top - LEGEND_PAD - 0.35 - r * LEGEND_ROW - LEGEND_ROW / 2
        sample = Rect(x0 + LEGEND_SAMPLE_W / 2, y, LEGEND_SAMPLE_W, 0.2)
        text_w = col_w - LEGEND_SAMPLE_W - 0.15
        text = Rect(x0 + LEGEND_SAMPLE_W + 0.15 + text_w / 2, y, text_w, 0.24)
        out.append((sample, text, e))
    return head, out


# Re-exported for emitters
__all__ = [
    "DiagramPlan", "PlannedNode", "PlannedGroup", "PlannedEdge", "LegendEntry", "TextBlock",
    "build_plan", "unique_edge_name", "title_case", "sentence_case",
]
