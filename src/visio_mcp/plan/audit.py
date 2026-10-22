"""Geometry audit of a DiagramPlan: everything that would make a diagram look broken.

Used by tests, by the CLI (`visio-ai check`) and before every render, so problems surface as
warnings instead of reaching the user's Visio page.
"""

from __future__ import annotations

from visio_mcp.layout import Rect
from visio_mcp.plan.model import DiagramPlan

EPS = 0.01  # inches; touching is fine, overlapping is not


def _overlap(a: Rect, b: Rect, gap: float = 0.0) -> bool:
    return (a.left < b.right + gap - EPS and b.left < a.right + gap - EPS
            and a.bottom < b.top + gap - EPS and b.bottom < a.top + gap - EPS)


def _inside(inner: Rect, outer: Rect) -> bool:
    return (inner.left >= outer.left - EPS and inner.right <= outer.right + EPS
            and inner.bottom >= outer.bottom - EPS and inner.top <= outer.top + EPS)


def audit(plan: DiagramPlan) -> list[str]:
    """Problems found, as readable one-liners. Empty means the geometry is clean."""
    problems: list[str] = []
    nodes = plan.nodes
    groups = {g.id: g for g in plan.groups}
    spec_group = {n.id: n.group for n in plan.spec.nodes}

    def ancestors(gid: str | None) -> list[str]:
        out = []
        while gid:
            out.append(gid)
            gid = groups[gid].parent if gid in groups else None
        return out

    # node vs node
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if _overlap(a.rect, b.rect):
                problems.append(f"nodes overlap: {a.id} and {b.id}")

    # node inside every group it belongs to, and outside every group it doesn't
    for n in nodes:
        mine = set(ancestors(spec_group.get(n.id)))
        for gid, g in groups.items():
            if gid in mine:
                if not _inside(n.rect, g.rect):
                    problems.append(f"node {n.id} sticks out of its group {gid}")
            elif _overlap(n.rect, g.rect):
                problems.append(f"node {n.id} intrudes into group {gid}")

    # groups: nested inside parents, siblings and unrelated groups apart
    ids = list(groups)
    for i, a in enumerate(ids):
        ga = groups[a]
        if ga.parent and ga.parent in groups and not _inside(ga.rect, groups[ga.parent].rect):
            problems.append(f"group {a} sticks out of its parent {ga.parent}")
        for b in ids[i + 1:]:
            if a in ancestors(b) or b in ancestors(a):
                continue
            if _overlap(ga.rect, groups[b].rect):
                problems.append(f"groups overlap: {a} and {b}")

    # decorations clear of the diagram
    content = [n.rect for n in nodes] + [g.rect for g in plan.groups]
    for label, r in (("title", plan.title.rect if plan.title else None), ("legend", plan.legend)):
        if r is not None and any(_overlap(r, c) for c in content):
            problems.append(f"{label} overlaps the diagram")

    # everything on the page
    for r in content + [x for x in (plan.legend, plan.title.rect if plan.title else None) if x]:
        if r.left < -EPS or r.bottom < -EPS or r.right > plan.width + EPS or r.top > plan.height + EPS:
            problems.append("content runs off the page")
            break

    # edges should not cut through unrelated nodes
    by_id = {n.id: n for n in nodes}
    for e in plan.edges:
        for (x1, y1), (x2, y2) in zip(e.points, e.points[1:]):
            seg = Rect((x1 + x2) / 2, (y1 + y2) / 2, abs(x2 - x1) + 1e-3, abs(y2 - y1) + 1e-3)
            for nid, n in by_id.items():
                if nid in (e.source, e.target):
                    continue
                r = n.shape
                if _overlap(seg, Rect(r.x, r.y, max(r.w - 0.1, 0.01), max(r.h - 0.1, 0.01))):
                    problems.append(f"edge {e.name} crosses node {nid}")
                    break
    return list(dict.fromkeys(problems))
