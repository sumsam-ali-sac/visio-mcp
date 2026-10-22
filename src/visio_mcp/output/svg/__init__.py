"""DiagramPlan -> SVG preview (and an interactive HTML viewer, and best-effort PNG).

Pure standard library. The plan is in inches with a bottom-left origin; the SVG is in
CSS pixels (1 inch = 96 px) with y flipped, so a shape with a larger plan y is drawn higher.

    render_svg(plan)        standalone SVG string
    write_html(plan, path)  single-file viewer: inline SVG, pan/zoom, dark/light chrome, download
    svg_to_png(svg, png)    rasterize with playwright/chromium or cairosvg; None when neither works
"""

from __future__ import annotations

import base64
import html as _html
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from visio_mcp.output.visio.backend import TextRun
from visio_mcp.layout import Rect
from visio_mcp.plan import DiagramPlan, LegendEntry, PlannedEdge, PlannedGroup, PlannedNode, TextBlock
from visio_mcp.style import ShapeStyle, TextStyle, replace, text_width, wrap  # noqa: F401  (wrap re-used by callers)

PX = 96.0  # px per inch
PT = 96.0 / 72.0  # px per point
LINE_H = 1.25  # line height / font size

# fraction of a shape's width (and height, for round shapes) available to text
_INNER = {"decision": 0.55, "hexagon": 0.75, "ellipse": 0.7, "circle": 0.7, "cloud": 0.6,
          "parallelogram": 0.75, "trapezoid": 0.75}
_ROUND_TEXT = {"decision", "hexagon", "ellipse", "circle", "cloud"}

_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


# --- small helpers ------------------------------------------------------------------------------


def esc(s: object) -> str:
    """Escape text for XML content and attribute values."""
    t = _BAD_XML.sub("", str(s))
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _snap(v: float) -> float:
    """Put a coordinate on a pixel center so 1px strokes stay crisp."""
    return math.floor(v) + 0.5


def _font_stack(font: str) -> str:
    f = font.strip().replace("'", "")
    low = f.lower()
    if low in ("arial", "helvetica"):
        return f"{f}, 'Helvetica Neue', Helvetica, 'Liberation Sans', sans-serif"
    return (f"'{f}', 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, "
            "'Liberation Sans', sans-serif")


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 128, 128, 128


def _lum(c: str) -> float:
    r, g, b = _rgb(c)
    return (r * 299 + g * 587 + b * 114) / 1000


def _dash(pattern: str, weight_px: float) -> str:
    s = max(1.0, weight_px)
    if pattern == "dashed":
        return f"{_n(4.5 * s + 1.5)} {_n(2.5 * s + 1.5)}"
    if pattern == "dotted":
        return f"0.1 {_n(2 * s + 2)}"
    return ""


def _stroke_attrs(color: str | None, weight_pt: float, pattern: str = "solid") -> str:
    if not color:
        return ' stroke="none"'
    w = weight_pt * PT
    out = f' stroke="{esc(color)}" stroke-width="{_n(w)}"'
    d = _dash(pattern, w)
    if d:
        out += f' stroke-dasharray="{d}"'
        if pattern == "dotted":
            out += ' stroke-linecap="round"'
    return out


def _shape_attrs(st: ShapeStyle, shadow: bool = False) -> str:
    fill = esc(st.fill) if st.fill else "none"
    a = f' fill="{fill}"' + _stroke_attrs(st.line, st.line_weight, st.line_pattern) + ' stroke-linejoin="round"'
    if shadow:
        a += ' filter="url(#shadow)"'
    return a


# --- text layout --------------------------------------------------------------------------------


@dataclass
class _Seg:
    text: str
    style: TextStyle
    size: float  # px


@dataclass
class _Line:
    segs: list[_Seg]
    width: float  # px
    height: float  # px


def _word_w(word: str, st: TextStyle, scale: float) -> float:
    return text_width(word, st.size * scale, st.bold) * PX


def _layout_text(runs: list[TextRun], max_w_px: float, scale: float = 1.0) -> list[_Line]:
    """Split runs into paragraphs on '\\n', wrap words greedily to max_w_px."""
    paras: list[list[tuple[str, TextStyle]]] = [[]]
    for r in runs:
        for i, part in enumerate(r.text.split("\n")):
            if i > 0:
                paras.append([])
            for w in part.split():
                paras[-1].append((w, r.style))
    lines: list[_Line] = []
    for para in (p for p in paras if p):
        cur: list[tuple[str, TextStyle]] = []
        cur_w = 0.0
        for word, st in para:
            ww = _word_w(word, st, scale)
            sp = _word_w(" ", st, scale) if cur else 0.0
            if cur and cur_w + sp + ww > max_w_px:
                lines.append(_finish_line(cur, scale))
                cur, cur_w, sp = [], 0.0, 0.0
            cur.append((word, st))
            cur_w += sp + ww
        if cur:
            lines.append(_finish_line(cur, scale))
    return lines


def _finish_line(words: list[tuple[str, TextStyle]], scale: float) -> _Line:
    segs: list[_Seg] = []
    width = 0.0
    for i, (w, st) in enumerate(words):
        width += _word_w(w, st, scale) + (_word_w(" ", st, scale) if i else 0)
        if segs and segs[-1].style == st:
            segs[-1].text += " " + w
        else:
            if segs:
                segs[-1].text += " "
            segs.append(_Seg(w, st, st.size * scale * PT))
    height = max(s.size for s in segs) * LINE_H
    return _Line(segs, width, height)


