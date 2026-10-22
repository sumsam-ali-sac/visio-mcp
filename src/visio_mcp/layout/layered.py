"""Sugiyama-style layered layout on flow coordinates, shared by the compound and swimlane engines.

A LayerGraph holds boxes (vertices) on integer ranks and chains: one chain per edge
fragment, a run of vertices on consecutive ranks (long edges get dummy vertices, so every
step spans one rank). The pipeline is: rank -> order (crossing reduction) -> cross
coordinates (aligned, compact) -> ports -> rank gaps and edge tracks -> along coordinates.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from visio_mcp.layout.model import DUMMY_GAP, LABEL_PT, LANE_GAP, LOOP, NODE_GAP, TRACK_GAP
from visio_mcp.style import text_width

EPS = 1e-6


@dataclass
class Vert:
    key: str
    cw: float  # extent across the rank
    ah: float  # extent along the flow
    kind: Literal["node", "block", "dummy"]
    index: float = 0.0  # input order, for deterministic tie breaks
    rank: int = 0
    lane: int = 0  # swimlane index (ordering never mixes lanes)
    decision: bool = False  # diamond: secondary exits leave from its side corners
    loop: bool = False  # has a self loop: keep room on its +u side
    u: float = 0.0  # center across the rank
    v: float = 0.0  # center along the flow

    @property
    def dummy(self) -> bool:
        return self.kind == "dummy"


@dataclass
class Chain:
    """One edge fragment through consecutive ranks. verts run from the top rank down."""

    edge: int
    verts: list[int]
    upward: bool = False  # the edge travels from the bottom vert to the top vert
    open_top: bool = False  # continues above verts[0] through the scope boundary
    open_bottom: bool = False
    port_top: float | None = None  # port offset at verts[0]; None = choose (nodes)
    port_bottom: float | None = None
    label: str = ""
    # results
    lanes: list[float] = field(default_factory=list)  # u of the edge at each vert
    jogs: list[float] = field(default_factory=list)  # v of the crossing between vert i and i+1
    side_top: int = 0  # verts[0] is attached on its -u / +u corner instead of top/bottom
    side_bottom: int = 0
    side_lane_top: float | None = None  # lane taken right after a side exit (None: the next lane)
    side_lane_bottom: float | None = None
    weight: float = 1.0  # pull on coordinate assignment (decision main branch > side branches)

    def attach_top(self) -> str | None:
        """Side of verts[0] the edge touches ('start' = upstream face, 'end' = downstream)."""
        if len(self.verts) == 1:
            return "start" if self.open_top else "end"
        return None if self.open_top else "end"

    def attach_bottom(self) -> str | None:
        if len(self.verts) == 1:
            return None
        return None if self.open_bottom else "start"


@dataclass
class Seg:
    a: int  # upper vert
    b: int  # lower vert
    chain: int
    pos: int  # index of a in the chain


class LayerGraph:
    def __init__(self) -> None:
        self.verts: list[Vert] = []
        self.chains: list[Chain] = []
        self.layers: list[list[int]] = []

    def add(self, v: Vert) -> int:
        self.verts.append(v)
        return len(self.verts) - 1

    def add_chain(self, edge: int, top: int | None, bottom: int | None, *, first_rank: int = 0,
                  last_rank: int = 0, lane: int | None = None, upward: bool = False,
                  port_top: float | None = None, port_bottom: float | None = None, label: str = "") -> Chain:
        """Chain from top to bottom (None = the scope boundary at first_rank / last_rank)."""
        r0 = self.verts[top].rank + 1 if top is not None else first_rank
        r1 = self.verts[bottom].rank - 1 if bottom is not None else last_rank
        anchor = self.verts[top if top is not None else bottom]  # type: ignore[index]
        dl = anchor.lane if lane is None else lane
        dummies = [self.add(Vert(f"~{edge}.{r}", 0.0, 0.0, "dummy", anchor.index + 0.5, r, dl))
                   for r in range(r0, r1 + 1)]
        verts = ([top] if top is not None else []) + dummies + ([bottom] if bottom is not None else [])
        if len(verts) == 1:  # vert straight onto the boundary: its one port lives in port_top
            port_top, port_bottom = (port_top if port_top is not None else port_bottom), None
        if top is None and dummies:
            port_top = 0.0
        if bottom is None and dummies:
            port_bottom = 0.0
        c = Chain(edge, verts, upward, top is None, bottom is None, port_top, port_bottom, label)
        if self.verts[verts[0]].dummy:
            c.port_top = 0.0
        if self.verts[verts[-1]].dummy:
            c.port_bottom = 0.0
        self.chains.append(c)
        return c

    def segs(self) -> list[Seg]:
        return [Seg(c.verts[i], c.verts[i + 1], ci, i)
                for ci, c in enumerate(self.chains) for i in range(len(c.verts) - 1)]

    def port(self, s: Seg, upper: bool) -> float:
        c = self.chains[s.chain]
        if upper:
            return (c.port_top or 0.0) if s.pos == 0 else 0.0
        return (c.port_bottom or 0.0) if s.pos + 1 == len(c.verts) - 1 else 0.0

    def build_layers(self) -> None:
        n = max((v.rank for v in self.verts), default=0) + 1
        self.layers = [[] for _ in range(n)]
        for i in sorted(range(len(self.verts)), key=lambda i: (self.verts[i].lane, self.verts[i].index, i)):
            self.layers[self.verts[i].rank].append(i)


# --- ranking -----------------------------------------------------------------------------


def break_cycles(n: int, edges: list[tuple[int, int]]) -> set[int]:
    """Indices of edges to reverse: DFS back edges, starting from sources in input order."""
    adj: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    indeg = [0] * n
    for i, (a, b) in enumerate(edges):
        if a != b:
            adj[a].append((b, i))
            indeg[b] += 1
    state = [0] * n  # 0 new, 1 on stack, 2 done
    rev: set[int] = set()
    for root in [v for v in range(n) if indeg[v] == 0] + list(range(n)):
        if state[root]:
            continue
        state[root] = 1
        stack = [(root, 0)]
        while stack:
            v, k = stack[-1]
            if k < len(adj[v]):
                stack[-1] = (v, k + 1)
                w, i = adj[v][k]
                if state[w] == 1:
                    rev.add(i)
                elif state[w] == 0:
                    state[w] = 1
                    stack.append((w, 0))
            else:
                state[v] = 2
                stack.pop()
    return rev


def rank_dag(n: int, edges: list[tuple[int, int]], pull_end: set[int] = frozenset()) -> list[int]:  # type: ignore[assignment]
    """Longest-path ranks, then nodes slide toward the side with more edges (shorter edges).

    pull_end: vertices without edges that should sit on the last rank.
    """
    preds: list[list[int]] = [[] for _ in range(n)]
    succs: list[list[int]] = [[] for _ in range(n)]
    for a, b in edges:
        if a != b:
            succs[a].append(b)
            preds[b].append(a)
    indeg = [len(p) for p in preds]
    queue = deque(v for v in range(n) if indeg[v] == 0)
    topo: list[int] = []
    rank = [0] * n
    while queue:
        v = queue.popleft()
        topo.append(v)
        for w in succs[v]:
            rank[w] = max(rank[w], rank[v] + 1)
            indeg[w] -= 1
            if indeg[w] == 0:
                queue.append(w)
    for _ in range(8):
        top = max(rank, default=0)
        moved = False
        for v in topo:
            lo = max((rank[p] + 1 for p in preds[v]), default=0)
            hi = min((rank[s] - 1 for s in succs[v]), default=top)
            ins, outs = len(preds[v]), len(succs[v])
            if not ins and not outs:
                want = top if v in pull_end else rank[v]
            elif outs > ins:
                want = hi
            elif ins > outs:
                want = lo
            else:
                want = rank[v]
            if want != rank[v] and lo <= want <= hi:
                rank[v], moved = want, True
        if not moved:
            break
    low = min(rank, default=0)
    return [r - low for r in rank]


# --- ordering ----------------------------------------------------------------------------


def order(lg: LayerGraph, sweeps: int = 12) -> None:
    """Barycenter sweeps plus adjacent transposition; keeps the order with fewest crossings."""
    segs = lg.segs()
    up: list[list[tuple[int, float]]] = [[] for _ in lg.verts]
    down: list[list[tuple[int, float]]] = [[] for _ in lg.verts]
    for s in segs:
        va, vb = lg.verts[s.a], lg.verts[s.b]
        fa = _frac(lg.port(s, True), va.cw)
        fb = _frac(lg.port(s, False), vb.cw)
        up[s.b].append((s.a, fa))
        down[s.a].append((s.b, fb))
    pos = [0.0] * len(lg.verts)

    def renumber() -> None:
        for layer in lg.layers:
            for i, v in enumerate(layer):
                pos[v] = float(i)

    def bary(v: int, nbrs: list[tuple[int, float]]) -> float:
        return sum(pos[w] + f for w, f in nbrs) / len(nbrs) if nbrs else pos[v]

    renumber()
    best = [list(layer) for layer in lg.layers]
    best_x = crossings(lg, segs, pos)
    for it in range(sweeps):
        if best_x == 0:
            break
        rng = range(1, len(lg.layers)) if it % 2 == 0 else range(len(lg.layers) - 2, -1, -1)
        nb = up if it % 2 == 0 else down
        for r in rng:
            layer = lg.layers[r]
            keys = {v: (lg.verts[v].lane, bary(v, nb[v])) for v in layer}
            layer.sort(key=lambda v: keys[v])
            for i, v in enumerate(layer):
                pos[v] = float(i)
        _transpose(lg, up, down, pos)
        x = crossings(lg, segs, pos)
        if x < best_x:
            best_x, best = x, [list(layer) for layer in lg.layers]
    lg.layers = best


def _frac(port: float, cw: float) -> float:
    return max(-0.45, min(0.45, port / cw)) if cw > EPS else 0.0


def crossings(lg: LayerGraph, segs: list[Seg], pos: list[float]) -> int:
    by_rank: dict[int, list[tuple[float, float]]] = {}
    for s in segs:
        by_rank.setdefault(lg.verts[s.a].rank, []).append((pos[s.a], pos[s.b]))
    total = 0
    for pairs in by_rank.values():
        pairs.sort()
        for i in range(len(pairs)):
            a1, b1 = pairs[i]
            for j in range(i + 1, len(pairs)):
                a2, b2 = pairs[j]
                if a2 > a1 and b2 < b1:
                    total += 1
    return total


def _transpose(lg: LayerGraph, up: list, down: list, pos: list[float]) -> None:
    """Swap neighbours in a rank while that removes crossings."""

    def cost(a: int, b: int) -> int:
        c = 0
        for nb in (up, down):
            for x, _ in nb[a]:
                for y, _ in nb[b]:
                    if pos[x] > pos[y]:
                        c += 1
        return c

    for _ in range(4):
        improved = False
        for layer in lg.layers:
            for i in range(len(layer) - 1):
                a, b = layer[i], layer[i + 1]
                if lg.verts[a].lane != lg.verts[b].lane:
                    continue
                if cost(b, a) < cost(a, b):
                    layer[i], layer[i + 1] = b, a
                    pos[a], pos[b] = pos[b], pos[a]
                    improved = True
        if not improved:
            break


# --- cross coordinates --------------------------------------------------------------------


def separation(a: Vert, b: Vert) -> float:
    """Minimum center distance between neighbours a (before) and b in one rank."""
    if a.dummy and b.dummy:
        gap = LANE_GAP
    elif a.dummy or b.dummy:
        gap = DUMMY_GAP
    else:
        gap = NODE_GAP
    if a.loop:
        gap += LOOP
    return (a.cw + b.cw) / 2 + gap


def assign_cross(lg: LayerGraph, members: set[int] | None = None, iterations: int = 10) -> None:
    """Place verts across their ranks: in order, separated, as close to their neighbours as possible.

    Each rank is solved exactly (weighted least squares under ordering constraints, by
    pool-adjacent-violators) against its neighbours, sweeping down and up repeatedly.
    """
    layers = [[v for v in layer if members is None or v in members] for layer in lg.layers]
    mark_branches(lg)
    up: list[list[tuple[int, float, float]]] = [[] for _ in lg.verts]  # (nbr, weight, offset)
    down: list[list[tuple[int, float, float]]] = [[] for _ in lg.verts]
    for s in lg.segs():
        if members is not None and (s.a not in members or s.b not in members):
            continue
        va, vb = lg.verts[s.a], lg.verts[s.b]
        w = 8.0 if va.dummy and vb.dummy else 2.0 if va.dummy or vb.dummy else 1.0
        w *= lg.chains[s.chain].weight
        off = lg.port(s, True) - lg.port(s, False)
        up[s.b].append((s.a, w, off))
        down[s.a].append((s.b, w, -off))
    for layer in layers:
        x = 0.0
        for i, v in enumerate(layer):
            if i:
                x += separation(lg.verts[layer[i - 1]], lg.verts[v])
            lg.verts[v].u = x
        for v in layer:
            lg.verts[v].u -= x / 2
    n = len(layers)
    for it in range(iterations + 3):
        both = it >= iterations
        for r in range(1, n):
            _place_rank(lg, layers[r], up, down if both else None)
        for r in range(n - 2, -1, -1):
            _place_rank(lg, layers[r], down, up if both else None)


def mark_branches(lg: LayerGraph) -> None:
    """A decision's branch toward most of the remaining flow stays straight; the others go sideways."""
    succ: dict[int, list[int]] = {}
    for c in lg.chains:
        if not c.upward and not c.open_top and not c.open_bottom:
            succ.setdefault(c.verts[0], []).append(c.verts[-1])
    memo: dict[int, int] = {}

    def reach(v: int) -> int:
        if v not in memo:
            seen, stack = {v}, [v]
            while stack:
                for w in succ.get(stack.pop(), []):
                    if w not in seen:
                        seen.add(w)
                        stack.append(w)
            memo[v] = len(seen)
        return memo[v]

    for vi, vert in enumerate(lg.verts):
        if not vert.decision:
            continue
        outs = [c for c in lg.chains if c.verts[0] == vi and not c.upward and not c.open_top]
        if len(outs) < 2:
            continue
        main = max(outs, key=lambda c: 0 if c.open_bottom else reach(c.verts[-1]))
        for c in outs:
            c.weight = 4.0 if c is main else 0.5


