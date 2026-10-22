"""Group-aware auto-layout: DiagramSpec + node sizes -> positions, group frames, edge routes.

PLACEHOLDER: a naive grid so the pipeline runs. The real layered engine replaces
compute_layout() but keeps Rect, LayoutResult and the compute_layout signature.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GroupStyle, NodeSize

Point = tuple[float, float]


@dataclass
class Rect:
    """Axis-aligned box by center, inches, origin bottom-left."""

    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x - self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w / 2

    @property
    def bottom(self) -> float:
        return self.y - self.h / 2

    @property
    def top(self) -> float:
        return self.y + self.h / 2


@dataclass
class LayoutResult:
    nodes: dict[str, Rect]  # node footprints by node id
    groups: dict[str, Rect]  # group frames by group id (include padding and header band)
    routes: dict[int, list[Point]] = field(default_factory=dict)  # by index in spec.edges
    width: float = 0.0  # extent of everything; all coordinates lie in [0, width] x [0, height]
    height: float = 0.0
    direction: Literal["tb", "lr", "none"] = "tb"


def compute_layout(
    spec: DiagramSpec, sizes: dict[str, NodeSize], group_styles: dict[str, GroupStyle], layout: str
) -> LayoutResult:
    """Place every node and group. layout is a concrete spec Layout (never 'auto')."""
    ids = [n.id for n in spec.nodes]
    cols = max(1, math.ceil(math.sqrt(len(ids))))
    nodes = {}
    for i, nid in enumerate(ids):
        s = sizes[nid]
        nodes[nid] = Rect(1.5 + (i % cols) * 3.0, 1.5 + (i // cols) * 2.0, s.w, s.h)
    groups = {}
    for g in spec.groups:
        members = [nodes[n.id] for n in spec.nodes if n.group == g.id]
        if not members:
            continue
        st = group_styles[g.id]
        left = min(r.left for r in members) - st.padding
        right = max(r.right for r in members) + st.padding
        bottom = min(r.bottom for r in members) - st.padding
        top = max(r.top for r in members) + st.padding + st.header_height
        groups[g.id] = Rect((left + right) / 2, (bottom + top) / 2, right - left, top - bottom)
    routes = {}
    for i, e in enumerate(spec.edges):
        a, b = nodes[e.source], nodes[e.target]
        routes[i] = [(a.x, a.y), (b.x, b.y)]
    w = max(r.right for r in list(nodes.values()) + list(groups.values())) + 0.5
    h = max(r.top for r in list(nodes.values()) + list(groups.values())) + 0.5
    return LayoutResult(nodes, groups, routes, w, h, "tb")