def _fit_text(runs: list[TextRun], max_w: float, max_h: float, min_scale: float = 0.72) -> tuple[list[_Line], float]:
    """Lay out text, shrinking the font a little when it would overflow max_h."""
    lines = _layout_text(runs, max_w)
    total = sum(ln.height for ln in lines)
    scale = 1.0
    if total > max_h > 0:
        scale = max(min_scale, max_h / total)
        lines = _layout_text(runs, max_w / scale * 1.0, scale)
    return lines, scale


def _text_svg(lines: list[_Line], x: float, top: float, anchor: str = "middle") -> str:
    out: list[str] = []
    y = top
    for ln in lines:
        fs = max(s.size for s in ln.segs)
        base = y + ln.height / 2 + fs * 0.34
        spans = []
        for s in ln.segs:
            st = s.style
            attrs = (f' font-family="{esc(_font_stack(st.font))}" font-size="{_n(s.size)}" fill="{esc(st.color)}"')
            if st.bold:
                attrs += ' font-weight="600"'
            if st.italic:
                attrs += ' font-style="italic"'
            spans.append(f"<tspan{attrs}>{esc(s.text)}</tspan>")
        out.append(f'<text x="{_n(x)}" y="{_n(base)}" text-anchor="{anchor}" xml:space="preserve">{"".join(spans)}</text>')
        y += ln.height
    return "".join(out)


def _block_h(lines: list[_Line]) -> float:
    return sum(ln.height for ln in lines)


# --- shapes -------------------------------------------------------------------------------------


def _shape(geometry: str, x0: float, y0: float, x1: float, y1: float, st: ShapeStyle,
           shadow: bool = False) -> tuple[str, tuple[float, float, float, float]]:
    """Return (markup, text box (x, y, w, h)) for a closed shape drawn in the pixel box."""
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    a = _shape_attrs(st, shadow)
    r = max(0.0, st.rounding * PX)
    tb = (x0, y0, w, h)
    g = geometry
    if g in ("rect", "rounded", "terminator", "subprocess", "entity"):
        rx = h / 2 if g == "terminator" else min(r, h / 2, w / 2)
        if g == "terminator":
            rx = h / 2
        m = f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(w)}" height="{_n(h)}" rx="{_n(rx)}"{a}/>'
        if g == "subprocess":
            lw = _stroke_attrs(st.line, st.line_weight)
            m += "".join(f'<line x1="{_n(xx)}" y1="{_n(y0)}" x2="{_n(xx)}" y2="{_n(y1)}"{lw}/>'
                         for xx in (_snap(x0 + 10), _snap(x1 - 10)))
            tb = (x0 + 10, y0, w - 20, h)
        elif g == "terminator":
            tb = (x0 + h * 0.25, y0, w - h * 0.5, h)
        return m, tb
    if g == "decision":
        pts = [(cx, y0), (x1, cy), (cx, y1), (x0, cy)]
        return _poly(pts, a), (x0, y0, w, h)
    if g == "parallelogram":
        k = min(w * 0.16, h * 0.5)
        return _poly([(x0 + k, y0), (x1, y0), (x1 - k, y1), (x0, y1)], a), (x0 + k * 0.6, y0, w - k * 1.2, h)
    if g == "trapezoid":
        k = min(w * 0.14, h * 0.5)
        return _poly([(x0, y0), (x1, y0), (x1 - k, y1), (x0 + k, y1)], a), (x0 + k * 0.6, y0, w - k * 1.2, h)
    if g == "hexagon":
        k = min(w * 0.18, h * 0.5)
        return _poly([(x0 + k, y0), (x1 - k, y0), (x1, cy), (x1 - k, y1), (x0 + k, y1), (x0, cy)], a), tb
    if g in ("ellipse", "circle"):
        return f'<ellipse cx="{_n(cx)}" cy="{_n(cy)}" rx="{_n(w / 2)}" ry="{_n(h / 2)}"{a}/>', tb
    if g == "document":
        wave = min(h * 0.12, 12)
        d = (f"M{_n(x0)} {_n(y0)}H{_n(x1)}V{_n(y1 - wave)}"
             f"Q{_n(x0 + w * 0.75)} {_n(y1 - wave * 2)} {_n(cx)} {_n(y1 - wave)}"
             f"T{_n(x0)} {_n(y1 - wave)}Z")
        return f'<path d="{d}"{a}/>', (x0, y0, w, h - wave)
    if g == "cylinder":
        ry = min(max(h * 0.14, 6), 14)
        d = (f"M{_n(x0)} {_n(y0 + ry)}A{_n(w / 2)} {_n(ry)} 0 0 1 {_n(x1)} {_n(y0 + ry)}"
             f"V{_n(y1 - ry)}A{_n(w / 2)} {_n(ry)} 0 0 1 {_n(x0)} {_n(y1 - ry)}Z")
        front = f"M{_n(x0)} {_n(y0 + ry)}A{_n(w / 2)} {_n(ry)} 0 0 0 {_n(x1)} {_n(y0 + ry)}"
        lw = _stroke_attrs(st.line, st.line_weight) + ' fill="none"'
        return (f'<path d="{d}"{a}/><path d="{front}"{lw}/>', (x0, y0 + ry * 2, w, h - ry * 3))
    if g == "queue":
        rx = min(max(w * 0.1, 8), 18)
        d = (f"M{_n(x0 + rx)} {_n(y0)}H{_n(x1 - rx)}A{_n(rx)} {_n(h / 2)} 0 0 1 {_n(x1 - rx)} {_n(y1)}"
             f"H{_n(x0 + rx)}A{_n(rx)} {_n(h / 2)} 0 0 1 {_n(x0 + rx)} {_n(y0)}Z")
        front = f"M{_n(x1 - rx)} {_n(y0)}A{_n(rx)} {_n(h / 2)} 0 0 0 {_n(x1 - rx)} {_n(y1)}"
        lw = _stroke_attrs(st.line, st.line_weight) + ' fill="none"'
        return f'<path d="{d}"{a}/><path d="{front}"{lw}/>', (x0 + rx, y0, w - rx * 2.4, h)
    if g == "cloud":
        def P(u: float, v: float) -> str:
            return f"{_n(x0 + u * w)} {_n(y0 + v * h)}"

        def A(rx_: float, ry_: float, u: float, v: float) -> str:
            return f"A{_n(rx_ * w)} {_n(ry_ * h)} 0 0 1 {P(u, v)}"

        d = (f"M{P(0.25, 0.88)}" + A(0.2, 0.27, 0.1, 0.5) + A(0.17, 0.22, 0.3, 0.2) + A(0.2, 0.25, 0.62, 0.12)
             + A(0.18, 0.22, 0.86, 0.32) + A(0.16, 0.25, 0.9, 0.7) + A(0.2, 0.25, 0.75, 0.88) + "Z")
        return f'<path d="{d}"{a}/>', (x0 + w * 0.15, y0 + h * 0.2, w * 0.7, h * 0.62)
    if g == "note":
        f = min(14.0, h * 0.25)
        d = f"M{_n(x0)} {_n(y0)}H{_n(x1 - f)}L{_n(x1)} {_n(y0 + f)}V{_n(y1)}H{_n(x0)}Z"
        fold = f"M{_n(x1 - f)} {_n(y0)}V{_n(y0 + f)}H{_n(x1)}"
        lw = _stroke_attrs(st.line, st.line_weight) + ' fill="none" stroke-linejoin="round"'
        return f'<path d="{d}"{a}/><path d="{fold}"{lw}/>', (x0, y0 + 4, w - 4, h - 4)
    # unknown geometry: rounded rect
    rx = min(r, h / 2, w / 2)
    return f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(w)}" height="{_n(h)}" rx="{_n(rx)}"{a}/>', tb


