"""compute_layout: pick the engine for a layout preset and finish the result."""

from __future__ import annotations

from typing import Literal

from visio_mcp.layout.compound import Compound
from visio_mcp.layout.finish import Direction, finish
from visio_mcp.layout.manual import manual_layout
from visio_mcp.layout.model import Frame, LayoutResult
from visio_mcp.layout.swimlane import swimlane_layout
from visio_mcp.layout.tree import is_forest, tree_layout
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import GroupStyle, NodeSize


def compute_layout(
    spec: DiagramSpec, sizes: dict[str, NodeSize], group_styles: dict[str, GroupStyle], layout: str
) -> LayoutResult:
    """Place every node and group. layout is a concrete spec Layout (never 'auto')."""
    if layout == "none" and any(n.x is not None and n.y is not None for n in spec.nodes):
        return manual_layout(spec, sizes, group_styles)
    lr = layout.endswith("-lr")
    frame = Frame(lr)
    direction: Direction = "lr" if lr else "tb"
    header: Literal["top", "left"] | None = None
    nested = any(g.parent for g in spec.groups)
    if layout.startswith("swimlane") and not nested:
        placed = swimlane_layout(spec, sizes, group_styles, frame)
        header = "left" if lr else "top"
    elif layout.startswith("tree") and not spec.groups and is_forest(spec):
        placed = tree_layout(spec, sizes, frame)
    elif layout.startswith(("flowchart", "tree", "swimlane")):  # nested lanes: groups as blocks
        placed = Compound(spec, sizes, group_styles, frame, "layered").run()
    else:
        mode = layout if layout in ("radial", "circular") else "grid"
        placed = Compound(spec, sizes, group_styles, frame, mode).run()  # type: ignore[arg-type]
        direction = "none"
    return finish(spec, placed, frame, direction, header, layout in ("radial", "circular"))
