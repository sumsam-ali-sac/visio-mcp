"""DiagramSpec -> DiagramPlan: every decision about how the diagram looks, made once.

A plan holds final geometry (inches, center pins, bottom-left origin), resolved
shapes, styles and text for every element. Emitters only draw it:

- output.visio  drives Visio desktop over COM (live, editable, real stencils)
- output.vsdx   writes a native .vsdx with no Visio installed
- output.svg    draws an SVG preview (any OS, browser, terminal tools)

model    plan dataclasses
kinds    per-node kind, master, icon image, geometry and size
runs     styled text runs for node labels
legend   legend entries, size and placement
build    build_plan, the pipeline that ties them together
audit    geometry audit of a finished plan (import visio_mcp.plan.audit)
"""

from visio_mcp.plan.build import build_plan
from visio_mcp.plan.model import (
    DiagramPlan,
    LegendEntry,
    PlannedEdge,
    PlannedGroup,
    PlannedNode,
    TextBlock,
)

__all__ = [
    "DiagramPlan", "LegendEntry", "PlannedEdge", "PlannedGroup", "PlannedNode", "TextBlock", "build_plan",
]