def _poly(pts: list[tuple[float, float]], attrs: str) -> str:
    return f'<polygon points="{" ".join(f"{_n(x)},{_n(y)}" for x, y in pts)}"{attrs}/>'


# --- the renderer -------------------------------------------------------------------------------


class _Ctx:
    def __init__(self, plan: DiagramPlan) -> None:
        self.plan = plan
        self.theme = plan.theme
        self.W = plan.width * PX
        self.H = plan.height * PX
        self.markers: dict[str, str] = {}

    # plan inches (bottom-left) -> svg px (top-left)
    def X(self, x: float) -> float:
        return x * PX

    def Y(self, y: float) -> float:
        return self.H - y * PX

    def box(self, r: Rect, snap: bool = True) -> tuple[float, float, float, float]:
        x0, x1 = self.X(r.left), self.X(r.right)
        y0, y1 = self.Y(r.top), self.Y(r.bottom)
        if snap:
            x0, x1, y0, y1 = _snap(x0), _snap(x1), _snap(y0), _snap(y1)
        return x0, y0, x1, y1

    def readable(self, st: TextStyle, secondary: bool = False) -> TextStyle:
        """Text drawn on the bare page must contrast with the page background."""
        bg = self.theme.background
        if abs(_lum(st.color) - _lum(bg)) >= 90:
            return st
        dark_bg = _lum(bg) < 128
        col = ("#94A3B8" if secondary else "#F1F5F9") if dark_bg else ("#475569" if secondary else "#0F172A")
        return replace(st, color=col)

    def marker(self, color: str, weight_pt: float) -> str:
        size = round(6.5 + weight_pt * PT * 1.8, 1)
        mid = f"arrow-{color.lstrip('#').lower()}-{_n(size).replace('.', '_')}"
        if mid not in self.markers:
            h = size * 0.78
            self.markers[mid] = (
                f'<marker id="{mid}" markerUnits="userSpaceOnUse" markerWidth="{_n(size + 2)}" '
                f'markerHeight="{_n(h + 2)}" refX="{_n(size - 0.5)}" refY="{_n(h / 2 + 1)}" '
                f'orient="auto-start-reverse" viewBox="0 0 {_n(size + 2)} {_n(h + 2)}">'
                f'<path d="M0.5 1L{_n(size)} {_n(h / 2 + 1)}L0.5 {_n(h + 1)}L{_n(size * 0.22)} {_n(h / 2 + 1)}Z" '
                f'fill="{esc(color)}" stroke="{esc(color)}" stroke-width="0.6" stroke-linejoin="round"/></marker>'
            )
        return mid


