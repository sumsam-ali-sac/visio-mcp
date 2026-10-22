import pytest
from pydantic import TypeAdapter, ValidationError

from visio_mcp.spec import DiagramSpec, PatchOp


def spec(**kw):
    base = {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "a", "target": "b"}]}
    return DiagramSpec.model_validate(base | kw)


def test_minimal_spec_defaults():
    s = spec()
    assert s.layout == "flowchart-tb"
    assert s.nodes[0].kind == "process"
    assert s.edges[0].arrow == "end"


def test_duplicate_node_ids_rejected():
    with pytest.raises(ValidationError, match="duplicate node ids"):
        spec(nodes=[{"id": "a"}, {"id": "a"}], edges=[])


def test_edge_to_unknown_node_rejected():
    with pytest.raises(ValidationError, match="unknown nodes"):
        spec(edges=[{"source": "a", "target": "zzz"}])


def test_unknown_group_rejected():
    with pytest.raises(ValidationError, match="unknown group"):
        spec(nodes=[{"id": "a", "group": "g"}], edges=[])


def test_bad_color_rejected():
    with pytest.raises(ValidationError):
        spec(nodes=[{"id": "a", "fill": "blue"}], edges=[])


def test_patch_ops_discriminated():
    ops = TypeAdapter(list[PatchOp]).validate_python(
        [{"op": "update_node", "id": "a", "label": "A"}, {"op": "relayout", "layout": "radial"}]
    )
    assert [o.op for o in ops] == ["update_node", "relayout"]
