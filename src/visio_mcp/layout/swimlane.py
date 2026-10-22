"""Swimlanes: top-level groups become full-length bands; flow ranks are shared by every lane."""

from __future__ import annotations

from visio_mcp.layout.compound import DECISION_KINDS, Frag, Placed
from visio_mcp.layout.hierarchy import Hierarchy
from visio_mcp.layout.layered import (
    LayerGraph,
    Vert,
    assign_along,
    assign_cross,
    assign_ports,
    break_cycles,
    order,
    rank_dag,
)
from visio_mcp.layout.model import LOOP, RANK_GAP_LR, RANK_GAP_TB, Frame
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GroupStyle, NodeSize

MIN_LANE = 1.2  # thinnest lane band, inches across the flow


def swimlane_layout(spec: DiagramSpec, sizes: dict[str, NodeSize], styles: dict[str, GroupStyle],
                    frame: Frame) -> Placed:
    h = Hierarchy(spec)
    lanes = [g for g in h.groups if h.parent[g] is None]
    lane_of = {n.id: lanes.index(h.ancestors(n.id)[-1]) if n.group else len(lanes) for n in spec.nodes}
    count = len(lanes) + (1 if any(not n.group for n in spec.nodes) else 0)
    ids = [n.id for n in spec.nodes]
    idx = {nid: i for i, nid in enumerate(ids)}
    loops = {e.source for e in spec.edges if e.source == e.target}
    decisions = {n.id for n in spec.nodes if n.kind in DECISION_KINDS}

    lg = LayerGraph()
    for i, nid in enumerate(ids):
        cw, ah = frame.size(sizes[nid].w, sizes[nid].h)
        lg.add(Vert(nid, cw, ah, "node", float(i), lane=lane_of[nid], decision=nid in decisions, loop=nid in loops))
    real = [(e, idx[x.source], idx[x.target]) for e, x in enumerate(spec.edges) if x.source != x.target]
    rev = break_cycles(len(ids), [(a, b) for _, a, b in real])
    dag = [(b, a) if i in rev else (a, b) for i, (_, a, b) in enumerate(real)]
    for v, r in zip(lg.verts, rank_dag(len(ids), dag)):
        v.rank = r
    reversed_edges = {real[i][0] for i in rev}
    for (e, _, b), (top, bottom) in zip(real, dag):
        lg.add_chain(e, top, bottom, lane=lane_of[ids[b]], upward=e in reversed_edges, label=spec.edges[e].label)
    lg.build_layers()
    order(lg)

    pad = {i: (styles[g].padding if i < len(lanes) else 0.3) for i, g in enumerate(lanes + [None])}
    offset = 0.0
    bands: list[tuple[float, float]] = []
    for lane in range(count):
        members = {i for i, v in enumerate(lg.verts) if v.lane == lane}
        assign_cross(lg, members)
        if members:
            lo = min(lg.verts[i].u - lg.verts[i].cw / 2 for i in members)
            hi = max(lg.verts[i].u + lg.verts[i].cw / 2 + (LOOP if lg.verts[i].loop else 0) for i in members)
        else:
            lo = hi = 0.0
        size = max(hi - lo + 2 * pad[lane], MIN_LANE)
        shift = offset + (size - (hi - lo)) / 2 - lo
        for i in members:
            lg.verts[i].u += shift
        bands.append((offset, size))
        offset += size
    assign_ports(lg)

    head = max((styles[g].header_height + styles[g].padding for g in lanes), default=0.3)
    tail = max((styles[g].padding for g in lanes), default=0.3)
    starts = assign_along(lg, head, RANK_GAP_LR if frame.lr else RANK_GAP_TB, frame.lr)
    length = starts[-1] + tail

    out = Placed({}, {}, {}, {})
    for v in lg.verts:
        if not v.dummy:
            out.nodes[v.key] = (v.u, v.v, v.cw, v.ah)
    for g, (off, size) in zip(lanes, bands):
        out.groups[g] = (off + size / 2, length / 2, size, length)
    _nested_frames(h, lanes, styles, frame, out)
    for c in lg.chains:
        lanes_, jogs, s0, s1 = c.lanes, c.jogs, c.side_top, c.side_bottom
        if c.upward:
            lanes_, jogs, s0, s1 = lanes_[::-1], jogs[::-1], s1, s0
        out.paths[c.edge] = Frag(lanes_, jogs, s0, s1)
        out.forward[c.edge] = not c.upward
    return out


def _nested_frames(h: Hierarchy, lanes: list[str], styles: dict[str, GroupStyle], frame: Frame,
                   out: Placed) -> None:
    """Groups inside a lane are framed around their members (bounding box + padding + header)."""
    for g in h.depth_first():
        if g in lanes:
            continue
        boxes = [out.nodes[i] if i in out.nodes else out.groups[i] for i in h.children[g]]
        ub, ua, vb, va = frame.insets(styles[g])
        lo_u = min(b[0] - b[2] / 2 for b in boxes) - ub
        hi_u = max(b[0] + b[2] / 2 for b in boxes) + ua
        lo_v = min(b[1] - b[3] / 2 for b in boxes) - vb
        hi_v = max(b[1] + b[3] / 2 for b in boxes) + va
        out.groups[g] = ((lo_u + hi_u) / 2, (lo_v + hi_v) / 2, hi_u - lo_u, hi_v - lo_v)
