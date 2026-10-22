"""Group-aware auto-layout: DiagramSpec + node sizes -> positions, group frames, edge routes.

Engines by preset:

- flowchart-* / tree-*  compound layered layout (groups as blocks); tree-* uses a tidy tree
                        when the graph is a forest without groups
- swimlane-*            lanes as full-length bands sharing flow ranks
- radial / circular     rings around a hub / one circle (groups as compact blocks)
- grid / compact        tidy grid, groups as blocks
- none                  given x/y, the rest in free spots
"""

from __future__ import annotations

from typing import Literal

from visio_mcp.layout.compound import Compound, Placed
from visio_mcp.layout.manual import manual_positions
from visio_mcp.layout.model import Frame, LayoutResult, Point, Rect
from visio_mcp.layout.router import Router
from visio_mcp.layout.routing import layered_route, ortho_route, self_loop, simplify, straight_route
from visio_mcp.layout.swimlane import swimlane_layout
from visio_mcp.layout.tree import is_forest, tree_layout
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GroupStyle, NodeSize

__all__ = ["Rect", "Point", "LayoutResult", "compute_layout"]

Direction = Literal["tb", "lr", "none"]


def compute_layout(
    spec: DiagramSpec, sizes: dict[str, NodeSize], group_styles: dict[str, GroupStyle], layout: str
) -> LayoutResult:
    """Place every node and group. layout is a concrete spec Layout (never 'auto')."""
    if layout == "none" and any(n.x is not None and n.y is not None for n in spec.nodes):
        return _manual(spec, sizes, group_styles)
    lr = layout.endswith("-lr")
    frame = Frame(lr)
    direction: Direction = "lr" if lr else "tb"
    header: Literal["top", "left"] | None = None
    nested = any(g.parent for g in spec.groups)
    if layout.startswith("swimlane") and not nested:
        placed = swimlane_layout(spec, sizes, group_styles, frame)
        header = "left" if lr else "top"
    elif layout.startswith("tree") and not spec.groups and is_forest(spec):
        placed = tree_layout(spec, sizes, frame)
    elif layout.startswith(("flowchart", "tree", "swimlane")):  # nested lanes: groups as blocks
        placed = Compound(spec, sizes, group_styles, frame, "layered").run()
    else:
        mode = layout if layout in ("radial", "circular") else "grid"
        placed = Compound(spec, sizes, group_styles, frame, mode).run()  # type: ignore[arg-type]
        direction = "none"
    return _finish(spec, placed, frame, direction, header, layout in ("radial", "circular"))


def _finish(spec: DiagramSpec, placed: Placed, frame: Frame, direction: Direction,
            header: Literal["top", "left"] | None, spokes: bool = False) -> LayoutResult:
    nodes = {k: frame.rect(*b) for k, b in placed.nodes.items()}
    groups = {k: frame.rect(*b) for k, b in placed.groups.items()}
    routes: dict[int, list[Point]] = {}
    router: Router | None = None
    for i, e in enumerate(spec.edges):
        a, b = nodes[e.source], nodes[e.target]
        if e.source == e.target:
            routes[i] = self_loop(a)
        elif i in placed.paths:
            pts = layered_route(placed.paths[i], placed.nodes[e.source], placed.nodes[e.target], placed.forward[i])
            routes[i] = [frame.point(u, v) for u, v in pts]
        else:
            router = router or Router(list(nodes.values()))
            routes[i] = _free_route(router, a, b, spokes)
    return _normalized(nodes, groups, routes, direction, header)


def _free_route(router: Router, a: Rect, b: Rect, spokes: bool) -> list[Point]:
    """Straight (spokes) or simple orthogonal line; detour around boxes when that one is blocked."""
    simple = straight_route(a, b) if spokes else ortho_route(a, b)
    if not router.blocked(simple, (a, b)):
        return simple
    return simplify(router.route(a, b) or simple)


def _manual(spec: DiagramSpec, sizes: dict[str, NodeSize], styles: dict[str, GroupStyle]) -> LayoutResult:
    nodes = manual_positions(spec, sizes)
    groups: dict[str, Rect] = {}
    frame = Frame(False)
    order = Compound(spec, sizes, styles, frame, "grid").h
    for g in order.depth_first():
        boxes = [nodes[i] if i in nodes else groups[i] for i in order.children[g]]
        ub, ua, vb, va = frame.insets(styles[g])
        left = min(r.left for r in boxes) - ub
        right = max(r.right for r in boxes) + ua
        bottom = min(r.bottom for r in boxes) - va
        top = max(r.top for r in boxes) + vb
        groups[g] = Rect((left + right) / 2, (bottom + top) / 2, right - left, top - bottom)
    router = Router(list(nodes.values()))
    routes = {i: self_loop(nodes[e.source]) if e.source == e.target
              else _free_route(router, nodes[e.source], nodes[e.target], False)
              for i, e in enumerate(spec.edges)}
    return _normalized(nodes, groups, routes, "none", None, keep=True)


def _normalized(nodes: dict[str, Rect], groups: dict[str, Rect], routes: dict[int, list[Point]],
                direction: Direction, header: Literal["top", "left"] | None, keep: bool = False) -> LayoutResult:
    """Shift everything so the minimum coordinate is 0 (keep: only when something is negative)."""
    rects = list(nodes.values()) + list(groups.values())
    pts = [p for r in routes.values() for p in r]
    min_x = min([r.left for r in rects] + [p[0] for p in pts])
    min_y = min([r.bottom for r in rects] + [p[1] for p in pts])
    if keep:
        min_x, min_y = min(min_x, 0.0), min(min_y, 0.0)

    def mv(r: Rect) -> Rect:
        return Rect(round(r.x - min_x, 4), round(r.y - min_y, 4), r.w, r.h)

    nodes = {k: mv(r) for k, r in nodes.items()}
    groups = {k: mv(r) for k, r in groups.items()}
    routes = {i: [(round(x - min_x, 4), round(y - min_y, 4)) for x, y in r] for i, r in routes.items()}
    rects = list(nodes.values()) + list(groups.values())
    pts = [p for r in routes.values() for p in r]
    width = max([r.right for r in rects] + [p[0] for p in pts])
    height = max([r.top for r in rects] + [p[1] for p in pts])
    return LayoutResult(nodes, groups, routes, round(width, 4), round(height, 4), direction, header)
