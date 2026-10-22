"""Patch operations: small edits to the open diagram, addressed by node/group id."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from visio_mcp.spec.diagram import Arrow, Edge, Group, HexColor, Layout, LineStyle, Node


class AddNode(BaseModel):
    op: Literal["add_node"] = "add_node"
    node: Node


class UpdateNode(BaseModel):
    op: Literal["update_node"] = "update_node"
    id: str
    label: str | None = None
    kind: str | None = None
    group: str | None = Field(None, description="Move into this group; '' takes it out of any group.")
    technology: str | None = None
    description: str | None = None
    emphasis: bool | None = None
    fill: HexColor | None = None


class UpdateEdge(BaseModel):
    op: Literal["update_edge"] = "update_edge"
    id: str = Field(description="Edge id 'source->target' (or 'source->target#2' for a repeat).")
    label: str | None = None
    style: LineStyle | None = None
    arrow: Arrow | None = None
    color: HexColor | None = None


class AddGroup(BaseModel):
    op: Literal["add_group"] = "add_group"
    group: Group
    members: list[str] = Field([], description="Node ids to move into the new group.")


class UpdateDiagram(BaseModel):
    op: Literal["update_diagram"] = "update_diagram"
    title: str | None = None
    subtitle: str | None = None
    theme: str | None = None
    layout: Layout | None = None
    legend: bool | None = None


class Remove(BaseModel):
    op: Literal["remove"] = "remove"
    id: str = Field(description="Node, group or edge id ('source->target') to delete.")


class AddEdge(BaseModel):
    op: Literal["add_edge"] = "add_edge"
    edge: Edge


class Move(BaseModel):
    op: Literal["move"] = "move"
    id: str
    x: float
    y: float


class Relayout(BaseModel):
    op: Literal["relayout"] = "relayout"
    layout: Layout


PatchOp = Annotated[
    AddNode | UpdateNode | UpdateEdge | AddGroup | UpdateDiagram | Remove | AddEdge | Move | Relayout,
    Field(discriminator="op"),
]
