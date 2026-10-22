"""The diagram spec: what an agent sends to describe a diagram by meaning, not geometry."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Layout = Literal[
    "auto",  # pick from the diagram type (default)
    "flowchart-tb",  # layered, top to bottom
    "flowchart-lr",  # layered, left to right
    "tree-tb",  # hierarchy, root on top (org charts)
    "tree-lr",  # hierarchy, root on the left
    "swimlane-lr",  # groups are horizontal lanes, flow runs left to right
    "swimlane-tb",  # groups are vertical lanes, flow runs top to bottom
    "radial",  # hub and spokes
    "circular",  # ring
    "grid",  # tidy grid, no flow direction (inventories, catalogs)
    "compact",  # alias of grid, kept for older specs
    "none",  # keep given x/y, no auto-layout
]

DiagramType = Literal[
    "auto",  # infer from the node kinds
    "flowchart",  # process with decisions
    "architecture",  # software components and data flow
    "cloud",  # cloud provider architecture (Azure, AWS, GCP icons)
    "c4-context",  # C4 level 1: system, people, external systems
    "c4-container",  # C4 level 2: apps, services, stores inside one system
    "deployment",  # hosts, clusters, networks
    "network",  # routers, switches, firewalls, subnets
    "dataflow",  # data sources, transforms, sinks
    "pipeline",  # CI/CD or ETL stages
    "erd",  # entities and relationships
    "org",  # org chart
    "swimlane",  # cross-functional process with lanes
    "state",  # state machine
    "mindmap",  # central idea and branches
]

GroupKind = Literal[
    "generic",
    "tier",  # presentation / services / data
    "system",  # a software system boundary (C4)
    "boundary",  # trust boundary
    "cloud",  # cloud account / subscription
    "region",  # cloud region
    "zone",  # availability zone
    "network",  # VNet / VPC
    "subnet",
    "cluster",  # Kubernetes / compute cluster
    "environment",  # dev / staging / prod
    "lane",  # swimlane (actor or department)
    "external",  # things outside your control
]

LineStyle = Literal["solid", "dashed", "dotted"]
Arrow = Literal["end", "both", "none"]
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class Node(BaseModel):
    id: str = Field(description="Unique id, referenced by edges. Short, no spaces, e.g. 'api'.")
    label: str = Field("", description="Text shown on the shape. Defaults to the id. At most ~4 words.")
    kind: str = Field(
        "process",
        description="Semantic shape kind, e.g. service, database, queue, user, decision, "
        "azure-functions, aws-lambda. Call list_kinds for the full list.",
    )
    group: str | None = Field(None, description="Id of the innermost group (container) this node sits in.")
    technology: str = Field("", description="Tech in brackets under the label, e.g. 'Python / FastAPI'.")
    description: str = Field("", description="One short sentence shown in small text. Optional.")
    emphasis: bool = Field(False, description="Highlight this node (accent border).")
    fill: HexColor | None = Field(None, description="Override fill color, e.g. '#DCEBFF'. Prefer themes.")
    x: float | None = Field(None, description="Inches from left. Only used when layout is 'none'.")
    y: float | None = Field(None, description="Inches from bottom. Only used when layout is 'none'.")


class Edge(BaseModel):
    source: str = Field(description="Id of the node the edge starts at.")
    target: str = Field(description="Id of the node the edge points to.")
    label: str = Field("", description="Verb or protocol, e.g. 'HTTPS', 'reads', 'yes'. Short.")
    style: LineStyle = Field("solid", description="solid = sync call, dashed = async/event, dotted = optional.")
    arrow: Arrow = "end"
    color: HexColor | None = Field(None, description="Override line color. Prefer themes.")


class Group(BaseModel):
    id: str
    label: str = ""
    kind: GroupKind = Field("generic", description="What the container means; drives its styling.")
    parent: str | None = Field(None, description="Id of the enclosing group, for nesting (region > vnet > subnet).")
    fill: HexColor | None = None


class DiagramSpec(BaseModel):
    title: str = "Diagram"
    subtitle: str = Field("", description="One line under the title: scope, audience or version.")
    type: DiagramType = Field("auto", description="What kind of diagram this is; drives rules and defaults.")
    layout: Layout = "auto"
    theme: str = Field("auto", description="Visual theme; call list_themes. 'auto' picks one from the type.")
    legend: bool = Field(True, description="Draw a legend of the shapes and line styles used.")
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = []
    groups: list[Group] = []

    @model_validator(mode="after")
    def _check_refs(self) -> DiagramSpec:
        ids = [n.id for n in self.nodes]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate node ids: {sorted(dupes)}")
        gids = [g.id for g in self.groups]
        if gdupes := {i for i in gids if gids.count(i) > 1}:
            raise ValueError(f"duplicate group ids: {sorted(gdupes)}")
        node_ids = set(ids)
        group_ids = set(gids)
        if clash := node_ids & group_ids:
            raise ValueError(f"ids used for both a node and a group: {sorted(clash)}")
        for e in self.edges:
            missing = {e.source, e.target} - node_ids
            if missing:
                raise ValueError(f"edge {e.source}->{e.target} refers to unknown nodes: {sorted(missing)}")
        for n in self.nodes:
            if n.group and n.group not in group_ids:
                raise ValueError(f"node {n.id!r} is in unknown group {n.group!r}")
        parents = {g.id: g.parent for g in self.groups}
        for g in self.groups:
            if g.parent and g.parent not in group_ids:
                raise ValueError(f"group {g.id!r} has unknown parent {g.parent!r}")
            seen, cur = {g.id}, g.parent
            while cur:
                if cur in seen:
                    raise ValueError(f"group nesting loops through {g.id!r}")
                seen.add(cur)
                cur = parents.get(cur)
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
    suggestions: list[str] = Field(
        [], description="Diagramming-rule findings (lint). Fix them with patch_diagram or a re-render."
    )
    overlaps: list[tuple[str, str]] = Field(
        [], description="Pairs of node ids whose shapes overlap. Should be empty."
    )
    files: list[str] = Field([], description="Absolute paths written (vsdx and exports).")