def render_svg(plan: DiagramPlan) -> str:
    """Draw the plan as a standalone SVG document."""
    c = _Ctx(plan)
    th = plan.theme
    body: list[str] = []

    body.append(f'<rect class="page" width="{_n(c.W)}" height="{_n(c.H)}" fill="{esc(th.background)}"/>')

    if plan.groups:
        body.append('<g id="groups">')
        for i, g in enumerate(plan.groups):
            body.append(_group(c, g, i))
        body.append("</g>")
    if plan.edges:
        body.append('<g id="edges" fill="none">')
        for i, e in enumerate(plan.edges):
            body.append(_edge(c, e, i))
        body.append("</g>")
    if plan.nodes:
        body.append('<g id="nodes">')
        for i, n in enumerate(plan.nodes):
            body.append(_node(c, n, i))
        body.append("</g>")
    if plan.title:
        body.append(f'<g id="title" data-id="title">{_text_block(c, plan.title)}</g>')
    if plan.legend:
        body.append(_legend(c))

    title = plan.spec.title or "Diagram"
    desc = plan.spec.subtitle or f"{len(plan.nodes)} nodes, {len(plan.edges)} connections"
    defs = ["<defs>"]
    if not th.dark:
        defs.append('<filter id="shadow" x="-10%" y="-10%" width="125%" height="135%" color-interpolation-filters="sRGB">'
                    '<feDropShadow dx="0" dy="1" stdDeviation="1.4" flood-color="#0F172A" flood-opacity="0.10"/></filter>')
    else:
        defs.append('<filter id="shadow" x="-10%" y="-10%" width="125%" height="135%" color-interpolation-filters="sRGB">'
                    '<feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000000" flood-opacity="0.35"/></filter>')
    defs.extend(c.markers.values())
    defs.append("</defs>")

    w, h = _n(c.W), _n(c.H)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="svg-title svg-desc" text-rendering="geometricPrecision" '
        f'data-theme="{esc(th.name)}">'
        f'<title id="svg-title">{esc(title)}</title><desc id="svg-desc">{esc(desc)}</desc>'
        + "".join(defs) + "".join(body) + "</svg>\n"
    )


def _group(c: _Ctx, g: PlannedGroup, idx: int) -> str:
    x0, y0, x1, y1 = c.box(g.rect)
    st = g.style.shape
    a = _shape_attrs(st)
    rx = min(max(0.0, st.rounding * PX), (y1 - y0) / 2, (x1 - x0) / 2)
    out = [f'<g id="group-{idx}" class="group" data-id="{esc(g.id)}" data-kind="{esc(g.kind)}" data-depth="{g.depth}">',
           f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0)}" height="{_n(y1 - y0)}" rx="{_n(rx)}"{a}/>']
    if g.label:
        hs = g.style.header
        size = hs.size * PT
        line = _Line([_Seg(g.label, hs, size)], 0, size * LINE_H)
        pad = 12 + min(rx, 8)
        top = y0 + (g.style.header_height * PX - line.height) / 2 + 2
        out.append(_text_svg([line], x0 + pad, top, "start"))
    out.append("</g>")
    return "".join(out)


def _node(c: _Ctx, n: PlannedNode, idx: int) -> str:
    head = (f'<g id="node-{idx}" class="node" data-id="{esc(n.id)}" data-kind="{esc(n.kind)}" '
            f'data-geometry="{esc(n.geometry)}"{" data-emphasis=\"true\"" if n.emphasis else ""}>')
    st = n.style
    x0, y0, x1, y1 = c.box(n.shape)
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    if n.geometry in ("icon", "person"):
        return head + _icon_node(c, n, x0, y0, x1, y1) + "</g>"

    markup, (tx, ty, tw, th_) = _shape(n.geometry, x0, y0, x1, y1, st, shadow=True)
    inner = _INNER.get(n.geometry, 0.88 if n.geometry not in ("subprocess",) else 1.0)
    if n.geometry in ("rect", "rounded", "terminator", "subprocess", "note", "document", "cylinder", "queue",
                      "entity"):
        max_w = tw - 20
    else:
        max_w = w * inner - 6
    max_h = th_ - 12 if n.geometry not in _ROUND_TEXT else h * _INNER.get(n.geometry, 0.7) * 1.05
    max_w = max(max_w, 24)

    text = ""
    if n.geometry == "entity" and len(n.runs) > 1 and h >= 52:
        band = 32.0
        lines, _ = _fit_text(n.runs[:1], w - 20, band - 6)
        rest, _ = _fit_text(n.runs[1:], w - 24, h - band - 12)
        lcol = st.line or "#64748B"
        markup = (f'<g><clipPath id="clip-{idx}"><rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(w)}" height="{_n(h)}" '
                  f'rx="{_n(min(st.rounding * PX, 8))}"/></clipPath>' + markup +
                  f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(w)}" height="{_n(band)}" fill="{esc(lcol)}" '
                  f'fill-opacity="0.14" clip-path="url(#clip-{idx})"/>'
                  f'<line x1="{_n(x0)}" y1="{_n(_snap(y0 + band))}" x2="{_n(x1)}" y2="{_n(_snap(y0 + band))}"'
                  f'{_stroke_attrs(st.line, st.line_weight)}/></g>')
        text += _text_svg(lines, cx, y0 + (band - _block_h(lines)) / 2)
        text += _text_svg(rest, cx, y0 + band + (h - band - _block_h(rest)) / 2)
        return head + markup + text + "</g>"

    lines, _ = _fit_text(n.runs, max_w, max_h)
    top = ty + (th_ - _block_h(lines)) / 2
    tcx = tx + tw / 2
    text = _text_svg(lines, tcx, top)
    return head + markup + text + "</g>"


