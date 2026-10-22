"""Radial (hub and rings) and circular arrangements of boxes. Page coordinates, y up."""

from __future__ import annotations

import math
from collections import deque

GAP = 0.45  # clearance between boxes on a ring or between rings
COMPONENT_GAP = 1.0

Dims = list[tuple[float, float]]
Centers = list[tuple[float, float]]


def radial_centers(dims: Dims, pairs: list[tuple[int, int]]) -> Centers:
    """Hub (highest degree) in the middle, rings by BFS distance, sectors sized by subtree."""
    adj = _adjacency(len(dims), pairs)
    out: Centers = [(0.0, 0.0)] * len(dims)
    parts = []
    for comp in _components(adj):
        hub = max(comp, key=lambda v: (len(adj[v]), -v))
        parts.append((comp, _radial(dims, adj, hub)))
    return _pack(parts, dims, out)


def circular_centers(dims: Dims, pairs: list[tuple[int, int]]) -> Centers:
    """All boxes on one circle, in an order that keeps neighbours together (DFS)."""
    n = len(dims)
    if n == 1:
        return [(0.0, 0.0)]
    adj = _adjacency(n, pairs)
    seq: list[int] = []
    seen: set[int] = set()
    for root in range(n):
        stack = [root]
        while stack:
            v = stack.pop()
            if v in seen:
                continue
            seen.add(v)
            seq.append(v)
            stack.extend(sorted(adj[v], reverse=True))
    size = [_radius(dims[v]) * 2 + GAP for v in seq]
    total = sum(size)
    angles, acc = [], 0.0
    for s in size:
        angles.append(math.pi / 2 - 2 * math.pi * (acc + s / 2) / total)
        acc += s
    r = total / (2 * math.pi)
    for i in range(n):
        j = (i + 1) % n
        d = (angles[i] - angles[j]) % (2 * math.pi)
        need = (size[i] + size[j]) / 2
        if 0 < d < math.pi:
            r = max(r, need / (2 * math.sin(d / 2)))
    pos = {v: (r * math.cos(a), r * math.sin(a)) for v, a in zip(seq, angles)}
    return _spread_until_clear([pos[v] for v in range(n)], dims, (0.0, 0.0))


def _adjacency(n: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    adj: list[set[int]] = [set() for _ in range(n)]
    for a, b in pairs:
        if a != b:
            adj[a].add(b)
            adj[b].add(a)
    return [sorted(s) for s in adj]


def _components(adj: list[list[int]]) -> list[list[int]]:
    seen: set[int] = set()
    comps = []
    for s in range(len(adj)):
        if s in seen:
            continue
        comp, queue = [], deque([s])
        seen.add(s)
        while queue:
            v = queue.popleft()
            comp.append(v)
            for w in adj[v]:
                if w not in seen:
                    seen.add(w)
                    queue.append(w)
        comps.append(sorted(comp))
    return comps


def _radius(d: tuple[float, float]) -> float:
    return math.hypot(d[0], d[1]) / 2


def _radial(dims: Dims, adj: list[list[int]], hub: int) -> dict[int, tuple[float, float]]:
    parent = {hub: -1}
    depth = {hub: 0}
    kids: dict[int, list[int]] = {hub: []}
    queue = deque([hub])
    while queue:
        v = queue.popleft()
        for w in adj[v]:
            if w not in parent:
                parent[w], depth[w] = v, depth[v] + 1
                kids[v].append(w)
                kids[w] = []
                queue.append(w)
    weight: dict[int, float] = {}
    for v in sorted(parent, key=lambda x: -depth[x]):
        weight[v] = max(1.0, sum(weight[k] for k in kids[v]))
    angle: dict[int, float] = {hub: 0.0}

    def split(v: int, a0: float, a1: float) -> None:
        total = sum(weight[k] for k in kids[v]) or 1.0
        a = a0
        for k in kids[v]:
            span = (a1 - a0) * weight[k] / total
            angle[k] = a + span / 2
            split(k, a, a + span)
            a += span

    split(hub, math.pi / 2, math.pi / 2 - 2 * math.pi)
    rings: dict[int, list[int]] = {}
    for v, d in depth.items():
        rings.setdefault(d, []).append(v)
    radius = {0: 0.0}
    for d in range(1, max(rings) + 1):
        ext_prev = max(_radius(dims[v]) for v in rings[d - 1])
        ext = max(_radius(dims[v]) for v in rings[d])
        r = radius[d - 1] + ext_prev + ext + GAP
        ring = sorted(rings[d], key=lambda v: -angle[v])
        for i in range(len(ring)):
            if len(ring) < 2:
                break
            a, b = ring[i], ring[(i + 1) % len(ring)]
            gap = (angle[a] - angle[b]) % (2 * math.pi)
            need = _radius(dims[a]) + _radius(dims[b]) + GAP
            if 0 < gap < math.pi:
                r = max(r, need / (2 * math.sin(gap / 2)))
        radius[d] = r
    pos = {v: (radius[depth[v]] * math.cos(angle[v]), radius[depth[v]] * math.sin(angle[v])) for v in depth}
    order = sorted(pos)
    clear = _spread_until_clear([pos[v] for v in order], [dims[v] for v in order], pos[hub])
    return dict(zip(order, clear))


def _spread_until_clear(pos: Centers, dims: Dims, center: tuple[float, float]) -> Centers:
    """Scale positions away from center until no two boxes come closer than a small gap."""
    cx, cy = center
    for _ in range(40):
        if not _overlaps(pos, dims):
            return pos
        pos = [(cx + (x - cx) * 1.12, cy + (y - cy) * 1.12) for x, y in pos]
    return pos


def _overlaps(pos: Centers, dims: Dims) -> bool:
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            dx = abs(pos[i][0] - pos[j][0]) - (dims[i][0] + dims[j][0]) / 2
            dy = abs(pos[i][1] - pos[j][1]) - (dims[i][1] + dims[j][1]) / 2
            if dx < 0.2 and dy < 0.2:
                return True
    return False


def _pack(parts: list[tuple[list[int], dict[int, tuple[float, float]]]], dims: Dims, out: Centers) -> Centers:
    """Components side by side, tops aligned."""
    x0 = 0.0
    out = list(out)
    for comp, pos in parts:
        left = min(pos[v][0] - dims[v][0] / 2 for v in comp)
        right = max(pos[v][0] + dims[v][0] / 2 for v in comp)
        top = max(pos[v][1] + dims[v][1] / 2 for v in comp)
        for v in comp:
            out[v] = (pos[v][0] - left + x0, pos[v][1] - top)
        x0 += right - left + COMPONENT_GAP
    return out
