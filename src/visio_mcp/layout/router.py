"""Orthogonal routing around boxes for free placements (grid, radial, circular, manual).

A* over a sparse grid: candidate lines run just outside every box and through every box
center; a path leaves a side midpoint of the source, travels along free grid lines and
enters a side midpoint of the target. Cost = length + a penalty per bend.
"""

from __future__ import annotations

import heapq
from bisect import bisect_left

from visio_mcp.layout.model import Point, Rect

CLEAR = 0.2  # candidate lines this far outside boxes
PAD = 0.08  # boxes are inflated by this for blocking
BEND = 0.6  # cost of one bend, inches
GREED = 2.0  # weighted A*: trades a little optimality for far fewer expansions
SHARE = 0.8  # extra cost per inch of running along a stretch another edge already uses
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Router:
    def __init__(self, boxes: list[Rect]) -> None:
        self.boxes = boxes
        xs, ys = set(), set()
        for r in boxes:
            xs |= {round(r.left - CLEAR, 4), round(r.right + CLEAR, 4), *(round(x, 4) for x in _ports(r.x, r.w))}
            ys |= {round(r.bottom - CLEAR, 4), round(r.top + CLEAR, 4), *(round(y, 4) for y in _ports(r.y, r.h))}
        self.xs, self.ys = sorted(xs), sorted(ys)
        self._rows: dict[int, list[tuple[float, float]]] = {}
        self._cols: dict[int, list[tuple[float, float]]] = {}
        self._used: set[tuple[tuple[int, int], tuple[int, int]]] = set()
        self._ports_used: set[Point] = set()

    def blocked(self, pts: list[Point], skip: tuple[Rect, ...]) -> bool:
        """Does the polyline pass through any box other than skip?"""
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            lo_x, hi_x, lo_y, hi_y = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
            for r in self.boxes:
                if any(r is s for s in skip):
                    continue
                if lo_x < r.right and hi_x > r.left and lo_y < r.top and hi_y > r.bottom:
                    return True
        return False

    def route(self, a: Rect, b: Rect) -> list[Point] | None:
        """Shortest low-bend orthogonal path from a side of a to a side of b, or None."""
        starts = self._stubs(a)
        goals = {g[1]: g for g in self._stubs(b)}
        if not starts or not goals:
            return None
        gx = [self.xs[i] for i, _ in goals]
        gy = [self.ys[j] for _, j in goals]

        goal_pts = list(zip(gx, gy))

        def h(i: int, j: int) -> float:
            x, y = self.xs[i], self.ys[j]
            return GREED * min(abs(x - u) + abs(y - v) for u, v in goal_pts)

        heap: list[tuple[float, float, tuple[int, int], int]] = []
        best: dict[tuple[tuple[int, int], int], float] = {}
        prev: dict[tuple[tuple[int, int], int], tuple[tuple[int, int], int] | None] = {}
        for border, cell, d in starts:
            key = (cell, d)
            best[key] = BEND if border in self._ports_used else 0.0
            prev[key] = None
            heapq.heappush(heap, (h(*cell) + best[key], best[key], cell, d))
        border_of = {(c, d): p for p, c, d in starts}
        while heap:
            _, cost, cell, d = heapq.heappop(heap)
            if cost > best.get((cell, d), float("inf")) + 1e-9:
                continue
            if cell in goals and d != goals[cell][2]:
                pts = self._unwind((cell, d), prev)
                for (c1, _), (c2, _) in zip(pts, pts[1:]):
                    self._used |= {(c1, c2), (c2, c1)}
                self._ports_used |= {border_of[pts[0]], goals[cell][0]}
                return [border_of[pts[0]], *[self._pt(c) for c, _ in pts], goals[cell][0]]
            for nd, (di, dj) in enumerate(STEPS):
                if _opposite(d, nd):
                    continue
                ni, nj = cell[0] + di, cell[1] + dj
                if not (0 <= ni < len(self.xs) and 0 <= nj < len(self.ys)):
                    continue
                if not self._free(cell, (ni, nj)):
                    continue
                step = abs(self.xs[ni] - self.xs[cell[0]]) + abs(self.ys[nj] - self.ys[cell[1]])
                shared = SHARE * step if (cell, (ni, nj)) in self._used else 0.0
                if (ni, nj) in goals and goals[(ni, nj)][0] in self._ports_used:
                    shared += BEND
                nc = cost + step + shared + (BEND if nd != d else 0.0)
                key = ((ni, nj), nd)
                if nc < best.get(key, float("inf")) - 1e-9:
                    best[key] = nc
                    prev[key] = (cell, d)
                    heapq.heappush(heap, (nc + h(ni, nj), nc, (ni, nj), nd))
        return None

    def _stubs(self, r: Rect) -> list[tuple[Point, tuple[int, int], int]]:
        """(border point, grid cell just outside it, direction of travel away from the box)."""
        cands = [((r.right, y), (r.right + CLEAR, y), 0) for y in _ports(r.y, r.h)]
        cands += [((r.left, y), (r.left - CLEAR, y), 1) for y in _ports(r.y, r.h)]
        cands += [((x, r.top), (x, r.top + CLEAR), 2) for x in _ports(r.x, r.w)]
        cands += [((x, r.bottom), (x, r.bottom - CLEAR), 3) for x in _ports(r.x, r.w)]
        out = []
        for border, outside, d in cands:
            i, j = _index(self.xs, outside[0]), _index(self.ys, outside[1])
            if i is not None and j is not None and not self._inside(self.xs[i], self.ys[j]):
                out.append((border, (i, j), d))
        return out

    def _pt(self, cell: tuple[int, int]) -> Point:
        return (self.xs[cell[0]], self.ys[cell[1]])

    def _unwind(self, key: tuple, prev: dict) -> list[tuple[tuple[int, int], int]]:
        out = []
        while key is not None:
            out.append(key)
            key = prev[key]
        return out[::-1]

    def _inside(self, x: float, y: float) -> bool:
        return any(r.left - PAD < x < r.right + PAD and r.bottom - PAD < y < r.top + PAD for r in self.boxes)

    def _free(self, c1: tuple[int, int], c2: tuple[int, int]) -> bool:
        if c1[1] == c2[1]:
            lo, hi = sorted((self.xs[c1[0]], self.xs[c2[0]]))
            spans = self._row(c1[1])
        else:
            lo, hi = sorted((self.ys[c1[1]], self.ys[c2[1]]))
            spans = self._col(c1[0])
        return not any(s < hi and e > lo for s, e in spans)

    def _row(self, j: int) -> list[tuple[float, float]]:
        if j not in self._rows:
            y = self.ys[j]
            self._rows[j] = [(r.left - PAD, r.right + PAD) for r in self.boxes
                             if r.bottom - PAD < y < r.top + PAD]
        return self._rows[j]

    def _col(self, i: int) -> list[tuple[float, float]]:
        if i not in self._cols:
            x = self.xs[i]
            self._cols[i] = [(r.bottom - PAD, r.top + PAD) for r in self.boxes
                             if r.left - PAD < x < r.right + PAD]
        return self._cols[i]


def _ports(c: float, size: float) -> tuple[float, ...]:
    """Attachment points along one side: the middle, plus quarter points on long sides."""
    return (c, c - size / 4, c + size / 4) if size >= 1.0 else (c,)


def _index(vals: list[float], v: float) -> int | None:
    i = bisect_left(vals, round(v, 4) - 1e-6)
    return i if i < len(vals) and abs(vals[i] - round(v, 4)) < 1e-6 else None


def _opposite(d1: int, d2: int) -> bool:
    """Directions 0/1 and 2/3 are opposite."""
    return d1 != d2 and d1 // 2 == d2 // 2
