"""Style dataclasses: text, shape, group, edge and the Theme that bundles them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

LinePattern = Literal["solid", "dashed", "dotted"]

# Node categories (catalog.Kind.category). Each theme styles every one of them.
CATEGORIES = (
    "terminal",  # start / end
    "flow",  # process steps
    "decision",
    "data",  # databases, storage, caches
    "compute",  # services, apps, functions, servers
    "integration",  # queues, buses, gateways, APIs
    "client",  # browsers, mobile, desktop
    "person",  # users, actors
    "external",  # third-party systems
    "network",  # routers, switches, firewalls, load balancers
    "security",  # identity, key vaults, firewalls
    "org",  # org chart positions
    "entity",  # ERD tables
    "note",
    "generic",
)


@dataclass(frozen=True)
class TextStyle:
    font: str = "Segoe UI"
    size: float = 10.0  # points
    color: str = "#1F2937"
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class ShapeStyle:
    fill: str | None = "#FFFFFF"  # None = no fill
    line: str | None = "#94A3B8"  # None = no line
    line_weight: float = 1.0  # points
    line_pattern: LinePattern = "solid"
    rounding: float = 0.0  # corner radius, inches
    shadow: bool = False
    text: TextStyle = TextStyle()


@dataclass(frozen=True)
class GroupStyle:
    shape: ShapeStyle
    header: TextStyle  # the group label, drawn in the top-left corner
    padding: float = 0.3  # inches between the frame and its members
    header_height: float = 0.4  # inches reserved above members for the label


@dataclass(frozen=True)
class EdgeStyle:
    color: str = "#64748B"
    weight: float = 1.25  # points
    text: TextStyle = TextStyle(size=8.5, color="#475569")
    label_bg: str | None = "#FFFFFF"  # box behind edge labels so lines don't cross text
    corner: float = 0.08  # rounded corners on right-angle routes, inches


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    background: str  # page color
    title: TextStyle
    subtitle: TextStyle
    nodes: dict[str, ShapeStyle]  # by category
    groups: dict[str, GroupStyle]  # by GroupKind
    edge: EdgeStyle
    accent: str  # emphasis border and legend highlights
    secondary: TextStyle  # technology / description lines inside nodes
    dark: bool = False
    legend: ShapeStyle = field(default_factory=lambda: ShapeStyle(fill="#FFFFFF", line="#CBD5E1", rounding=0.06))

    def node_style(self, category: str) -> ShapeStyle:
        return self.nodes.get(category) or self.nodes["generic"]

    def group_style(self, kind: str) -> GroupStyle:
        return self.groups.get(kind) or self.groups["generic"]
