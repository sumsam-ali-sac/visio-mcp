"""The diagram spec: what an agent sends to describe a diagram by meaning, not geometry."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Layout = Literal[
    "flowchart-tb",  # top to bottom flow (default)
    "flowchart-lr",  # left to right flow
    "tree-tb",  # hierarchy, root on top (org charts)
    "tree-lr",  # hierarchy, root on the left
    "radial",  # hub and spokes
    "circular",  # ring
    "compact",  # dense grid-like packing
    "none",  # keep given x/y, no auto-layout
]

LineStyle = Literal["solid", "dashed", "dotted"]
Arrow = Literal["end", "both", "none"]
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class Node(BaseModel):
    id: str = Field(description="Unique id, referenced by edges. Short, no spaces, e.g. 'api'.")
    label: str = Field("", description="Text shown on the shape. Defaults to the id.")
    kind: str = Field(
        "process",
        description="Semantic shape kind, e.g. service, database, queue, user, decision. "
        "Call list_kinds for the full list.",
    )
    group: str | None = Field(None, description="Id of the group (container) this node sits in.")
    fill: HexColor | None = Field(None, description="Override fill color, e.g. '#DCEBFF'.")
    x: float | None = Field(None, description="Inches from left. Only used when layout is 'none'.")
    y: float | None = Field(None, description="Inches from bottom. Only used when layout is 'none'.")


class Edge(BaseModel):
    source: str = Field(description="Id of the node the edge starts at.")
    target: str = Field(description="Id of the node the edge points to.")
    label: str = ""
    style: LineStyle = "solid"
    arrow: Arrow = "end"


class Group(BaseModel):
    id: str
    label: str = ""


class DiagramSpec(BaseModel):
    title: str = "Diagram"
    layout: Layout = "flowchart-tb"
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = []
    groups: list[Group] = []

    @model_validator(mode="after")
    def _check_refs(self) -> DiagramSpec:
        ids = [n.id for n in self.nodes]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate node ids: {sorted(dupes)}")
        node_ids = set(ids)
        group_ids = {g.id for g in self.groups}
        if clash := node_ids & group_ids:
            raise ValueError(f"ids used for both a node and a group: {sorted(clash)}")
        for e in self.edges:
            missing = {e.source, e.target} - node_ids
            if missing:
                raise ValueError(f"edge {e.source}->{e.target} refers to unknown nodes: {sorted(missing)}")
        for n in self.nodes:
            if n.group and n.group not in group_ids:
                raise ValueError(f"node {n.id!r} is in unknown group {n.group!r}")
        return self


# Patch operations: small edits to the open diagram, addressed by node/group id.


class AddNode(BaseModel):
    op: Literal["add_node"] = "add_node"
    node: Node


class UpdateNode(BaseModel):
    op: Literal["update_node"] = "update_node"
    id: str
    label: str | None = None
    fill: HexColor | None = None


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
    AddNode | UpdateNode | Remove | AddEdge | Move | Relayout, Field(discriminator="op")
]


class RenderResult(BaseModel):
    """What render and patch report back to the agent."""

    shapes: int
    connectors: int
    warnings: list[str] = []
    overlaps: list[tuple[str, str]] = Field(
        [], description="Pairs of node ids whose shapes overlap. Should be empty."
    )
    files: list[str] = Field([], description="Absolute paths written (vsdx and exports).")