def _icon_node(c: _Ctx, n: PlannedNode, x0: float, y0: float, x1: float, y1: float) -> str:
    st = n.style
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    col = st.line or "#475569"
    out: list[str] = []
    if n.geometry == "person":
        s = min(w, h)
        px0, py0 = cx - s / 2, y0
        fillc = col
        head_r = s * 0.2
        out.append(
            f'<g fill="{esc(fillc)}" stroke="none" filter="url(#shadow)">'
            f'<circle cx="{_n(cx)}" cy="{_n(py0 + s * 0.28)}" r="{_n(head_r)}"/>'
            f'<path d="M{_n(px0 + s * 0.12)} {_n(py0 + s)}'
            f'C{_n(px0 + s * 0.12)} {_n(py0 + s * 0.62)} {_n(px0 + s * 0.3)} {_n(py0 + s * 0.55)} {_n(cx)} {_n(py0 + s * 0.55)}'
            f'C{_n(px0 + s * 0.7)} {_n(py0 + s * 0.55)} {_n(px0 + s * 0.88)} {_n(py0 + s * 0.62)} {_n(px0 + s * 0.88)} {_n(py0 + s)}Z"/></g>')
    elif n.image is not None and (uri := _image_uri(n.image)):
        s = min(w, h)
        out.append(f'<image xmlns:xlink="http://www.w3.org/1999/xlink" x="{_n(cx - s / 2)}" y="{_n(y0)}" width="{_n(s)}" height="{_n(s)}" '
                   f'preserveAspectRatio="xMidYMid meet" xlink:href="{uri}"/>')
    else:
        s = min(w, h)
        rx = s * 0.18
        tx0, ty0 = _snap(cx - s / 2), y0
        out.append(f'<rect x="{_n(tx0)}" y="{_n(ty0)}" width="{_n(s)}" height="{_n(s)}" rx="{_n(rx)}" '
                   f'fill="{esc(col)}" stroke="none" filter="url(#shadow)"/>')
        # soft top highlight keeps the tile from looking flat
        out.append(f'<rect x="{_n(tx0 + 0.5)}" y="{_n(ty0 + 0.5)}" width="{_n(s - 1)}" height="{_n(s - 1)}" rx="{_n(rx)}" '
                   f'fill="none" stroke="#FFFFFF" stroke-opacity="0.22"/>')
        vec = None if n.glyph else _vector_glyph(n.kind, cx, ty0 + s / 2, s)
        if vec:
            out.append(vec)
            glyph = ""
        else:
            glyph = n.glyph or n.kind.split("-")[-1][:2].upper()
        gsize = s * (0.40 if len(glyph) <= 1 else 0.34 if len(glyph) == 2 else 0.27)
        gst = TextStyle(font=st.text.font, size=gsize / PT, color="#FFFFFF", bold=True)
        if glyph:
            gl = _Line([_Seg(glyph, gst, gsize)], 0, gsize * LINE_H)
            out.append(_text_svg([gl], cx, ty0 + (s - gl.height) / 2))
    # label below, inside the node footprint
    fp = n.rect
    fx0, fx1 = c.X(fp.left), c.X(fp.right)
    runs = [TextRun(r.text, c.readable(r.style, secondary=i > 0)) for i, r in enumerate(n.runs)]
    avail_h = c.Y(fp.bottom) - (y0 + min(w, h) + 6)
    lines, _ = _fit_text(runs, (fx1 - fx0) - 4, max(avail_h, 14))
    out.append(_text_svg(lines, cx, y0 + min(w, h) + 6))
    return "".join(out)


_URI_CACHE: dict[tuple[str, int, int], str] = {}


def _image_uri(path: Path) -> str | None:
    """An icon file as a base64 data URI (SVG or PNG); None when it can't be read."""
    try:
        p = Path(path)
        st = p.stat()
        key = (str(p), st.st_mtime_ns, st.st_size)
        if key not in _URI_CACHE:
            mime = {".svg": "image/svg+xml", ".png": "image/png"}.get(p.suffix.lower())
            if mime is None:
                return None
            _URI_CACHE[key] = f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
        return _URI_CACHE[key]
    except OSError:
        return None


def _vector_glyph(kind: str, cx: float, cy: float, s: float) -> str | None:
    """Simple white line glyphs for common icon kinds; None when there is no drawing for the kind."""
    k = kind.lower()
    sw = max(1.5, s * 0.05)
    a = f'fill="none" stroke="#FFFFFF" stroke-width="{_n(sw)}" stroke-linecap="round" stroke-linejoin="round"'
    u = s / 100.0

    def R(x, y, w, h, r=0):
        return (f'<rect x="{_n(cx + x * u)}" y="{_n(cy + y * u)}" width="{_n(w * u)}" height="{_n(h * u)}" '
                f'rx="{_n(r * u)}"/>')

    def L(x1, y1, x2, y2):
        return f'<path d="M{_n(cx + x1 * u)} {_n(cy + y1 * u)}L{_n(cx + x2 * u)} {_n(cy + y2 * u)}"/>'

    def Dot(x, y):
        return f'<circle cx="{_n(cx + x * u)}" cy="{_n(cy + y * u)}" r="{_n(sw * 0.6)}" fill="#FFFFFF" stroke="none"/>'

    body = None
    if "server" in k:
        body = R(-28, -32, 56, 17, 4) + R(-28, -8.5, 56, 17, 4) + R(-28, 15, 56, 17, 4) + Dot(-17, -23.5) + Dot(-17, 0) + Dot(-17, 23.5)
    elif "router" in k:
        body = (R(-32, 2, 64, 26, 5) + L(-16, 2, -16, -14) + L(16, 2, 16, -14) + L(-16, -14, -24, -22)
                + L(16, -14, 24, -22) + Dot(-16, 15) + Dot(0, 15))
    elif "switch" in k:
        body = (R(-34, -12, 68, 26, 5) + L(-16, 0, 16, 0) + L(8, -7, 16, 0) + L(8, 7, 16, 0) + L(-8, -7, -16, 0) + L(-8, 7, -16, 0))
    elif "firewall" in k:
        body = (R(-30, -28, 60, 56, 3) + L(-30, -9.5, 30, -9.5) + L(-30, 9.5, 30, 9.5) + L(0, -28, 0, -9.5)
                + L(-15, -9.5, -15, 9.5) + L(15, -9.5, 15, 9.5) + L(0, 9.5, 0, 28))
    elif k in ("pc", "client", "workstation", "desktop", "laptop"):
        body = R(-32, -28, 64, 42, 4) + L(0, 14, 0, 26) + L(-16, 28, 16, 28)
    elif "mobile" in k or "phone" in k:
        body = R(-17, -32, 34, 64, 7) + L(-6, 24, 6, 24)
    if body is None:
        return None
    return f'<g {a}>{body}</g>'


