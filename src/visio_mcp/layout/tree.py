"""Tidy tree (Reingold-Tilford style): parents centered over children, subtrees packed by contour."""

from __future__ import annotations

from visio_mcp.layout.compound import Frag, Placed
from visio_mcp.layout.model import LABEL_PT, NODE_GAP, RANK_GAP_LR, RANK_GAP_TB, Frame
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import NodeSize, text_width

Contour = list[tuple[float, float]]  # (lo, hi) across the rank, per depth below the subtree root


def is_forest(spec: DiagramSpec) -> bool:
    """Every node has at most one parent (edge source) and there are no cycles or self loops."""
    parent: dict[str, str] = {}
    for e in spec.edges:
        if e.source == e.target or e.target in parent:
            return False
        parent[e.target] = e.source
    for n in spec.nodes:
        seen, cur = {n.id}, parent.get(n.id)
        while cur is not None:
            if cur in seen:
                return False
            seen.add(cur)
            cur = parent.get(cur)
    return True


def tree_layout(spec: DiagramSpec, sizes: dict[str, NodeSize], frame: Frame) -> Placed:
    kids: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    has_parent = set()
    for e in spec.edges:
        kids[e.source].append(e.target)
        has_parent.add(e.target)
    dims = {nid: frame.size(s.w, s.h) for nid, s in sizes.items()}
    depth: dict[str, int] = {}

    def subtree(v: str, d: int) -> tuple[dict[str, float], Contour]:
        depth[v] = d
        pos, contour = _pack([subtree(k, d + 1) for k in kids[v]])
        if kids[v]:
            mid = (pos[kids[v][0]] + pos[kids[v][-1]]) / 2
            pos = {k: u - mid for k, u in pos.items()}
            contour = [(lo - mid, hi - mid) for lo, hi in contour]
        half = dims[v][0] / 2
        return {v: 0.0, **pos}, [(-half, half), *contour]

    roots = [n.id for n in spec.nodes if n.id not in has_parent]
    pos, _ = _pack([subtree(r, 0) for r in roots])
    left = min(u - dims[k][0] / 2 for k, u in pos.items())
    levels = max(depth.values()) + 1
    band = [0.0] * levels
    for k, d in depth.items():
        band[d] = max(band[d], dims[k][1])
    base = RANK_GAP_LR if frame.lr else RANK_GAP_TB
    gaps = [base] * levels
    for e in spec.edges:
        if e.label:
            need = text_width(e.label, LABEL_PT) + 0.5 if frame.lr else base + 0.25
            gaps[depth[e.source]] = max(gaps[depth[e.source]], need)
    starts, v = [], 0.0
    for d in range(levels):
        starts.append(v)
        v += band[d] + gaps[d]
    out = Placed({}, {}, {}, {})
    for k, u in pos.items():
        d = depth[k]
        out.nodes[k] = (u - left, starts[d] + band[d] / 2, *dims[k])
    for i, e in enumerate(spec.edges):
        d = depth[e.source]
        jog = starts[d] + band[d] + gaps[d] / 2
        out.paths[i] = Frag([out.nodes[e.source][0], out.nodes[e.target][0]], [jog])
        out.forward[i] = True
    return out


def _pack(subs: list[tuple[dict[str, float], Contour]]) -> tuple[dict[str, float], Contour]:
    """Place subtrees left to right, each as close as its contour allows."""
    pos: dict[str, float] = {}
    contour: Contour = []
    for sp, sc in subs:
        shift = 0.0
        if contour:
            shift = max(contour[d][1] - sc[d][0] + NODE_GAP for d in range(min(len(contour), len(sc))))
        pos.update({k: u + shift for k, u in sp.items()})
        for d, (lo, hi) in enumerate(sc):
            if d < len(contour):
                contour[d] = (min(contour[d][0], lo + shift), max(contour[d][1], hi + shift))
            else:
                contour.append((lo + shift, hi + shift))
    return pos, contour
