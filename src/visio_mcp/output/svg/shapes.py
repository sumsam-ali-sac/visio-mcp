"""Closed SVG outlines for each node geometry, with the box their text fits in."""

from __future__ import annotations

from visio_mcp.output.svg.markup import PX, num, shape_attrs, snap, stroke_attrs
from visio_mcp.style import ShapeStyle

Box = tuple[float, float, float, float]  # x, y, w, h in px


def shape(geometry: str, x0: float, y0: float, x1: float, y1: float, st: ShapeStyle,
          shadow: bool = False) -> tuple[str, Box]:
    """Return (markup, text box (x, y, w, h)) for a closed shape drawn in the pixel box."""
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    a = shape_attrs(st, shadow)
    r = max(0.0, st.rounding * PX)
    tb = (x0, y0, w, h)
    g = geometry
    if g in ("rect", "rounded", "terminator", "subprocess", "entity"):
        rx = h / 2 if g == "terminator" else min(r, h / 2, w / 2)
        m = f'<rect x="{num(x0)}" y="{num(y0)}" width="{num(w)}" height="{num(h)}" rx="{num(rx)}"{a}/>'
        if g == "subprocess":
            lw = stroke_attrs(st.line, st.line_weight)
            m += "".join(f'<line x1="{num(xx)}" y1="{num(y0)}" x2="{num(xx)}" y2="{num(y1)}"{lw}/>'
                         for xx in (snap(x0 + 10), snap(x1 - 10)))
            tb = (x0 + 10, y0, w - 20, h)
        elif g == "terminator":
            tb = (x0 + h * 0.25, y0, w - h * 0.5, h)
        return m, tb
    if g == "decision":
        pts = [(cx, y0), (x1, cy), (cx, y1), (x0, cy)]
        return _polygon(pts, a), (x0, y0, w, h)
    if g == "parallelogram":
        k = min(w * 0.16, h * 0.5)
        return _polygon([(x0 + k, y0), (x1, y0), (x1 - k, y1), (x0, y1)], a), (x0 + k * 0.6, y0, w - k * 1.2, h)
    if g == "trapezoid":
        k = min(w * 0.14, h * 0.5)
        return _polygon([(x0, y0), (x1, y0), (x1 - k, y1), (x0 + k, y1)], a), (x0 + k * 0.6, y0, w - k * 1.2, h)
    if g == "hexagon":
        k = min(w * 0.18, h * 0.5)
        return _polygon([(x0 + k, y0), (x1 - k, y0), (x1, cy), (x1 - k, y1), (x0 + k, y1), (x0, cy)], a), tb
    if g in ("ellipse", "circle"):
        return f'<ellipse cx="{num(cx)}" cy="{num(cy)}" rx="{num(w / 2)}" ry="{num(h / 2)}"{a}/>', tb
    if g == "document":
        wave = min(h * 0.12, 12)
        d = (f"M{num(x0)} {num(y0)}H{num(x1)}V{num(y1 - wave)}"
             f"Q{num(x0 + w * 0.75)} {num(y1 - wave * 2)} {num(cx)} {num(y1 - wave)}"
             f"T{num(x0)} {num(y1 - wave)}Z")
        return f'<path d="{d}"{a}/>', (x0, y0, w, h - wave)
    if g == "cylinder":
        ry = min(max(h * 0.14, 6), 14)
        d = (f"M{num(x0)} {num(y0 + ry)}A{num(w / 2)} {num(ry)} 0 0 1 {num(x1)} {num(y0 + ry)}"
             f"V{num(y1 - ry)}A{num(w / 2)} {num(ry)} 0 0 1 {num(x0)} {num(y1 - ry)}Z")
        front = f"M{num(x0)} {num(y0 + ry)}A{num(w / 2)} {num(ry)} 0 0 0 {num(x1)} {num(y0 + ry)}"
        lw = stroke_attrs(st.line, st.line_weight) + ' fill="none"'
        return (f'<path d="{d}"{a}/><path d="{front}"{lw}/>', (x0, y0 + ry * 2, w, h - ry * 3))
    if g == "queue":
        rx = min(max(w * 0.1, 8), 18)
        d = (f"M{num(x0 + rx)} {num(y0)}H{num(x1 - rx)}A{num(rx)} {num(h / 2)} 0 0 1 {num(x1 - rx)} {num(y1)}"
             f"H{num(x0 + rx)}A{num(rx)} {num(h / 2)} 0 0 1 {num(x0 + rx)} {num(y0)}Z")
        front = f"M{num(x1 - rx)} {num(y0)}A{num(rx)} {num(h / 2)} 0 0 0 {num(x1 - rx)} {num(y1)}"
        lw = stroke_attrs(st.line, st.line_weight) + ' fill="none"'
        return f'<path d="{d}"{a}/><path d="{front}"{lw}/>', (x0 + rx, y0, w - rx * 2.4, h)
    if g == "cloud":
        def P(u: float, v: float) -> str:
            return f"{num(x0 + u * w)} {num(y0 + v * h)}"

        def A(rx_: float, ry_: float, u: float, v: float) -> str:
            return f"A{num(rx_ * w)} {num(ry_ * h)} 0 0 1 {P(u, v)}"

        d = (f"M{P(0.25, 0.88)}" + A(0.2, 0.27, 0.1, 0.5) + A(0.17, 0.22, 0.3, 0.2) + A(0.2, 0.25, 0.62, 0.12)
             + A(0.18, 0.22, 0.86, 0.32) + A(0.16, 0.25, 0.9, 0.7) + A(0.2, 0.25, 0.75, 0.88) + "Z")
        return f'<path d="{d}"{a}/>', (x0 + w * 0.15, y0 + h * 0.2, w * 0.7, h * 0.62)
    if g == "note":
        f = min(14.0, h * 0.25)
        d = f"M{num(x0)} {num(y0)}H{num(x1 - f)}L{num(x1)} {num(y0 + f)}V{num(y1)}H{num(x0)}Z"
        fold = f"M{num(x1 - f)} {num(y0)}V{num(y0 + f)}H{num(x1)}"
        lw = stroke_attrs(st.line, st.line_weight) + ' fill="none" stroke-linejoin="round"'
        return f'<path d="{d}"{a}/><path d="{fold}"{lw}/>', (x0, y0 + 4, w - 4, h - 4)
    # unknown geometry: rounded rect
    rx = min(r, h / 2, w / 2)
    return f'<rect x="{num(x0)}" y="{num(y0)}" width="{num(w)}" height="{num(h)}" rx="{num(rx)}"{a}/>', tb


def _polygon(pts: list[tuple[float, float]], attrs: str) -> str:
    return f'<polygon points="{" ".join(f"{num(x)},{num(y)}" for x, y in pts)}"{attrs}/>'
