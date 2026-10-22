"""Edge polylines: layered paths, straight spokes, simple orthogonal routes and self loops."""

from __future__ import annotations

import math

from visio_mcp.layout.compound import Box, Frag
from visio_mcp.layout.model import LOOP, Point, Rect


def layered_route(f: Frag, src: Box, tgt: Box, forward: bool) -> list[Point]:
    """Flow-coordinate polyline: leave src downstream face, jog in each rank gap, enter tgt.

    Back edges (forward=False) leave the upstream face. A side flag attaches that end at a
    side corner instead (diamond branches, back edges looping round the side).
    """
    su, sv, scw, sah = src
    tu, tv, tcw, tah = tgt
    d = 1 if forward else -1
    pts: list[Point] = [(f.lanes[0], sv + d * sah / 2)]
    for i, jog in enumerate(f.jogs):
        pts += [(f.lanes[i], jog), (f.lanes[i + 1], jog)]
    pts.append((f.lanes[-1], tv - d * tah / 2))
    if f.side_start:
        pts[0:1] = [(su + f.side_start * scw / 2, sv), (f.lanes[0], sv)]
    if f.side_end:
        pts[-1:] = [(f.lanes[-1], tv), (tu + f.side_end * tcw / 2, tv)]
    return simplify(pts)


def straight_route(a: Rect, b: Rect) -> list[Point]:
    """Two points on the borders, along the line between the centers."""
    return [_clip(a, b.x, b.y), _clip(b, a.x, a.y)]


def ortho_route(a: Rect, b: Rect) -> list[Point]:
    """Z or straight route between two boxes in free placement (grid, manual)."""
    if b.left >= a.right or a.left >= b.right:
        horizontal = abs(b.x - a.x) >= abs(b.y - a.y) or not (b.bottom >= a.top or a.bottom >= b.top)
    else:
        horizontal = False
    if horizontal:
        s = 1 if b.x > a.x else -1
        x1, x2 = a.x + s * a.w / 2, b.x - s * b.w / 2
        lo, hi = max(a.bottom, b.bottom) + 0.1, min(a.top, b.top) - 0.1
        if lo <= hi:
            y = min(hi, max(lo, (a.y + b.y) / 2))
            return [(x1, y), (x2, y)]
        xm = (x1 + x2) / 2
        return simplify([(x1, a.y), (xm, a.y), (xm, b.y), (x2, b.y)])
    s = 1 if b.y > a.y else -1
    y1, y2 = a.y + s * a.h / 2, b.y - s * b.h / 2
    lo, hi = max(a.left, b.left) + 0.1, min(a.right, b.right) - 0.1
    if lo <= hi:
        x = min(hi, max(lo, (a.x + b.x) / 2))
        return [(x, y1), (x, y2)]
    ym = (y1 + y2) / 2
    return simplify([(a.x, y1), (a.x, ym), (b.x, ym), (b.x, y2)])


def self_loop(r: Rect) -> list[Point]:
    """Small rectangular loop on the right side."""
    dy = min(r.h / 4, 0.2)
    x = r.right + LOOP
    return [(r.right, r.y + dy), (x, r.y + dy), (x, r.y - dy), (r.right, r.y - dy)]


def simplify(pts: list[Point]) -> list[Point]:
    """Drop repeated points and middle points of straight runs."""
    out: list[Point] = []
    for p in pts:
        p = (round(p[0], 4), round(p[1], 4))
        if out and math.isclose(out[-1][0], p[0], abs_tol=1e-4) and math.isclose(out[-1][1], p[1], abs_tol=1e-4):
            continue
        if len(out) >= 2 and _collinear(out[-2], out[-1], p):
            out[-1] = p
            continue
        out.append(p)
    if len(out) == 1:
        out.append(out[0])
    return out


def _collinear(a: Point, b: Point, c: Point) -> bool:
    same_x = abs(a[0] - b[0]) < 1e-4 and abs(b[0] - c[0]) < 1e-4
    same_y = abs(a[1] - b[1]) < 1e-4 and abs(b[1] - c[1]) < 1e-4
    return same_x or same_y


def _clip(r: Rect, tx: float, ty: float) -> Point:
    """Where the ray from r's center toward (tx, ty) leaves r."""
    dx, dy = tx - r.x, ty - r.y
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return (r.x, r.y)
    sx = (r.w / 2) / abs(dx) if abs(dx) > 1e-9 else math.inf
    sy = (r.h / 2) / abs(dy) if abs(dy) > 1e-9 else math.inf
    s = min(sx, sy)
    return (r.x + dx * s, r.y + dy * s)