def _rounded_path(pts: list[tuple[float, float]], radius: float) -> str:
    p = [pts[0]]
    for q in pts[1:]:
        if abs(q[0] - p[-1][0]) > 1e-6 or abs(q[1] - p[-1][1]) > 1e-6:
            p.append(q)
    if len(p) < 2:
        return ""
    d = [f"M{_n(p[0][0])} {_n(p[0][1])}"]
    for i in range(1, len(p) - 1):
        (ax, ay), (bx, by), (cx_, cy_) = p[i - 1], p[i], p[i + 1]
        l1, l2 = math.hypot(bx - ax, by - ay), math.hypot(cx_ - bx, cy_ - by)
        r = min(radius, l1 / 2, l2 / 2)
        # collinear points need no rounding
        cross = (bx - ax) * (cy_ - by) - (by - ay) * (cx_ - bx)
        if r < 0.5 or abs(cross) < 1e-6:
            d.append(f"L{_n(bx)} {_n(by)}")
            continue
        s1 = (bx - (bx - ax) / l1 * r, by - (by - ay) / l1 * r)
        s2 = (bx + (cx_ - bx) / l2 * r, by + (cy_ - by) / l2 * r)
        d.append(f"L{_n(s1[0])} {_n(s1[1])}Q{_n(bx)} {_n(by)} {_n(s2[0])} {_n(s2[1])}")
    d.append(f"L{_n(p[-1][0])} {_n(p[-1][1])}")
    return "".join(d)


def _edge(c: _Ctx, e: PlannedEdge, idx: int) -> str:
    st = e.style
    head = (f'<g id="edge-{idx}" class="edge" data-id="{esc(e.name)}" data-source="{esc(e.source)}" '
            f'data-target="{esc(e.target)}">')
    pts = [(_snap(c.X(x)), _snap(c.Y(y))) for x, y in e.points]
    if len(pts) < 2:
        return head + "</g>"
    d = _rounded_path(pts, st.corner * PX)
    attrs = _stroke_attrs(e.color, st.weight, e.pattern) + ' stroke-linejoin="round"'
    if e.pattern != "dotted":
        attrs += ' stroke-linecap="round"' if "linecap" not in attrs else ""
    if e.arrow in ("end", "both"):
        mid = c.marker(e.color, st.weight)
        attrs += f' marker-end="url(#{mid})"'
        if e.arrow == "both":
            attrs += f' marker-start="url(#{mid})"'
    out = [head, f'<path d="{d}"{attrs}/>']
    if e.label:
        # label sits at the midpoint of the longest segment
        best = max(range(len(pts) - 1), key=lambda i: math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]))
        mx = (pts[best][0] + pts[best + 1][0]) / 2
        my = (pts[best][1] + pts[best + 1][1]) / 2
        ts = st.text
        size = ts.size * PT
        lines = _layout_text([TextRun(e.label, ts)], 2.2 * PX)
        tw = max(ln.width for ln in lines)
        th_ = _block_h(lines)
        padx, pady = 6.0, 2.5
        if st.label_bg:
            out.append(f'<rect class="edge-label-bg" x="{_n(mx - tw / 2 - padx)}" y="{_n(my - th_ / 2 - pady)}" '
                       f'width="{_n(tw + 2 * padx)}" height="{_n(th_ + 2 * pady)}" rx="3" fill="{esc(st.label_bg)}" '
                       f'stroke="none"/>')
        out.append(_text_svg(lines, mx, my - th_ / 2))
        del size
    out.append("</g>")
    return "".join(out)


def _text_block(c: _Ctx, tb: TextBlock) -> str:
    r = tb.rect
    x0, x1 = c.X(r.left), c.X(r.right)
    runs = [TextRun(t.text, c.readable(t.style, secondary=i > 0)) for i, t in enumerate(tb.runs)]
    lines = _layout_text(runs, (x1 - x0) + 80)
    top = (c.Y(r.top) + c.Y(r.bottom)) / 2 - _block_h(lines) / 2
    if tb.align == "left":
        return _text_svg(lines, x0, top, "start")
    if tb.align == "right":
        return _text_svg(lines, x1, top, "end")
    return _text_svg(lines, (x0 + x1) / 2, top, "middle")