def _place_rank(lg: LayerGraph, layer: list[int], nbrs: list, extra: list | None) -> None:
    if not layer:
        return
    verts = lg.verts
    desired, weights = [], []
    for v in layer:
        items = nbrs[v] + (extra[v] if extra is not None else [])
        tw = sum(w for _, w, _ in items)
        if tw > 0:
            desired.append(sum(w * (verts[o].u + off) for o, w, off in items) / tw)
            weights.append(tw)
        else:
            desired.append(verts[v].u)
            weights.append(0.01)
    seps = [separation(verts[layer[i]], verts[layer[i + 1]]) for i in range(len(layer) - 1)]
    for v, x in zip(layer, pav(desired, weights, seps)):
        verts[v].u = x


def pav(desired: list[float], weights: list[float], seps: list[float]) -> list[float]:
    """Minimize sum w (x - d)^2 subject to x[i+1] - x[i] >= seps[i]."""
    offs = [0.0]
    for s in seps:
        offs.append(offs[-1] + s)
    blocks: list[list[float]] = []  # [weight, weighted sum, count]
    for d, w, o in zip(desired, weights, offs):
        blocks.append([w, w * (d - o), 1])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][0] > blocks[-1][1] / blocks[-1][0]:
            w2, s2, c2 = blocks.pop()
            blocks[-1][0] += w2
            blocks[-1][1] += s2
            blocks[-1][2] += c2
    out: list[float] = []
    for w, s, c in blocks:
        out.extend([s / w] * int(c))
    return [y + o for y, o in zip(out, offs)]


