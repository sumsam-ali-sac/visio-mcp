"""Final layout steps: route every edge, then shift the result to the origin."""

from __future__ import annotations

from typing import Literal

from visio_mcp.layout.compound import Placed
from visio_mcp.layout.model import Frame, LayoutResult, Point, Rect
from visio_mcp.layout.obstacle_router import ObstacleRouter
from visio_mcp.layout.polylines import (
    layered_route,
    ortho_route,
    self_loop,
    simplify,
    straight_route,
)
from visio_mcp.spec import DiagramSpec

Direction = Literal["tb", "lr", "none"]


def finish(spec: DiagramSpec, placed: Placed, frame: Frame, direction: Direction,
            header: Literal["top", "left"] | None, spokes: bool = False) -> LayoutResult:
    nodes = {k: frame.rect(*b) for k, b in placed.nodes.items()}
    groups = {k: frame.rect(*b) for k, b in placed.groups.items()}
    routes: dict[int, list[Point]] = {}
    router: ObstacleRouter | None = None
    for i, e in enumerate(spec.edges):
        a, b = nodes[e.source], nodes[e.target]
        if e.source == e.target:
            routes[i] = self_loop(a)
        elif i in placed.paths:
            pts = layered_route(placed.paths[i], placed.nodes[e.source], placed.nodes[e.target], placed.forward[i])
            routes[i] = [frame.point(u, v) for u, v in pts]
        else:
            router = router or ObstacleRouter(list(nodes.values()))
            routes[i] = free_route(router, a, b, spokes)
    return normalized(nodes, groups, routes, direction, header)


def free_route(router: ObstacleRouter, a: Rect, b: Rect, spokes: bool) -> list[Point]:
    """Straight (spokes) or simple orthogonal line; detour around boxes when that one is blocked."""
    simple = straight_route(a, b) if spokes else ortho_route(a, b)
    if not router.blocked(simple, (a, b)):
        return simple
    return simplify(router.route(a, b) or simple)



def normalized(nodes: dict[str, Rect], groups: dict[str, Rect], routes: dict[int, list[Point]],
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