def _legend(c: _Ctx) -> str:
    p = c.plan
    th = c.theme
    x0, y0, x1, y1 = c.box(p.legend)  # type: ignore[arg-type]
    ls = th.legend
    rx = min(ls.rounding * PX, 10)
    out = [f'<g id="legend" class="legend" data-id="legend">',
           f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0)}" height="{_n(y1 - y0)}" rx="{_n(rx)}"'
           f'{_shape_attrs(replace(ls, shadow=False))}/>']
    if p.legend_title:
        tb = p.legend_title
        r = tb.rect
        runs = tb.runs
        lines = _layout_text(runs, 200)
        top = (c.Y(r.top) + c.Y(r.bottom)) / 2 - _block_h(lines) / 2
        out.append(_text_svg(lines, x0 + (0.18 * PX), top, "start"))
    text_style = replace(ls.text, size=9)
    for i, (srect, trect, entry) in enumerate(p.legend_entries):
        out.append(f'<g class="legend-entry" data-id="legend-{i}" data-sample="{esc(entry.sample)}">')
        out.append(_legend_sample(c, srect, entry))
        tx = c.X(trect.left)
        cy = (c.Y(trect.top) + c.Y(trect.bottom)) / 2
        size = text_style.size * PT
        ln = _Line([_Seg(entry.label, text_style, size)], 0, size * LINE_H)
        out.append(_text_svg([ln], tx, cy - ln.height / 2, "start"))
        out.append("</g>")
    out.append("</g>")
    return "".join(out)


def _legend_sample(c: _Ctx, r: Rect, e: LegendEntry) -> str:
    x0, y0, x1, y1 = c.box(r)
    if e.sample == "edge":
        cy = _snap((y0 + y1) / 2)
        color = e.color or c.theme.edge.color
        wt = c.theme.edge.weight
        mid = c.marker(color, wt)
        return (f'<path d="M{_n(x0 + 1)} {_n(cy)}H{_n(x1 - 1)}" fill="none"'
                f'{_stroke_attrs(color, wt, e.pattern)} marker-end="url(#{mid})"/>')
    st = e.style or ShapeStyle()
    st = replace(st, line_weight=min(st.line_weight, 1.0))
    if e.sample == "group":
        return f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0)}" height="{_n(y1 - y0)}" rx="3"{_shape_attrs(st)}/>'
    markup, _ = _shape(e.geometry, x0, y0, x1, y1, st)
    return markup


# --- PNG ----------------------------------------------------------------------------------------


def _svg_size(svg: str) -> tuple[float, float]:
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if m:
        return float(m.group(1)), float(m.group(2))
    return 1200.0, 800.0


def _find_chromium() -> str | None:
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers"]
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for pat in ("chromium-*/chrome-linux/chrome", "chromium_headless_shell-*/chrome-linux/headless_shell",
                    "chromium-*/chrome-linux64/chrome", "chromium-*/chrome-win/chrome.exe",
                    "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"):
            hits = sorted(Path(root).glob(pat))
            if hits:
                return str(hits[-1])
    return None


def _png_playwright(svg: str, png_path: Path, scale: float) -> bool:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except Exception:
        return False
    w, h = _svg_size(svg)
    page_html = ("<!doctype html><meta charset=utf-8><style>html,body{margin:0;padding:0;background:transparent}"
                 "svg{display:block}</style>" + re.sub(r"^<\?xml[^>]*\?>", "", svg))
    with sync_playwright() as pw:
        browser = None
        args = ["--no-sandbox", "--disable-gpu"]
        try:
            browser = pw.chromium.launch(args=args)
        except Exception:
            exe = _find_chromium()
            if exe:
                browser = pw.chromium.launch(executable_path=exe, args=args)
        if browser is None:
            return False
        try:
            ctx = browser.new_context(viewport={"width": max(1, math.ceil(w)), "height": max(1, math.ceil(h))},
                                      device_scale_factor=scale)
            page = ctx.new_page()
            page.set_content(page_html)
            page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": w, "height": h})
        finally:
            browser.close()
    return png_path.exists()


def _png_cairosvg(svg: str, png_path: Path, scale: float) -> bool:
    try:
        import cairosvg  # type: ignore[import-not-found]
    except Exception:
        return False
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path), scale=scale)
    return png_path.exists()


