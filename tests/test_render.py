import pytest

from visio_mcp import catalog
from visio_mcp.backend import ShapeInfo
from visio_mcp.catalog import Resolved, Shape
from visio_mcp.render import find_overlaps, render_spec
from visio_mcp.spec import DiagramSpec, Edge, Group, Node

PROCESS = Shape("BASFLO_U.VSSX", "Process")
DECISION = Shape("BASFLO_U.VSSX", "Decision")
RECT = Shape("BASIC_U.VSSX", "Rectangle")


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    def resolve(kind, has_master):
        if kind == "decision":
            return Resolved(DECISION, "#FFF2CC", None)
        if kind == "mystery":
            return Resolved(RECT, None, "unknown kind 'mystery', used Rectangle")
        return Resolved(PROCESS, None, None)

    monkeypatch.setattr(catalog, "resolve", resolve)


def box(name, x, y, w=1.0, h=1.0, **kw):
    return ShapeInfo(name, name, "Process", x, y, w, h, **kw)


def test_full_render(fake):
    spec = DiagramSpec(
        title="Flow",
        layout="flowchart-lr",
        nodes=[
            Node(id="a", label="Start"),
            Node(id="b", kind="decision", group="g"),
            Node(id="c", group="g", fill="#112233"),
            Node(id="d", kind="mystery"),
        ],
        edges=[
            Edge(source="a", target="b", label="go", style="dashed", arrow="both"),
            Edge(source="b", target="c"),
        ],
        groups=[Group(id="g", label="Zone")],
    )
    result = render_spec(fake, spec)

    assert fake.title == "Flow"
    assert fake.layouts == ["flowchart-lr"]
    assert (result.shapes, result.connectors) == (5, 2)
    assert result.warnings == ["unknown kind 'mystery', used Rectangle"]
    assert fake.items["a"].text == "Start"
    assert fake.items["b"].text == "b"
    assert fake.items["b"].master == "Decision"
    assert fake.fills == {"b": "#FFF2CC", "c": "#112233"}
    assert fake.edges["a->b"] == dict(
        source="a", target="b", label="go", pattern="dashed", arrow="both"
    )
    assert fake.containers == {"g": ["b", "c"]}
    assert fake.items["g"].text == "Zone"
    assert result.overlaps == []


def test_group_members_are_adjacent(fake):
    spec = DiagramSpec(
        nodes=[Node(id="a", group="g"), Node(id="x"), Node(id="b", group="g")],
        groups=[Group(id="g")],
    )
    render_spec(fake, spec)
    assert list(fake.items)[:3] == ["a", "b", "x"]
    assert fake.containers["g"] == ["a", "b"]


def test_duplicate_edge_names(fake):
    spec = DiagramSpec(
        nodes=[Node(id="a"), Node(id="b")],
        edges=[Edge(source="a", target="b"), Edge(source="a", target="b"), Edge(source="a", target="b")],
    )
    result = render_spec(fake, spec)
    assert list(fake.edges) == ["a->b", "a->b#2", "a->b#3"]
    assert result.connectors == 3


def test_layout_none_uses_given_coordinates(fake):
    spec = DiagramSpec(
        layout="none",
        nodes=[Node(id="a", x=5, y=6), Node(id="b"), Node(id="c", x=1, y=1), Node(id="d")],
    )
    result = render_spec(fake, spec)
    assert (fake.items["a"].x, fake.items["a"].y) == (5, 6)
    assert (fake.items["c"].x, fake.items["c"].y) == (1, 1)
    assert fake.layouts == ["none"]
    assert result.overlaps == []  # unplaced nodes avoid the fixed ones and each other


def test_empty_group_warns_and_is_skipped(fake):
    spec = DiagramSpec(nodes=[Node(id="a")], groups=[Group(id="empty")])
    result = render_spec(fake, spec)
    assert "empty" not in fake.items
    assert result.shapes == 1
    assert any("'empty'" in w for w in result.warnings)


def test_warnings_deduped(fake):
    spec = DiagramSpec(nodes=[Node(id="a", kind="mystery"), Node(id="b", kind="mystery")])
    assert len(render_spec(fake, spec).warnings) == 1


def test_find_overlaps_detects_intersection():
    shapes = [box("b", 0.5, 0), box("a", 0, 0), box("c", 10, 10)]
    assert find_overlaps(shapes) == [("a", "b")]


def test_find_overlaps_touching_does_not_count():
    assert find_overlaps([box("a", 0, 0), box("b", 1, 0), box("c", 0, 1)]) == []


def test_find_overlaps_ignores_connectors_and_containers():
    shapes = [
        box("a", 0, 0),
        box("e", 0, 0, is_connector=True),
        box("g", 0, 0, 5, 5, is_container=True),
    ]
    assert find_overlaps(shapes) == []
