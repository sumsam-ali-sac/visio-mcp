"""Planning and drawing through the backend (FakeVisio records every call)."""

import json
from pathlib import Path

import pytest

from visio_mcp.output.visio.backend import ShapeInfo
from visio_mcp.plan import build_plan
from visio_mcp.output.visio.draw import render_spec
from visio_mcp.output.visio.inspect import find_overlaps
from visio_mcp.spec import DiagramSpec, Edge, Group, Node

ROOT = Path(__file__).resolve().parents[1]


def box(name, x, y, w=1.0, h=1.0, **kw):
    return ShapeInfo(name, name, "Process", x, y, w, h, **kw)


SPEC = DiagramSpec(
    title="orders platform",
    subtitle="Container view",
    type="architecture",
    groups=[Group(id="core", label="core services", kind="system"), Group(id="data", kind="tier")],
    nodes=[
        Node(id="user", label="customer", kind="user"),
        Node(id="api", label="orders api", kind="api", technology="Python / FastAPI", group="core", emphasis=True),
        Node(id="bus", label="order events", kind="queue", group="core"),
        Node(id="db", label="orders db", kind="database", group="data"),
    ],
    edges=[
        Edge(source="user", target="api", label="HTTPS"),
        Edge(source="api", target="db", label="Reads From"),
        Edge(source="api", target="bus", label="publishes", style="dashed"),
    ],
)


def test_full_render_draws_everything(fake):
    result = render_spec(fake, SPEC)
    assert fake.title == "orders platform"
    assert (result.shapes, result.connectors) == (6, 3)
    assert result.overlaps == []
    # nodes are styled with rich text: cased label, then the technology line
    assert fake.items["api"].text.startswith("Orders API\n[Python / FastAPI]")
    assert fake.runs["api"][0].style.bold
    # emphasis thickens the border in the theme accent
    assert fake.styles["api"]["style"].line_weight >= 2.0
    # containers with exact bounds, members included, cased labels
    assert fake.containers["core"] == ["api", "bus"]
    assert fake.items["core"].text == "Core Services"
    assert fake.container_bounds["core"] is not None
    # connectors glued and styled; edge labels read as phrases
    assert fake.edges["api->db"]["label"] == "reads from"
    assert fake.edges["api->bus"]["pattern"] == "dashed"
    assert set(fake.edge_styles) == {"user->api", "api->db", "api->bus"}
    # page, title block and presentation
    assert fake.page["background"] == "#FFFFFF"
    assert "__title" in fake.texts
    assert fake.presented == 1


def test_containers_are_drawn_inner_first(fake):
    spec = DiagramSpec(
        nodes=[Node(id="a", group="subnet")],
        groups=[Group(id="cloud", kind="cloud"), Group(id="vnet", kind="network", parent="cloud"),
                Group(id="subnet", kind="subnet", parent="vnet")],
    )
    render_spec(fake, spec)
    order = [n for n in fake.containers]
    assert order == ["subnet", "vnet", "cloud"]
    assert fake.containers["vnet"] == ["subnet"]


def test_theme_drives_styles(fake):
    render_spec(fake, SPEC.model_copy(update={"theme": "blueprint"}))
    assert fake.page["background"] == "#0B1F3A"
    assert fake.styles["db"]["style"].fill == "#12305A"


def test_unknown_kind_warns_and_draws(fake):
    spec = DiagramSpec(nodes=[Node(id="a", kind="mystery"), Node(id="b", kind="mystery")])
    result = render_spec(fake, spec)
    assert len([w for w in result.warnings if "mystery" in w]) == 1  # deduped
    assert "a" in fake.items


def test_legend_lists_categories_and_line_styles(fake):
    render_spec(fake, SPEC)
    legend = " ".join(t["runs"][0].text for name, t in fake.texts.items() if name.startswith("__legend_"))
    assert "Synchronous call" in legend and "Asynchronous / event" in legend
    assert "__legend" in fake.boxes


def test_no_legend_when_disabled(fake):
    render_spec(fake, SPEC.model_copy(update={"legend": False}))
    assert not any(n.startswith("__legend") for n in fake.boxes)


def test_progress_messages(fake):
    seen = []
    render_spec(fake, SPEC, seen.append)
    assert any("shapes" in m for m in seen) and any("Connecting" in m for m in seen)


@pytest.mark.parametrize("path", sorted((ROOT / "examples").glob("*.json")), ids=lambda p: p.stem)
def test_examples_plan_cleanly(path):
    plan = build_plan(DiagramSpec.model_validate(json.loads(path.read_text(encoding="utf-8"))))
    rects = [n.rect for n in plan.nodes]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert abs(a.x - b.x) >= (a.w + b.w) / 2 - 1e-6 or abs(a.y - b.y) >= (a.h + b.h) / 2 - 1e-6
    for n in plan.nodes:
        assert 0 <= n.rect.left and n.rect.right <= plan.width
        assert 0 <= n.rect.bottom and n.rect.top <= plan.height
    assert not [w for w in plan.warnings if "no members" in w]


def test_find_overlaps_detects_intersection():
    shapes = [box("b", 0.5, 0), box("a", 0, 0), box("c", 10, 10)]
    assert find_overlaps(shapes) == [("a", "b")]


def test_find_overlaps_touching_does_not_count():
    assert find_overlaps([box("a", 0, 0), box("b", 1, 0), box("c", 0, 1)]) == []


def test_find_overlaps_ignores_connectors_containers_and_decorations():
    shapes = [
        box("a", 0, 0),
        box("e", 0, 0, is_connector=True),
        box("g", 0, 0, 5, 5, is_container=True),
        box("__background", 0, 0, 50, 50),
    ]
    assert find_overlaps(shapes) == []