def svg_to_png(svg_path: str | os.PathLike, png_path: str | os.PathLike, scale: float = 2.0) -> Path | None:
    """Best-effort rasterization. Tries playwright/chromium, then cairosvg; returns None if neither works."""
    try:
        src = Path(svg_path)
        out = Path(png_path)
        svg = src.read_text(encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    for fn in (_png_playwright, _png_cairosvg):
        try:
            if fn(svg, out, scale):
                return out
        except Exception:
            continue
    return None


# --- HTML viewer --------------------------------------------------------------------------------

_HTML = """<!doctype html>
<html lang="en" data-theme="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#F4F5F7;--panel:#FFFFFF;--ink:#0F172A;--muted:#64748B;--line:#E2E8F0;--accent:#2563EB;--dot:#D5DAE1;--shadow:0 1px 2px rgba(15,23,42,.08),0 12px 32px rgba(15,23,42,.10)}
:root[data-theme=dark]{--bg:#0B1020;--panel:#141B2D;--ink:#E5E9F2;--muted:#8B97AD;--line:#26304A;--accent:#60A5FA;--dot:#1C2540;--shadow:0 1px 2px rgba(0,0,0,.5),0 16px 40px rgba(0,0,0,.45)}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.4 'Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif;display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--panel);border-bottom:1px solid var(--line);flex:none}
h1{font-size:15px;font-weight:600;margin:0;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
h1 small{font-weight:400;color:var(--muted);margin-left:10px;font-size:12.5px}
.tools{display:flex;gap:6px;align-items:center}
button{font:inherit;color:var(--ink);background:transparent;border:1px solid var(--line);border-radius:8px;height:32px;min-width:32px;padding:0 10px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px}
button:hover{background:color-mix(in srgb,var(--accent) 10%,transparent);border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}
button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
#zoom{min-width:48px;text-align:center;color:var(--muted);font-variant-numeric:tabular-nums;font-size:12.5px}
#vp{flex:1;position:relative;overflow:hidden;cursor:grab;touch-action:none;background-image:radial-gradient(var(--dot) 1px,transparent 1px);background-size:22px 22px}
#vp.drag{cursor:grabbing}
#canvas{position:absolute;left:0;top:0;transform-origin:0 0;box-shadow:var(--shadow);border-radius:4px;overflow:hidden;line-height:0;user-select:none;-webkit-user-select:none}
#canvas svg{display:block}
footer{position:absolute;left:16px;bottom:12px;color:var(--muted);font-size:12px;pointer-events:none}
@media(max-width:560px){h1 small,.lbl{display:none}}
</style>
</head>
<body>
<header>
  <h1>__TITLE__<small>__SUB__</small></h1>
  <div class="tools">
    <button id="out" title="Zoom out (-)" aria-label="Zoom out">&minus;</button>
    <span id="zoom">100%</span>
    <button id="in" title="Zoom in (+)" aria-label="Zoom in">+</button>
    <button id="fit" title="Fit to window (0)">Fit</button>
    <button id="theme" title="Toggle light/dark interface" aria-label="Toggle theme">&#9680;</button>
    <button id="dl" title="Download SVG">&#8681;<span class="lbl">SVG</span></button>
  </div>
</header>
<div id="vp"><div id="canvas">__SVG__</div><footer>Scroll to zoom &middot; drag to pan &middot; 0 fit &middot; + / &minus; zoom</footer></div>
<script>
(function(){
var vp=document.getElementById('vp'),cv=document.getElementById('canvas'),svg=cv.querySelector('svg');
var W=parseFloat(svg.getAttribute('width')),H=parseFloat(svg.getAttribute('height'));
var s=1,x=0,y=0,fitted=true,MIN=.05,MAX=10;
function apply(){cv.style.transform='translate('+x+'px,'+y+'px) scale('+s+')';document.getElementById('zoom').textContent=Math.round(s*100)+'%';}
function fit(){var vw=vp.clientWidth,vh=vp.clientHeight,pad=40;s=Math.min((vw-pad)/W,(vh-pad)/H,2);s=Math.max(s,MIN);x=(vw-W*s)/2;y=(vh-H*s)/2;fitted=true;apply();}
function zoomAt(cx,cy,f){var n=Math.min(MAX,Math.max(MIN,s*f));f=n/s;x=cx-(cx-x)*f;y=cy-(cy-y)*f;s=n;fitted=false;apply();}
function center(f){zoomAt(vp.clientWidth/2,vp.clientHeight/2,f);}
vp.addEventListener('wheel',function(e){e.preventDefault();var r=vp.getBoundingClientRect();var k=e.ctrlKey?.01:.0016;zoomAt(e.clientX-r.left,e.clientY-r.top,Math.exp(-e.deltaY*k));},{passive:false});
var drag=null;
vp.addEventListener('pointerdown',function(e){if(e.button!==0)return;drag={px:e.clientX,py:e.clientY,x:x,y:y};vp.classList.add('drag');vp.setPointerCapture(e.pointerId);});
vp.addEventListener('pointermove',function(e){if(!drag)return;x=drag.x+e.clientX-drag.px;y=drag.y+e.clientY-drag.py;fitted=false;apply();});
function end(e){drag=null;vp.classList.remove('drag');}
vp.addEventListener('pointerup',end);vp.addEventListener('pointercancel',end);
vp.addEventListener('dblclick',fit);
document.getElementById('in').onclick=function(){center(1.25)};
document.getElementById('out').onclick=function(){center(1/1.25)};
document.getElementById('fit').onclick=fit;
document.addEventListener('keydown',function(e){if(e.metaKey||e.ctrlKey||e.altKey)return;
 if(e.key==='0')fit();else if(e.key==='+'||e.key==='=')center(1.25);else if(e.key==='-'||e.key==='_')center(1/1.25);});
window.addEventListener('resize',function(){if(fitted)fit();});
var root=document.documentElement;
document.getElementById('theme').onclick=function(){root.setAttribute('data-theme',root.getAttribute('data-theme')==='dark'?'light':'dark');};
document.getElementById('dl').onclick=function(){
 var src='<?xml version="1.0" encoding="UTF-8"?>\\n'+new XMLSerializer().serializeToString(svg);
 var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([src],{type:'image/svg+xml'}));
 a.download=__FILENAME__;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(a.href)},1000);};
fit();
})();
</script>
</body>
</html>
"""


def write_html(plan: DiagramPlan, path: str | os.PathLike) -> Path:
    """Write a self-contained HTML viewer (inline SVG, pan/zoom, chrome theme toggle, SVG download)."""
    import json

    svg = render_svg(plan)
    title = plan.spec.title or "Diagram"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-").lower() or "diagram"
    sub = f"{len(plan.nodes)} nodes · {len(plan.edges)} connections"
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    page = (_HTML.replace("__THEME__", "dark" if plan.theme.dark else "light")
            .replace("__TITLE__", _html.escape(title))
            .replace("__SUB__", _html.escape(sub))
            .replace("__FILENAME__", json.dumps(slug + ".svg").replace("</", "<\\/"))
            .replace("__SVG__", svg))
    out.write_text(page, encoding="utf-8")
    return out
