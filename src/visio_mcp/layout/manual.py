"""layout 'none': keep the given positions, put the other nodes in free spots."""

from __future__ import annotations

from visio_mcp.layout.compound import Compound
from visio_mcp.layout.finish import free_route, normalized
from visio_mcp.layout.model import Frame, LayoutResult, Rect
from visio_mcp.layout.obstacle_router import ObstacleRouter
from visio_mcp.layout.polylines import self_loop
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GroupStyle, NodeSize

CLEAR = 0.4  # free space kept around every node
STEP = 0.25


def manual_positions(spec: DiagramSpec, sizes: dict[str, NodeSize]) -> dict[str, Rect]:
    """Given x/y are centers in inches. Unplaced nodes fill free spots, reading order from the top-left."""
    placed: dict[str, Rect] = {}
    for n in spec.nodes:
        if n.x is not None and n.y is not None:
            placed[n.id] = Rect(n.x, n.y, sizes[n.id].w, sizes[n.id].h)
    free = [n for n in spec.nodes if n.id not in placed]
    if not free:
        return placed
    rects = list(placed.values())
    widest = max(sizes[n.id].w for n in free)
    span = max([r.right for r in rects] + [widest * 4 + CLEAR * 4]) + widest
    top = max([r.top for r in rects], default=0.0)
    for n in free:
        s = sizes[n.id]
        y = top - s.h / 2 if rects else s.h / 2
        while n.id not in placed:
            x = s.w / 2
            while x + s.w / 2 <= span:
                cand = Rect(x, y, s.w, s.h)
                if not any(_hits(cand, r) for r in rects):
                    placed[n.id] = cand
                    rects.append(cand)
                    break
                x += STEP
            y -= STEP
    return placed


def _hits(a: Rect, b: Rect) -> bool:
    return (a.left < b.right + CLEAR and b.left < a.right + CLEAR
            and a.bottom < b.top + CLEAR and b.bottom < a.top + CLEAR)


def manual_layout(spec: DiagramSpec, sizes: dict[str, NodeSize], styles: dict[str, GroupStyle]) -> LayoutResult:
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
    router = ObstacleRouter(list(nodes.values()))
    routes = {i: self_loop(nodes[e.source]) if e.source == e.target
              else free_route(router, nodes[e.source], nodes[e.target], False)
              for i, e in enumerate(spec.edges)}
    return normalized(nodes, groups, routes, "none", None, keep=True)
