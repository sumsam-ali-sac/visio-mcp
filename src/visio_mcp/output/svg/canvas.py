"""The SVG drawing surface: plan inches to pixels, readable page text, arrowhead markers."""

from __future__ import annotations

from visio_mcp.layout import Rect
from visio_mcp.output.svg.markup import PT, PX, esc, lum, num, snap
from visio_mcp.plan import DiagramPlan
from visio_mcp.style import TextStyle, replace


class Canvas:
    def __init__(self, plan: DiagramPlan) -> None:
        self.plan = plan
        self.theme = plan.theme
        self.W = plan.width * PX
        self.H = plan.height * PX
        self.markers: dict[str, str] = {}  # id -> <marker>, collected for <defs>

    # plan inches (bottom-left origin) -> svg px (top-left origin)
    def X(self, x: float) -> float:
        return x * PX

    def Y(self, y: float) -> float:
        return self.H - y * PX

    def box(self, r: Rect, snapped: bool = True) -> tuple[float, float, float, float]:
        """(x0, y0, x1, y1) in px, top-left to bottom-right."""
        x0, x1 = self.X(r.left), self.X(r.right)
        y0, y1 = self.Y(r.top), self.Y(r.bottom)
        if snapped:
            x0, x1, y0, y1 = snap(x0), snap(x1), snap(y0), snap(y1)
        return x0, y0, x1, y1

    def readable(self, st: TextStyle, secondary: bool = False) -> TextStyle:
        """Text drawn on the bare page must contrast with the page background."""
        bg = self.theme.background
        if abs(lum(st.color) - lum(bg)) >= 90:
            return st
        dark_bg = lum(bg) < 128
        col = ("#94A3B8" if secondary else "#F1F5F9") if dark_bg else ("#475569" if secondary else "#0F172A")
        return replace(st, color=col)

    def marker(self, color: str, weight_pt: float) -> str:
        """Id of an arrowhead marker sized for the line weight (defined once per color and size)."""
        size = round(6.5 + weight_pt * PT * 1.8, 1)
        mid = f"arrow-{color.lstrip('#').lower()}-{num(size).replace('.', '_')}"
        if mid not in self.markers:
            h = size * 0.78
            self.markers[mid] = (
                f'<marker id="{mid}" markerUnits="userSpaceOnUse" markerWidth="{num(size + 2)}" '
                f'markerHeight="{num(h + 2)}" refX="{num(size - 0.5)}" refY="{num(h / 2 + 1)}" '
                f'orient="auto-start-reverse" viewBox="0 0 {num(size + 2)} {num(h + 2)}">'
                f'<path d="M0.5 1L{num(size)} {num(h / 2 + 1)}L0.5 {num(h + 1)}L{num(size * 0.22)} {num(h / 2 + 1)}Z" '
                f'fill="{esc(color)}" stroke="{esc(color)}" stroke-width="0.6" stroke-linejoin="round"/></marker>'
            )
        return mid