# --- ports, side exits, lanes -------------------------------------------------------------


@dataclass
class _Attach:
    chain: int
    top: bool  # attached at chain.verts[0] (else verts[-1])
    anchor: float  # where the other end of this step wants the edge
    outgoing: bool  # the edge leaves this vert


def assign_ports(lg: LayerGraph, spread: bool = True) -> None:
    """Fix port offsets at node ends, decide side exits, then compute every chain's lanes."""
    verts = lg.verts
    sides: dict[tuple[int, str], list[_Attach]] = {}
    for ci, c in enumerate(lg.chains):
        for top in (True, False):
            face = c.attach_top() if top else c.attach_bottom()
            vi = c.verts[0] if top else c.verts[-1]
            if face is None or verts[vi].kind != "node" or (c.port_top if top else c.port_bottom) is not None:
                continue
            if len(c.verts) == 1:  # vert to boundary: outgoing when travel heads for the boundary
                outgoing = c.open_bottom != c.upward
            else:
                outgoing = top != c.upward  # downward travel leaves verts[0]
            sides.setdefault((vi, face), []).append(_Attach(ci, top, _anchor(lg, c, top), outgoing))
    if spread:
        _side_exits(lg, sides)
    for (vi, _), items in sides.items():
        _spread(lg, vi, items, spread)
    for c in lg.chains:
        _lanes(lg, c)


