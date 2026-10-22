"""Compound (group-aware) layout: each group is laid out as a block, bottom-up through the nesting.

A block becomes one box in its parent's layout. Edges between members of different groups
are lifted to the items standing for their endpoints in the lowest common scope; where an
edge crosses a group frame, the group's own layout gives it a lane through its ranks to the
frame (so it never crosses members) and reports that lane as a port on the block.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from visio_mcp.layout import radial
from visio_mcp.layout.hierarchy import Hierarchy, Scope
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
from visio_mcp.layout.model import COMPACT_GAP, LOOP, NODE_GAP, RANK_GAP_LR, RANK_GAP_TB, Frame
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GroupStyle, NodeSize, text_width

Mode = Literal["layered", "grid", "radial", "circular"]
Box = tuple[float, float, float, float]  # u, v (center), cw, ah in flow coordinates
DECISION_KINDS = {"decision", "diamond", "gateway-exclusive", "choice"}


@dataclass
class Frag:
    """An edge's path through one scope, in travel order: lane u per rank, jog v between lanes."""

    lanes: list[float]
    jogs: list[float]
    side_start: int = 0
    side_end: int = 0

    def shifted(self, du: float, dv: float) -> Frag:
        return Frag([x + du for x in self.lanes], [y + dv for y in self.jogs], self.side_start, self.side_end)


@dataclass
class Block:
    cw: float
    ah: float
    pos: dict[str, tuple[float, float]] = field(default_factory=dict)  # item centers from the top-left
    children: dict[str, Block] = field(default_factory=dict)
    frags: dict[int, Frag] = field(default_factory=dict)
    ports: dict[int, float] = field(default_factory=dict)  # edge crossing the frame -> u from the left


@dataclass
class Placed:
    nodes: dict[str, Box]
    groups: dict[str, Box]
    paths: dict[int, Frag]  # layered mode only: whole path per edge
    forward: dict[int, bool]


