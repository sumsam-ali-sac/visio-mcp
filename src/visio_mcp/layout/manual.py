"""layout 'none': keep the given positions, put the other nodes in free spots."""

from __future__ import annotations

from visio_mcp.layout.model import Rect
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import NodeSize

CLEAR = 0.4  # free space kept around every node
STEP = 0.25


def manual_positions(spec: DiagramSpec, sizes: dict[str, NodeSize]) -> dict[str, Rect]:
    """Given x/y are centers in inches. Unplaced nodes fill free spots, reading order from the top-left."""
    placed: dict[str, Rect] = {}
    for n in spec.nodes:
        if n.x is not None and n.y is not None:
            placed[n.id] = Rect(n.x, n.y, sizes[n.id].w, sizes[n.id].h)
    free = [n for n in spec.nodes if n.id not in placed]
    if not free:
        return placed
    rects = list(placed.values())
    widest = max(sizes[n.id].w for n in free)
    span = max([r.right for r in rects] + [widest * 4 + CLEAR * 4]) + widest
    top = max([r.top for r in rects], default=0.0)
    for n in free:
        s = sizes[n.id]
        y = top - s.h / 2 if rects else s.h / 2
        while n.id not in placed:
            x = s.w / 2
            while x + s.w / 2 <= span:
                cand = Rect(x, y, s.w, s.h)
                if not any(_hits(cand, r) for r in rects):
                    placed[n.id] = cand
                    rects.append(cand)
                    break
                x += STEP
            y -= STEP
    return placed


def _hits(a: Rect, b: Rect) -> bool:
    return (a.left < b.right + CLEAR and b.left < a.right + CLEAR
            and a.bottom < b.top + CLEAR and b.bottom < a.top + CLEAR)
