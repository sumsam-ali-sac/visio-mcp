"""The diagram spec: what an agent sends to describe a diagram by meaning, not geometry."""

from visio_mcp.spec.diagram import (
    Arrow,
    DiagramSpec,
    DiagramType,
    Edge,
    Group,
    GroupKind,
    HexColor,
    Layout,
    LineStyle,
    Node,
    edge_name,
)
from visio_mcp.spec.patch import (
    AddEdge,
    AddGroup,
    AddNode,
    Move,
    PatchOp,
    Relayout,
    Remove,
    UpdateDiagram,
    UpdateEdge,
    UpdateNode,
)
from visio_mcp.spec.result import RenderResult

__all__ = [
    "AddEdge",
    "AddGroup",
    "AddNode",
    "Arrow",
    "DiagramSpec",
    "DiagramType",
    "Edge",
    "Group",
    "GroupKind",
    "HexColor",
    "Layout",
    "LineStyle",
    "Move",
    "Node",
    "PatchOp",
    "Relayout",
    "Remove",
    "RenderResult",
    "UpdateDiagram",
    "UpdateEdge",
    "UpdateNode",
    "edge_name",
]
