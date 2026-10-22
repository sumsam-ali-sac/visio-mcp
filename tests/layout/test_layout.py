"""Auto-layout invariants: no overlaps, tidy groups, clean routes, every preset, every example."""

from __future__ import annotations

import itertools
import random
import time
from pathlib import Path

import pytest

from visio_mcp import lint
from visio_mcp.layout import LayoutResult, Rect, compute_layout
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GroupStyle, NodeSize, get_theme

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))
PRESETS = ["flowchart-tb", "flowchart-lr", "tree-tb", "tree-lr", "swimlane-lr", "swimlane-tb",
           "radial", "circular", "grid", "none"]
LAYERED = {"flowchart-tb", "flowchart-lr", "tree-tb", "tree-lr", "swimlane-lr", "swimlane-tb"}
EPS = 1e-3


# --- fixtures --------------------------------------------------------------------------------


def _spec(nodes, edges=(), groups=(), layout="flowchart-tb") -> DiagramSpec:
    return DiagramSpec.model_validate({
        "nodes": [n if isinstance(n, dict) else {"id": n} for n in nodes],
        "edges": [e if isinstance(e, dict) else {"source": e[0], "target": e[1]} for e in edges],
        "groups": list(groups), "layout": layout,
    })


def _dag20() -> DiagramSpec:
    rnd = random.Random(7)
    nodes = [f"n{i}" for i in range(20)]
    edges = {(f"n{rnd.randrange(i)}", f"n{i}") for i in range(1, 20)}
    edges |= {(f"n{a}", f"n{b}") for a, b in ((rnd.randrange(10), rnd.randrange(10, 20)) for _ in range(8))}
    return _spec(nodes, sorted(edges))


