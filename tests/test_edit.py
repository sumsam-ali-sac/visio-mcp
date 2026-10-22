import pytest

from visio_mcp import catalog
from visio_mcp.catalog import Resolved, Shape
from visio_mcp.output.visio.edit import apply_ops
from visio_mcp.output.visio.inspect import inspect
from visio_mcp.output.visio.draw import render_spec
from visio_mcp.spec import (
    AddEdge,
    AddNode,
    DiagramSpec,
    Edge,
    Group,
    Move,
    Node,
    Relayout,
    Remove,
    UpdateNode,
)


@pytest.fixture(autouse=True)
def fake_catalog(monkeypatch):
    def resolve(kind, has_master):
        if kind == "mystery":
            return Resolved(Shape("BASIC_U.VSSX", "Rectangle"), "unknown kind 'mystery'")
        return Resolved(Shape("BASFLO_U.VSSX", "Process"), None)

    monkeypatch.setattr(catalog, "resolve", resolve)
    monkeypatch.setattr(catalog, "lookup", lambda kind: None)


@pytest.fixture
def drawn(fake):
    spec = DiagramSpec(
        nodes=[Node(id="a"), Node(id="b", group="g"), Node(id="c", group="g")],
        edges=[Edge(source="a", target="b", label="x"), Edge(source="a", target="b")],
        groups=[Group(id="g")],
    )
    render_spec(fake, spec)
    return fake


def test_update_node(drawn):
    result = apply_ops(drawn, [UpdateNode(id="a", label="Alpha", fill="#00FF00")])
    assert drawn.items["a"].text == "Alpha"
    assert drawn.fills["a"] == "#00FF00"
    assert result.warnings == []


def test_move(drawn):
    apply_ops(drawn, [Move(id="a", x=9, y=8)])
    assert (drawn.items["a"].x, drawn.items["a"].y) == (9, 8)


def test_relayout_needs_a_spec(drawn):
    result = apply_ops(drawn, [Relayout(layout="tree-tb")])
    assert "drawn from a spec" in result.warnings[0]


def test_remove_node_drops_its_edges(drawn):
    result = apply_ops(drawn, [Remove(id="a")])
    assert "a" not in drawn.items
    assert result.connectors == 0
    assert result.shapes == 3  # b, c, container g


def test_remove_edge_by_name(drawn):
    result = apply_ops(drawn, [Remove(id="a->b#2")])
    assert result.connectors == 1
    assert "a->b" in drawn.edges


def test_add_edge_gets_unique_name(drawn):
    result = apply_ops(drawn, [AddEdge(edge=Edge(source="b", target="c", style="dotted"))])
    assert drawn.edges["b->c"]["pattern"] == "dotted"
    assert apply_ops(drawn, [AddEdge(edge=Edge(source="a", target="b"))]).connectors == result.connectors + 1
    assert "a->b#3" in drawn.edges


def test_add_node_is_placed_clear_of_existing(drawn):
    ops = [AddNode(node=Node(id=f"n{i}", fill="#AABBCC")) for i in range(3)]
    result = apply_ops(drawn, ops)
    assert result.overlaps == []
    assert drawn.items["n0"].text == "n0"
    assert drawn.styles["n2"]["style"].fill == "#AABBCC"
    assert result.warnings == []


def test_add_node_on_empty_page_and_explicit_coordinates(fake):
    fake.new_document("t")
    apply_ops(fake, [AddNode(node=Node(id="a")), AddNode(node=Node(id="b", x=7, y=7))])
    assert (fake.items["b"].x, fake.items["b"].y) == (7, 7)
    assert apply_ops(fake, []).overlaps == []


def test_add_node_warning_from_catalog(drawn):
    result = apply_ops(drawn, [AddNode(node=Node(id="m", kind="mystery"))])
    assert result.warnings == ["unknown kind 'mystery'"]


def test_failing_op_warns_and_batch_continues(drawn):
    ops = [
        Remove(id="x"),
        Move(id="nope", x=1, y=1),
        UpdateNode(id="a", label="ok"),
        AddEdge(edge=Edge(source="a", target="ghost")),
    ]
    result = apply_ops(drawn, ops)
    assert result.warnings[0] == "op 1 (remove 'x'): no shape named 'x'"
    assert result.warnings[1].startswith("op 2 (move 'nope')")
    assert result.warnings[2].startswith("op 4 (add_edge 'a->ghost')")
    assert len(result.warnings) == 3
    assert drawn.items["a"].text == "ok"


def test_counts_reflect_backend(drawn):
    result = apply_ops(drawn, [])
    assert (result.shapes, result.connectors) == (4, 2)


def test_inspect_shape(drawn):
    drawn.items["a"].x = 1.23456
    out = inspect(drawn)

    shapes = {s["id"]: s for s in out["shapes"]}
    assert set(shapes) == {"a", "b", "c", "g"}
    assert shapes["a"]["x"] == 1.23
    assert shapes["a"]["master"] == "Process"
    assert shapes["a"]["container"] is False
    assert shapes["g"]["container"] is True
    assert set(shapes["a"]) == {"id", "text", "master", "x", "y", "width", "height", "container"}

    assert out["connectors"] == [
        {"id": "a->b", "source": "a", "target": "b", "label": "x"},
        {"id": "a->b#2", "source": "a", "target": "b", "label": ""},
    ]
    assert out["overlaps"] == []


def test_inspect_reports_overlaps(drawn):
    apply_ops(drawn, [Move(id="b", x=drawn.items["a"].x, y=drawn.items["a"].y)])
    assert inspect(drawn)["overlaps"] == [("a", "b")]
