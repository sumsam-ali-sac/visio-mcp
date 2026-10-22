"""Group-aware auto-layout: DiagramSpec + node sizes -> positions, group frames, edge routes.

Engines by preset:

- flowchart-* / tree-*  compound layered layout (groups as blocks); tree-* uses a tidy tree
                        when the graph is a forest without groups
- swimlane-*            lanes as full-length bands sharing flow ranks
- radial / circular     rings around a hub / one circle (groups as compact blocks)
- grid                  tidy grid, groups as blocks
- none                  given x/y, the rest in free spots

Modules:

compute         compute_layout: picks the engine for a preset
model           Rect, Point, Frame, LayoutResult and spacing constants
compound        group-aware layered/grid/radial placement (groups as blocks)
layered         rank assignment, ordering and coordinates for layered layouts
hierarchy       group tree of a spec
tree            tidy tree layout for forests
swimlane        lanes as full-length bands
radial          rings around a hub
manual          given x/y positions
polylines       edge polylines: layered paths, straight spokes, orthogonal, self loops
obstacle_router A* routing around boxes for free placements
finish          route every edge and normalize to the origin
"""

from visio_mcp.layout.compute import compute_layout
from visio_mcp.layout.model import LayoutResult, Point, Rect

__all__ = ["LayoutResult", "Point", "Rect", "compute_layout"]
