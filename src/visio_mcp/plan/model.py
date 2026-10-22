"""Plan dataclasses: the resolved geometry, styles and text every emitter draws."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from visio_mcp.catalog import Shape
from visio_mcp.layout import Point, Rect
from visio_mcp.output.visio.backend import TextRun
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import EdgeStyle, GroupStyle, ShapeStyle, Theme


@dataclass
class PlannedNode:
    id: str
    kind: str  # resolved kind name ('box' when unknown)
    category: str
    geometry: str  # how non-Visio renderers draw it (style.GEOMETRY_MIN key)
    label: str  # final, cased
    runs: list[TextRun]  # label + [technology] + description, styled
    rect: Rect  # footprint reserved by layout (icon + label for icons)
    shape: Rect  # where the actual shape sits
    style: ShapeStyle
    icon: bool  # Visio master is an icon: keep its colors, label below
    master: Shape | None  # Visio stencil master (None when planned without Visio)
    glyph: str = ""
    provider: str | None = None
    emphasis: bool = False
    image: Path | None = None  # official cloud icon or a custom icon (svg/png) drawn instead of the glyph tile


@dataclass
class PlannedGroup:
    id: str
    label: str
    kind: str
    rect: Rect
    style: GroupStyle
    depth: int  # 0 = top level
    parent: str | None
    members: list[str]  # direct member node ids and child group ids


@dataclass
class PlannedEdge:
    name: str  # 'source->target' (+ '#n' for repeats): the Visio shape name
    source: str
    target: str
    label: str
    pattern: Literal["solid", "dashed", "dotted"]
    arrow: Literal["end", "both", "none"]
    color: str
    style: EdgeStyle
    points: list[Point]  # orthogonal polyline, first/last on the shape borders


@dataclass
class LegendEntry:
    label: str
    sample: Literal["node", "edge", "group"]
    style: ShapeStyle | None = None  # node / group swatch
    geometry: str = "rect"
    pattern: Literal["solid", "dashed", "dotted"] = "solid"
    color: str | None = None  # edge sample


@dataclass
class TextBlock:
    rect: Rect
    runs: list[TextRun]
    align: Literal["left", "center", "right"] = "left"


@dataclass
class DiagramPlan:
    spec: DiagramSpec  # normalized spec (type, layout, theme resolved; labels cased)
    theme: Theme
    width: float  # page size, inches
    height: float
    nodes: list[PlannedNode]
    groups: list[PlannedGroup]  # parents before children
    edges: list[PlannedEdge]
    title: TextBlock | None = None
    legend: Rect | None = None
    legend_title: TextBlock | None = None
    legend_entries: list[tuple[Rect, Rect, LegendEntry]] = field(default_factory=list)  # (sample, text) rects
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # what normalize filled in (informational)

    def node(self, nid: str) -> PlannedNode:
        return next(n for n in self.nodes if n.id == nid)