def _anchor(lg: LayerGraph, c: Chain, top: bool) -> float:
    verts = lg.verts
    if len(c.verts) == 1:
        return verts[c.verts[0]].u
    me = verts[c.verts[0] if top else c.verts[-1]]
    oi = c.verts[1] if top else c.verts[-2]
    other = verts[oi]
    if other.kind == "node" and (len(c.verts) == 2):
        lo = max(me.u - me.cw / 2, other.u - other.cw / 2) + 0.15
        hi = min(me.u + me.cw / 2, other.u + other.cw / 2) - 0.15
        if lo <= hi:  # overlapping boxes: both ends pick the same straight line
            return min(hi, max(lo, (me.u + other.u) / 2))
        return other.u
    port = c.port_bottom if top else c.port_top
    if len(c.verts) > 2 or port is None:
        port = 0.0
    return other.u + port


def _side_exits(lg: LayerGraph, sides: dict[tuple[int, str], list[_Attach]]) -> None:
    """Diamonds send secondary branches out of their side corners; back edges use the sides too."""
    verts = lg.verts
    for (vi, face), items in sides.items():
        me = verts[vi]
        half = me.cw / 2
        outs = [a for a in items if a.outgoing]
        fork = me.decision and len(outs) >= 2
        main = max(outs, key=lambda a: (lg.chains[a.chain].weight, -abs(a.anchor - me.u))) if fork else None
        chosen: dict[int, tuple[_Attach, float | None]] = {}
        for a in sorted(items, key=lambda a: abs(a.anchor - me.u)):
            c = lg.chains[a.chain]
            back = c.upward and len(c.verts) > 1 and not (c.open_top or c.open_bottom)
            d = a.anchor - me.u
            if fork and a.outgoing and a is not main:
                sign = (1 if d > 0 else -1) if abs(d) > 1e-6 else (-1 if 1 in chosen else 1)
                lane = None if abs(d) > half + 0.25 else me.u + sign * (half + 0.3)
            elif back and abs(d) > half + 0.05:
                sign, lane = (1 if d > 0 else -1), None
            else:
                continue
            reach_to = a.anchor if lane is None else lane
            if sign not in chosen and _free(lg, vi, sign, reach_to if sign * (reach_to - me.u) > 0 else me.u):
                chosen[sign] = (a, lane)
        for sign, (a, lane) in chosen.items():
            c = lg.chains[a.chain]
            if a.top:
                c.side_top, c.side_lane_top = sign, lane
            else:
                c.side_bottom, c.side_lane_bottom = sign, lane
            items.remove(a)