GRAPHS = {
    "chain": _spec("abc", [("a", "b"), ("b", "c")]),
    "diamond": _spec([{"id": "s"}, {"id": "d", "kind": "decision"}, {"id": "y"}, {"id": "n"}, {"id": "e"}],
                     [("s", "d"), {"source": "d", "target": "y", "label": "yes"},
                      {"source": "d", "target": "n", "label": "no"}, ("y", "e"), ("n", "e")]),
    "dag20": _dag20(),
    "cycle": _spec("abcde", [("a", "b"), ("b", "c"), ("c", "d"), ("d", "b"), ("d", "e"), ("e", "e")]),
    "nested": _spec(
        [{"id": "u"}, {"id": "a", "group": "g1"}, {"id": "b", "group": "g2"}, {"id": "c", "group": "g3"},
         {"id": "d", "group": "g3"}, {"id": "e", "group": "g2"}, {"id": "f", "group": "k"}, {"id": "x"}],
        [("u", "a"), ("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("u", "f"), ("a", "x"), ("c", "f")],
        [{"id": "g1", "label": "Outer"}, {"id": "g2", "parent": "g1", "label": "Middle"},
         {"id": "g3", "parent": "g2", "label": "Inner"}, {"id": "k", "label": "Other"},
         {"id": "only_groups", "label": "Wrapper"}, {"id": "empty", "parent": "only_groups"}],
    ),
}
for path in EXAMPLES:
    GRAPHS[path.stem] = DiagramSpec.model_validate_json(path.read_text(encoding="utf-8"))


def _prepare(spec: DiagramSpec) -> tuple[DiagramSpec, dict[str, NodeSize], dict[str, GroupStyle]]:
    spec, _ = lint.normalize(spec)
    theme = get_theme("professional")
    sizes = {}
    for n in spec.nodes:  # simple deterministic footprints of varied size
        w = 1.4 + 0.1 * (len(n.label) % 6)
        h = 1.0 if n.kind == "decision" else 0.75 + 0.1 * (len(n.id) % 3)
        sizes[n.id] = NodeSize(w, h, w, h)
    styles = {g.id: theme.group_style(g.kind) for g in spec.groups}
    return spec, sizes, styles


def _layout(name: str, preset: str) -> tuple[DiagramSpec, LayoutResult, dict[str, NodeSize], dict[str, GroupStyle]]:
    spec, sizes, styles = _prepare(GRAPHS[name])
    return spec, compute_layout(spec, sizes, styles, preset), sizes, styles


def _overlap(a: Rect, b: Rect) -> bool:
    return a.left < b.right - EPS and b.left < a.right - EPS and a.bottom < b.top - EPS and b.bottom < a.top - EPS


def _inside(inner: Rect, outer: Rect, pad: float = 0.0) -> bool:
    return (inner.left >= outer.left + pad - EPS and inner.right <= outer.right - pad + EPS
            and inner.bottom >= outer.bottom + pad - EPS and inner.top <= outer.top - pad + EPS)


def _ancestors(spec: DiagramSpec, gid: str | None) -> list[str]:
    parents = {g.id: g.parent for g in spec.groups}
    out = []
    while gid:
        out.append(gid)
        gid = parents.get(gid)
    return out


CASES = [(g, p) for g in GRAPHS for p in PRESETS]


# --- geometry invariants -----------------------------------------------------------------------


@pytest.mark.parametrize(("graph", "preset"), CASES)
def test_nodes_never_overlap(graph: str, preset: str):
    _, r, sizes, _ = _layout(graph, preset)
    ids = list(r.nodes)
    for i, a in enumerate(ids):
        assert (r.nodes[a].w, r.nodes[a].h) == (sizes[a].w, sizes[a].h)
        for b in ids[i + 1:]:
            assert not _overlap(r.nodes[a], r.nodes[b]), f"{a} overlaps {b}"


@pytest.mark.parametrize(("graph", "preset"), CASES)
def test_everything_within_extent(graph: str, preset: str):
    _, r, _, _ = _layout(graph, preset)
    rects = list(r.nodes.values()) + list(r.groups.values())
    pts = [p for route in r.routes.values() for p in route]
    assert min([x.left for x in rects] + [p[0] for p in pts]) >= -EPS
    assert min([x.bottom for x in rects] + [p[1] for p in pts]) >= -EPS
    assert max([x.right for x in rects] + [p[0] for p in pts]) <= r.width + EPS
    assert max([x.top for x in rects] + [p[1] for p in pts]) <= r.height + EPS


@pytest.mark.parametrize(("graph", "preset"), [c for c in CASES if c[1] != "none"])
def test_groups_are_tidy(graph: str, preset: str):
    spec, r, _, styles = _layout(graph, preset)
    live = {g for n in spec.nodes for g in _ancestors(spec, n.group)}
    assert set(r.groups) == live  # groups holding only child groups too; empty ones are dropped
    for n in spec.nodes:
        mine = _ancestors(spec, n.group)
        for gid, frame in r.groups.items():
            if gid in mine:
                st = styles[gid]
                assert _inside(r.nodes[n.id], frame, st.padding - 1e-6), f"{n.id} not inside {gid}"
            else:
                assert not _overlap(r.nodes[n.id], frame), f"{n.id} intrudes into {gid}"
    gids = list(r.groups)
    for i, a in enumerate(gids):
        parent = next(g.parent for g in spec.groups if g.id == a)
        if parent:
            assert _inside(r.groups[a], r.groups[parent]), f"{a} sticks out of {parent}"
        for b in gids[i + 1:]:
            if a in _ancestors(spec, b) or b in _ancestors(spec, a):
                continue
            assert not _overlap(r.groups[a], r.groups[b]), f"groups {a} and {b} overlap"


@pytest.mark.parametrize(("graph", "preset"), CASES)
def test_routes_start_and_end_on_borders(graph: str, preset: str):
    spec, r, _, _ = _layout(graph, preset)
    assert set(r.routes) == set(range(len(spec.edges)))
    for i, e in enumerate(spec.edges):
        pts = r.routes[i]
        assert len(pts) >= 2
        assert _on_border(pts[0], r.nodes[e.source]), (e.source, pts)
        assert _on_border(pts[-1], r.nodes[e.target]), (e.target, pts)
        if preset in LAYERED or preset in ("grid", "none") or e.source == e.target:
            for (x1, y1), (x2, y2) in itertools.pairwise(pts):
                assert abs(x1 - x2) < EPS or abs(y1 - y2) < EPS, f"diagonal segment in {e.source}->{e.target}"


def _on_border(p: tuple[float, float], r: Rect) -> bool:
    x, y = p
    within = r.left - EPS <= x <= r.right + EPS and r.bottom - EPS <= y <= r.top + EPS
    edge = min(abs(x - r.left), abs(x - r.right), abs(y - r.bottom), abs(y - r.top)) < 2 * EPS
    return within and edge


@pytest.mark.parametrize("preset", PRESETS)
def test_deterministic(preset: str):
    spec, sizes, styles = _prepare(GRAPHS["web-architecture"])
    assert compute_layout(spec, sizes, styles, preset) == compute_layout(spec, sizes, styles, preset)


# --- layered quality ---------------------------------------------------------------------------


def test_chain_is_straight_top_to_bottom():
    _, r, _, _ = _layout("chain", "flowchart-tb")
    a, b, c = r.nodes["a"], r.nodes["b"], r.nodes["c"]
    assert a.x == pytest.approx(b.x) == pytest.approx(c.x)
    assert a.y > b.y > c.y  # rank 0 on top
    assert all(len(r.routes[i]) == 2 for i in range(2))  # straight lines
    assert r.direction == "tb"


def test_chain_is_straight_left_to_right():
    _, r, _, _ = _layout("chain", "flowchart-lr")
    a, b, c = r.nodes["a"], r.nodes["b"], r.nodes["c"]
    assert a.y == pytest.approx(b.y) == pytest.approx(c.y)
    assert a.x < b.x < c.x
    assert r.direction == "lr"


def test_rank_gap_and_labels():
    _, r, _, _ = _layout("diamond", "flowchart-tb")
    gap = r.nodes["s"].bottom - r.nodes["d"].top
    assert gap == pytest.approx(0.9, abs=0.05)
    assert r.nodes["d"].bottom - max(r.nodes["y"].top, r.nodes["n"].top) > gap  # labelled edges get room


def test_decision_branches_leave_from_corners():
    _, r, _, _ = _layout("diamond", "flowchart-tb")
    d = r.nodes["d"]
    starts = [r.routes[i][0] for i in (1, 2)]
    on_corner = [abs(y - d.y) < EPS and min(abs(x - d.left), abs(x - d.right)) < EPS for x, y in starts]
    on_bottom = [abs(x - d.x) < EPS and abs(y - d.bottom) < EPS for x, y in starts]
    assert sum(on_corner) + sum(on_bottom) == 2 and sum(on_corner) >= 1


def test_ranks_share_center_lines():
    _, r, _, _ = _layout("dag20", "flowchart-tb")
    ys = sorted({round(n.y, 3) for n in r.nodes.values()})
    for n in r.nodes.values():
        assert round(n.y, 3) in ys
    assert len(ys) < len(r.nodes)  # several nodes per rank, on one line


def test_single_parent_sits_over_its_children():
    _, r, _, _ = _layout("org-chart", "tree-tb")
    kids = [r.nodes[k].x for k in ("vp_plat", "vp_prod")]
    assert r.nodes["cto"].x == pytest.approx(sum(kids) / 2)
    assert r.nodes["mgr_data"].x == pytest.approx(r.nodes["de1"].x)


def test_tiers_flow_left_to_right():
    _, r, _, _ = _layout("web-architecture", "flowchart-lr")
    g = r.groups
    assert r.nodes["user"].right < g["edge"].left
    assert g["edge"].right < g["app"].left < g["app"].right < g["data"].left
    data = sorted(r.nodes[n].y for n in ("cache", "db", "blob"))
    assert len({round(r.nodes[n].x, 3) for n in ("cache", "db", "blob")}) == 1  # stacked, not a row
    assert data[0] < data[1] < data[2]


def test_back_edge_goes_against_the_flow():
    spec, r, _, _ = _layout("cycle", "flowchart-tb")
    i = next(i for i, e in enumerate(spec.edges) if (e.source, e.target) == ("d", "b"))
    assert r.nodes["d"].y < r.nodes["b"].y
    pts = r.routes[i]
    assert pts[-1][1] <= r.nodes["b"].y + EPS  # enters b from below or the side, not the top


def test_self_loop_on_the_right():
    spec, r, _, _ = _layout("cycle", "flowchart-tb")
    i = next(i for i, e in enumerate(spec.edges) if e.source == e.target)
    e = r.nodes["e"]
    assert all(x >= e.right - EPS for x, _ in r.routes[i])
    assert max(x for x, _ in r.routes[i]) > e.right


# --- swimlanes ----------------------------------------------------------------------------------


@pytest.mark.parametrize("preset", ["swimlane-lr", "swimlane-tb"])
def test_lanes_span_and_stack(preset: str):
    spec, r, _, _ = _layout("refund-swimlane", preset)
    lanes = [r.groups[g.id] for g in spec.groups]
    lr = preset.endswith("lr")
    assert r.lane_header == ("left" if lr else "top")
    if lr:  # horizontal bands, first lane on top, touching
        assert len({(round(x.left, 4), round(x.w, 4)) for x in lanes}) == 1
        for upper, lower in itertools.pairwise(lanes):
            assert upper.bottom == pytest.approx(lower.top)
    else:
        assert len({(round(x.top, 4), round(x.h, 4)) for x in lanes}) == 1
        for left, right in itertools.pairwise(lanes):
            assert left.right == pytest.approx(right.left)


def test_lanes_share_ranks():
    _, r, _, styles = _layout("refund-swimlane", "swimlane-lr")
    assert r.nodes["valid"].right < r.nodes["approve"].left
    assert r.nodes["approve"].x == pytest.approx(r.nodes["reject"].x)  # same rank, other lane
    header = styles["customer"].header_height
    assert min(n.left for n in r.nodes.values()) >= r.groups["customer"].left + header


# --- other presets ------------------------------------------------------------------------------


def test_radial_hub_in_the_middle():
    spokes = _spec(["hub", "a", "b", "c", "d", "e"], [("hub", x) for x in "abcde"], layout="radial")
    spec, sizes, styles = _prepare(spokes)
    r = compute_layout(spec, sizes, styles, "radial")
    hub = r.nodes["hub"]
    assert hub.x == pytest.approx(r.width / 2, abs=0.5)
    assert r.direction == "none"


def test_none_keeps_given_positions():
    spec, sizes, styles = _prepare(_spec([{"id": "a", "x": 5, "y": 6}, "b", {"id": "c", "x": 1, "y": 1}, "d"],
                                         layout="none"))
    r = compute_layout(spec, sizes, styles, "none")
    assert (r.nodes["a"].x, r.nodes["a"].y) == (5, 6)
    assert (r.nodes["c"].x, r.nodes["c"].y) == (1, 1)


def test_large_graph_is_fast():
    rnd = random.Random(3)
    groups = [{"id": f"g{i}"} for i in range(5)] + [{"id": f"h{i}", "parent": f"g{i}"} for i in range(3)]
    gids = [None, "g0", "g1", "g2", "g3", "g4", "h0", "h1", "h2"]
    nodes = [{"id": f"n{i}", "group": rnd.choice(gids)} for i in range(150)]
    edges = [(f"n{rnd.randrange(max(0, i - 15), i)}", f"n{i}") for i in range(1, 150)]
    edges += [(f"n{rnd.randrange(150)}", f"n{rnd.randrange(150)}") for _ in range(30)]
    spec, sizes, styles = _prepare(_spec(nodes, edges, groups))
    for preset in ("flowchart-tb", "flowchart-lr", "grid"):
        t = time.perf_counter()
        compute_layout(spec, sizes, styles, preset)
        assert time.perf_counter() - t < 1.0, preset  # ~0.2s here; slack for slow CI machines