class Compound:
    def __init__(self, spec: DiagramSpec, sizes: dict[str, NodeSize], styles: dict[str, GroupStyle],
                 frame: Frame, root: Mode) -> None:
        self.spec, self.sizes, self.styles, self.frame = spec, sizes, styles, frame
        self.root = root
        self.inner: Mode = "layered" if root == "layered" else "grid"
        self.h = Hierarchy(spec)
        self.loops = {e.source for e in spec.edges if e.source == e.target}
        self.decisions = {n.id for n in spec.nodes if n.kind in DECISION_KINDS}
        self.labels = {g.id: g.label or g.id for g in spec.groups}
        self._lift_edges()

    # --- edge bookkeeping ----------------------------------------------------------------

    def _lift_edges(self) -> None:
        h = self.h
        self.scope_edges: dict[Scope, list[tuple[int, str, str]]] = defaultdict(list)
        for e, edge in enumerate(self.spec.edges):
            if edge.source != edge.target:
                s, a, b = h.lift(edge.source, edge.target)
                self.scope_edges[s].append((e, a, b))
        self.reversed: set[int] = set()
        for s, lst in self.scope_edges.items():
            idx = {it: i for i, it in enumerate(h.children[s])}
            rev = break_cycles(len(idx), [(idx[a], idx[b]) for _, a, b in lst])
            self.reversed |= {lst[i][0] for i in rev}
        # edges crossing group frames: (edge, item, frame side, role)
        self.external: dict[Scope, list[tuple[int, str, str, str]]] = defaultdict(list)
        for s, lst in self.scope_edges.items():
            for e, _, _ in lst:
                fwd = e not in self.reversed
                edge = self.spec.edges[e]
                for g in h.between(edge.source, s):
                    self.external[g].append((e, h.item_in(g, edge.source), "end" if fwd else "start", "src"))
                for g in h.between(edge.target, s):
                    self.external[g].append((e, h.item_in(g, edge.target), "start" if fwd else "end", "tgt"))

    # --- blocks ----------------------------------------------------------------------------

    def block(self, scope: Scope) -> Block:
        items = self.h.children[scope]
        kids = {it: self.block(it) for it in items if self.h.is_group(it)}
        if scope is None:
            insets = (0.0, 0.0, 0.0, 0.0)
        else:
            insets = self.frame.insets(self.styles[scope])
        mode = self.root if scope is None else self.inner
        if mode == "layered":
            b = self._layered(scope, items, kids, insets)
        elif mode == "grid" or len(items) < 2:
            b = self._grid(items, kids, insets)
        else:
            b = self._ring(scope, items, kids, mode)
        if scope is not None:
            self._fit_label(b, scope, insets)
        b.children = kids
        return b

    def _size(self, it: str, kids: dict[str, Block]) -> tuple[float, float]:
        if it in kids:
            return kids[it].cw, kids[it].ah
        s = self.sizes[it]
        return self.frame.size(s.w, s.h)

    def _layered(self, scope: Scope, items: list[str], kids: dict[str, Block],
                 insets: tuple[float, float, float, float]) -> Block:
        lg = LayerGraph()
        vid: dict[str, int] = {}
        for i, it in enumerate(items):
            cw, ah = self._size(it, kids)
            kind = "block" if it in kids else "node"
            vid[it] = lg.add(Vert(it, cw, ah, kind, float(i), decision=it in self.decisions, loop=it in self.loops))
        internal = self.scope_edges.get(scope, [])
        dag = [(vid[b], vid[a]) if e in self.reversed else (vid[a], vid[b]) for e, a, b in internal]
        ext = self.external.get(scope, [])
        compact = not internal
        if compact and len(items) > 4:
            per = math.ceil(math.sqrt(len(items)))
            ranks = [i // per for i in range(len(items))]
        else:
            linked = {x for pair in dag for x in pair}
            faces: dict[int, set[str]] = defaultdict(set)
            for _, it, side, _ in ext:
                faces[vid[it]].add(side)
            pull = {v for v, f in faces.items() if f == {"end"} and v not in linked}
            ranks = rank_dag(len(items), dag, pull)
        for i, r in enumerate(ranks):
            lg.verts[i].rank = r
        last = max(ranks, default=0)

        def port(it: str, e: int) -> float | None:
            return kids[it].ports[e] - kids[it].cw / 2 if it in kids else None

        for (e, a, b), (x, y) in zip(internal, dag):
            up = e in self.reversed
            top, bottom = (b, a) if up else (a, b)
            lg.add_chain(e, x, y, upward=up, port_top=port(top, e), port_bottom=port(bottom, e),
                         label=self.spec.edges[e].label)
        for e, it, side, role in ext:
            x, label = vid[it], self.spec.edges[e].label
            if side == "end":
                lg.add_chain(e, x, None, last_rank=last, upward=role == "tgt", port_top=port(it, e), label=label)
            else:
                lg.add_chain(e, None, x, first_rank=0, upward=role == "src", port_bottom=port(it, e), label=label)
        lg.build_layers()
        order(lg)
        assign_cross(lg)
        ub, ua, vb, va = insets
        left = min(v.u - v.cw / 2 for v in lg.verts)
        for v in lg.verts:
            v.u += ub - left
        assign_ports(lg)
        gap = COMPACT_GAP if compact else (RANK_GAP_LR if self.frame.lr else RANK_GAP_TB)
        starts = assign_along(lg, vb, gap, self.frame.lr, compact)
        right = max(v.u + v.cw / 2 + (LOOP if v.loop else 0.0) for v in lg.verts)
        b = Block(right + ua, starts[-1] + va)
        for it, i in vid.items():
            b.pos[it] = (lg.verts[i].u, lg.verts[i].v)
        for c in lg.chains:
            lanes, jogs, s0, s1 = c.lanes, c.jogs, c.side_top, c.side_bottom
            if c.open_top:
                b.ports[c.edge] = lanes[0]
            if c.open_bottom:
                b.ports[c.edge] = lanes[-1]
            if c.upward:
                lanes, jogs, s0, s1 = lanes[::-1], jogs[::-1], s1, s0
            b.frags[c.edge] = Frag(lanes, jogs, s0, s1)
        return b

    def _grid(self, items: list[str], kids: dict[str, Block], insets: tuple[float, float, float, float]) -> Block:
        """Tidy grid of plain nodes (column widths and row heights align); shelf rows when blocks mix in."""
        ub, ua, vb, va = insets
        dims = [self._size(it, kids) for it in items]
        b = Block(0.0, 0.0)
        gap_u, gap_v = NODE_GAP + 0.1, NODE_GAP + 0.1
        if not kids:
            cols = max(1, math.ceil(math.sqrt(len(items))))
            colw = [max(d[0] for d in dims[c::cols]) for c in range(cols)]
            rows = math.ceil(len(items) / cols)
            rowh = [max(d[1] for d in dims[r * cols:(r + 1) * cols]) for r in range(rows)]
            for i, it in enumerate(items):
                r, c = divmod(i, cols)
                u = ub + sum(colw[:c]) + c * gap_u + colw[c] / 2
                v = vb + sum(rowh[:r]) + r * gap_v + rowh[r] / 2
                b.pos[it] = (u, v)
            b.cw = ub + sum(colw) + (cols - 1) * gap_u + ua
            b.ah = vb + sum(rowh) + (rows - 1) * gap_v + va
            return b
        target = max(max(d[0] for d in dims), math.sqrt(sum(d[0] * d[1] for d in dims)) * 1.5)
        rows: list[list[int]] = [[]]
        width = 0.0
        for i, (cw, _) in enumerate(dims):
            if rows[-1] and width + gap_u + cw > target:
                rows.append([])
                width = 0.0
            width += (gap_u if rows[-1] else 0.0) + cw
            rows[-1].append(i)
        v = vb
        full = 0.0
        for row in rows:
            rh = max(dims[i][1] for i in row)
            u = ub
            for i in row:
                b.pos[items[i]] = (u + dims[i][0] / 2, v + rh / 2)
                u += dims[i][0] + gap_u
            full = max(full, u - gap_u)
            v += rh + gap_v
        b.cw, b.ah = full + ua, v - gap_v + va
        return b

    def _ring(self, scope: Scope, items: list[str], kids: dict[str, Block], mode: Mode) -> Block:
        """Top-level radial / circular arrangement of nodes and group blocks."""
        idx = {it: i for i, it in enumerate(items)}
        dims = [self._size(it, kids) for it in items]
        pairs = [(idx[a], idx[b]) for _, a, b in self.scope_edges.get(scope, [])]
        fn = radial.radial_centers if mode == "radial" else radial.circular_centers
        centers = fn(dims, pairs)
        left = min(x - d[0] / 2 for (x, _), d in zip(centers, dims))
        top = max(y + d[1] / 2 for (_, y), d in zip(centers, dims))
        b = Block(0.0, 0.0)
        for it, (x, y), (cw, ah) in zip(items, centers, dims):
            b.pos[it] = (x - left, top - y)
            b.cw = max(b.cw, x - left + cw / 2)
            b.ah = max(b.ah, top - y + ah / 2)
        return b

    def _fit_label(self, b: Block, scope: str, insets: tuple[float, float, float, float]) -> None:
        """Widen a frame whose header label is longer than its members, keeping members centered."""
        st = self.styles[scope]
        need = text_width(self.labels.get(scope, scope), st.header.size, st.header.bold) + 2 * st.padding + 0.2
        along = self.frame.lr  # the header text runs along the page x axis
        have = b.ah if along else b.cw
        if have >= need:
            return
        d = (need - have) / 2
        b.pos = {k: (u, v + d) if along else (u + d, v) for k, (u, v) in b.pos.items()}
        b.frags = {k: f.shifted(0.0, d) if along else f.shifted(d, 0.0) for k, f in b.frags.items()}
        if not along:
            b.ports = {k: p + d for k, p in b.ports.items()}
        if along:
            b.ah = need
        else:
            b.cw = need

    # --- placement -------------------------------------------------------------------------

    def run(self) -> Placed:
        root = self.block(None)
        out = Placed({}, {}, {}, {})
        frags: dict[int, dict[Scope, Frag]] = defaultdict(dict)
        self._place(root, None, 0.0, 0.0, out, frags)
        if self.root == "layered":
            for e, edge in enumerate(self.spec.edges):
                if edge.source == edge.target:
                    continue
                scope, _, _ = self.h.lift(edge.source, edge.target)
                seq = self.h.between(edge.source, scope) + [scope] + self.h.between(edge.target, scope)[::-1]
                out.paths[e] = _join([frags[e][s] for s in seq])
                out.forward[e] = e not in self.reversed
        return out

    def _place(self, b: Block, scope: Scope, ou: float, ov: float, out: Placed,
               frags: dict[int, dict[Scope, Frag]]) -> None:
        for it, (u, v) in b.pos.items():
            au, av = ou + u, ov + v
            if it in b.children:
                kid = b.children[it]
                out.groups[it] = (au, av, kid.cw, kid.ah)
                self._place(kid, it, au - kid.cw / 2, av - kid.ah / 2, out, frags)
            else:
                cw, ah = self._size(it, {})
                out.nodes[it] = (au, av, cw, ah)
        for e, f in b.frags.items():
            frags[e][scope] = f.shifted(ou, ov)


def _join(parts: list[Frag]) -> Frag:
    """Concatenate fragments that meet on a shared lane at each frame crossing."""
    lanes, jogs = list(parts[0].lanes), list(parts[0].jogs)
    for f in parts[1:]:
        lanes += f.lanes[1:]
        jogs += f.jogs
    return Frag(lanes, jogs, parts[0].side_start, parts[-1].side_end)