def _free(lg: LayerGraph, vi: int, sign: int, target: float) -> bool:
    """Nothing in vi's rank between its side and target (plus a margin)."""
    me = lg.verts[vi]
    layer = lg.layers[me.rank]
    i = layer.index(vi)
    nxt = layer[i + 1] if sign > 0 and i + 1 < len(layer) else layer[i - 1] if sign < 0 and i > 0 else None
    if nxt is None:
        return True
    o = lg.verts[nxt]
    if sign > 0:
        return o.u - o.cw / 2 > target + 0.15
    return o.u + o.cw / 2 < target - 0.15


def _spread(lg: LayerGraph, vi: int, items: list[_Attach], spread: bool) -> None:
    """Ports on one face: straight where the other end lines up, else near the center, spaced apart."""
    me = lg.verts[vi]
    if not items:
        return
    half = me.cw / 2
    m = min(0.15, half * 0.3)
    lo, hi = me.u - half + m, me.u + half - m
    if not spread or me.decision:
        for a in items:
            _set_port(lg, a, 0.0)
        return
    items.sort(key=lambda a: (a.anchor, a.chain))
    ideal, weights = [], []
    for a in items:
        if lo <= a.anchor <= hi:
            ideal.append(a.anchor)
            weights.append(10.0)
        else:
            ideal.append(max(me.u - 0.25, min(me.u + 0.25, a.anchor)))
            weights.append(1.0)
    gap = 0.22
    xs = pav(ideal, weights, [gap] * (len(items) - 1))
    if xs[-1] - xs[0] > hi - lo:
        step = (hi - lo) / (len(items) - 1) if len(items) > 1 else 0.0
        xs = [lo + i * step if len(items) > 1 else me.u for i in range(len(items))]
    elif xs[0] < lo:
        xs = [x + lo - xs[0] for x in xs]
    elif xs[-1] > hi:
        xs = [x - (xs[-1] - hi) for x in xs]
    for a, x in zip(items, xs):
        _set_port(lg, a, x - me.u)


