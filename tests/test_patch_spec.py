"""Patching a diagram drawn from a spec edits the spec (then it is re-rendered)."""

from visio_mcp.spec.edit import apply_to_spec
from visio_mcp.spec import (
    AddEdge,
    AddGroup,
    AddNode,
    DiagramSpec,
    Edge,
    Group,
    Move,
    Node,
    Relayout,
    Remove,
    UpdateDiagram,
    UpdateEdge,
    UpdateNode,
)

SPEC = DiagramSpec(
    title="Shop",
    nodes=[Node(id="a"), Node(id="b", group="g"), Node(id="c", group="inner")],
    edges=[Edge(source="a", target="b"), Edge(source="a", target="b", label="two"), Edge(source="b", target="c")],
    groups=[Group(id="g"), Group(id="inner", parent="g")],
)


def test_update_node_fields():
    spec, moves, warnings = apply_to_spec(SPEC, [
        UpdateNode(id="a", label="Alpha", kind="database", technology="PostgreSQL", emphasis=True, group="g"),
    ])
    a = spec.nodes[0]
    assert (a.label, a.kind, a.technology, a.emphasis, a.group) == ("Alpha", "database", "PostgreSQL", True, "g")
    assert moves == [] and warnings == []


def test_update_node_ungroup_with_empty_string():
    spec, _, _ = apply_to_spec(SPEC, [UpdateNode(id="b", group="")])
    assert spec.nodes[1].group is None


def test_update_repeated_edge_by_suffix():
    spec, _, warnings = apply_to_spec(SPEC, [UpdateEdge(id="a->b#2", label="changed", style="dashed")])
    assert warnings == []
    assert (spec.edges[0].label, spec.edges[1].label, spec.edges[1].style) == ("", "changed", "dashed")


def test_bad_ops_become_warnings_and_others_apply():
    spec, _, warnings = apply_to_spec(SPEC, [
        AddEdge(edge=Edge(source="a", target="zz")),
        UpdateNode(id="nope", label="x"),
        UpdateNode(id="a", label="Kept"),
    ])
    assert spec.nodes[0].label == "Kept"
    assert len(warnings) == 2
    assert "op 1" in warnings[0] and "unknown nodes" in warnings[0]
    assert "op 2" in warnings[1] and "nope" in warnings[1]


def test_remove_node_drops_edges():
    spec, _, _ = apply_to_spec(SPEC, [Remove(id="b")])
    assert [n.id for n in spec.nodes] == ["a", "c"]
    assert spec.edges == []


def test_remove_group_moves_members_up():
    spec, _, _ = apply_to_spec(SPEC, [Remove(id="inner")])
    assert [g.id for g in spec.groups] == ["g"]
    assert spec.nodes[2].group == "g"


def test_remove_edge():
    spec, _, _ = apply_to_spec(SPEC, [Remove(id="a->b")])
    assert [(e.source, e.target, e.label) for e in spec.edges] == [("a", "b", "two"), ("b", "c", "")]


def test_add_group_with_members_and_diagram_update():
    spec, _, warnings = apply_to_spec(SPEC, [
        AddNode(node=Node(id="d")),
        AddGroup(group=Group(id="data", label="Data", kind="tier"), members=["a", "d"]),
        UpdateDiagram(title="New", theme="azure", layout="flowchart-lr", legend=False),
        Relayout(layout="grid"),
    ])
    assert warnings == []
    assert {n.id: n.group for n in spec.nodes}["d"] == "data"
    assert (spec.title, spec.theme, spec.layout, spec.legend) == ("New", "azure", "grid", False)


def test_moves_are_returned_for_after_render():
    _, moves, _ = apply_to_spec(SPEC, [Move(id="a", x=1, y=2)])
    assert moves == [Move(id="a", x=1, y=2)]


def test_original_spec_untouched():
    apply_to_spec(SPEC, [UpdateNode(id="a", label="Changed"), Remove(id="b")])
    assert SPEC.nodes[0].label == "" and len(SPEC.nodes) == 3