def _set_port(lg: LayerGraph, a: _Attach, off: float) -> None:
    c = lg.chains[a.chain]
    if a.top:
        c.port_top = off
    else:
        c.port_bottom = off


def _lanes(lg: LayerGraph, c: Chain) -> None:
    verts = lg.verts
    lanes = [verts[v].u for v in c.verts]
    lanes[0] += c.port_top or 0.0
    if len(lanes) > 1:
        lanes[-1] += c.port_bottom or 0.0
    # near-equal neighbouring lanes are drawn as one straight line (dummies, or a node end)
    for i in range(1, len(lanes)):
        kind = verts[c.verts[i]].kind
        node_end = kind == "node" and i == len(lanes) - 1 and not c.open_bottom
        if abs(lanes[i] - lanes[i - 1]) < 0.06 and (kind == "dummy" or node_end):
            lanes[i] = lanes[i - 1]
    if c.side_top and len(lanes) > 1:
        lanes[0] = c.side_lane_top if c.side_lane_top is not None else lanes[1]
    if c.side_bottom and len(lanes) > 1:
        lanes[-1] = c.side_lane_bottom if c.side_lane_bottom is not None else lanes[-2]
    c.lanes = lanes


# --- rank gaps, tracks, along coordinates ---------------------------------------------------


def assign_along(lg: LayerGraph, start: float, base_gap: float, lr: bool, compact: bool = False) -> list[float]:
    """Set v for every vert and the jog positions of every chain. Returns rank band starts.

    Gaps grow for edge labels (LR: label width; TB: a text line) and for parallel jogs.
    """
    verts = lg.verts
    n = len(lg.layers)
    band = [max((verts[v].ah for v in layer), default=0.0) for layer in lg.layers]
    gaps = [base_gap] * max(0, n - 1)
    jogs: list[list[tuple[float, float, tuple, int, int, bool]]] = [[] for _ in gaps]
    for ci, c in enumerate(lg.chains):
        for i in range(len(c.verts) - 1):
            r = verts[c.verts[i]].rank
            if c.label and not compact:
                need = text_width(c.label, LABEL_PT) + 0.5 if lr else base_gap + 0.25
                gaps[r] = max(gaps[r], need)
            a, b = c.lanes[i], c.lanes[i + 1]
            if abs(a - b) > 1e-3:
                start_vert, start_lane = (c.verts[i], a) if not c.upward else (c.verts[i + 1], b)
                key = (start_vert, round(start_lane, 3))
                jogs[r].append((min(a, b), max(a, b), key, ci, i, (b > a) != c.upward))
    tracks = [_tracks(js) for js in jogs]
    for r, (count, _) in enumerate(tracks):
        gaps[r] = max(gaps[r], (count + 1) * TRACK_GAP)
    starts = []
    v = start
    for r in range(n):
        starts.append(v)
        for vi in lg.layers[r]:
            verts[vi].v = v + band[r] / 2
        v += band[r] + (gaps[r] if r < n - 1 else 0.0)
    for c in lg.chains:
        c.jogs = [0.0] * (len(c.verts) - 1)
        for i in range(len(c.verts) - 1):
            r = verts[c.verts[i]].rank
            c.jogs[i] = starts[r] + band[r] + gaps[r] / 2
    for r, (count, assign) in enumerate(tracks):
        g0 = starts[r] + band[r]
        for (ci, i), t in assign.items():
            lg.chains[ci].jogs[i] = g0 + gaps[r] * (t + 1) / (count + 1)
    return starts + [v]


def _tracks(jogs: list[tuple[float, float, tuple, int, int, bool]]) -> tuple[int, dict[tuple[int, int], int]]:
    """Give overlapping horizontal jogs in one gap separate tracks; jogs leaving one port share one.

    Rightward jogs that start further right go higher (and mirrored), which avoids crossings.
    """
    order = sorted(jogs, key=lambda j: (not j[5], -j[0] if j[5] else j[0], j[1], j[3]))
    tracks: list[list[tuple[float, float, tuple]]] = []
    assign: dict[tuple[int, int], int] = {}
    for lo, hi, key, ci, i, _ in order:
        for t, used in enumerate(tracks):
            if all(k == key for _, _, k in used):
                used.append((lo, hi, key))
                assign[(ci, i)] = t
                break
        else:
            tracks.append([(lo, hi, key)])
            assign[(ci, i)] = len(tracks) - 1
    return len(tracks), assign
