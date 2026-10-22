"""SVG for nodes: outlined shapes with fitted text, and icon/person tiles with a label below."""

from __future__ import annotations

import base64
from pathlib import Path

from visio_mcp.output.svg.canvas import Canvas
from visio_mcp.output.svg.markup import PT, PX, esc, num, snap, stroke_attrs
from visio_mcp.output.svg.shapes import shape
from visio_mcp.output.svg.text import block_h, fit_text, single_line, text_svg
from visio_mcp.style import TextRun
from visio_mcp.plan import PlannedNode
from visio_mcp.style import TextStyle

# fraction of a shape's width (and height, for round shapes) available to text
_INNER = {"decision": 0.55, "hexagon": 0.75, "ellipse": 0.7, "circle": 0.7, "cloud": 0.6,
          "parallelogram": 0.75, "trapezoid": 0.75}
_ROUND_TEXT = {"decision", "hexagon", "ellipse", "circle", "cloud"}
_BOX_TEXT = {"rect", "rounded", "terminator", "subprocess", "note", "document", "cylinder", "queue", "entity"}
ENTITY_BAND = 32.0  # px, header band of an entity (ERD table)

_URI_CACHE: dict[tuple[str, int, int], str] = {}


def node(c: Canvas, n: PlannedNode, idx: int) -> str:
    head = (f'<g id="node-{idx}" class="node" data-id="{esc(n.id)}" data-kind="{esc(n.kind)}" '
            f'data-geometry="{esc(n.geometry)}"{" data-emphasis=\"true\"" if n.emphasis else ""}>')
    x0, y0, x1, y1 = c.box(n.shape)
    if n.geometry in ("icon", "person"):
        return head + _icon_node(c, n, x0, y0, x1, y1) + "</g>"
    if n.geometry == "entity" and len(n.runs) > 1 and y1 - y0 >= 52:
        return head + _entity(n, idx, x0, y0, x1, y1) + "</g>"

    w, h = x1 - x0, y1 - y0
    markup, (tx, ty, tw, th) = shape(n.geometry, x0, y0, x1, y1, n.style, shadow=True)
    if n.geometry in _BOX_TEXT:
        max_w = tw - 20
    else:
        max_w = w * _INNER.get(n.geometry, 0.88) - 6
    max_h = th - 12 if n.geometry not in _ROUND_TEXT else h * _INNER.get(n.geometry, 0.7) * 1.05
    lines = fit_text(n.runs, max(max_w, 24), max_h)
    return head + markup + text_svg(lines, tx + tw / 2, ty + (th - block_h(lines)) / 2) + "</g>"


def _entity(n: PlannedNode, idx: int, x0: float, y0: float, x1: float, y1: float) -> str:
    """ERD table: a tinted header band with the name, the attributes below a divider."""
    st = n.style
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    band = ENTITY_BAND
    markup, _ = shape(n.geometry, x0, y0, x1, y1, st, shadow=True)
    lines = fit_text(n.runs[:1], w - 20, band - 6)
    rest = fit_text(n.runs[1:], w - 24, h - band - 12)
    lcol = st.line or "#64748B"
    out = (f'<g><clipPath id="clip-{idx}"><rect x="{num(x0)}" y="{num(y0)}" width="{num(w)}" height="{num(h)}" '
           f'rx="{num(min(st.rounding * PX, 8))}"/></clipPath>' + markup +
           f'<rect x="{num(x0)}" y="{num(y0)}" width="{num(w)}" height="{num(band)}" fill="{esc(lcol)}" '
           f'fill-opacity="0.14" clip-path="url(#clip-{idx})"/>'
           f'<line x1="{num(x0)}" y1="{num(snap(y0 + band))}" x2="{num(x1)}" y2="{num(snap(y0 + band))}"'
           f'{stroke_attrs(st.line, st.line_weight)}/></g>')
    out += text_svg(lines, cx, y0 + (band - block_h(lines)) / 2)
    out += text_svg(rest, cx, y0 + band + (h - band - block_h(rest)) / 2)
    return out


def _icon_node(c: Canvas, n: PlannedNode, x0: float, y0: float, x1: float, y1: float) -> str:
    st = n.style
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    s = min(w, h)
    col = st.line or "#475569"
    out: list[str] = []
    if n.geometry == "person":
        px0, py0 = cx - s / 2, y0
        out.append(
            f'<g fill="{esc(col)}" stroke="none" filter="url(#shadow)">'
            f'<circle cx="{num(cx)}" cy="{num(py0 + s * 0.28)}" r="{num(s * 0.2)}"/>'
            f'<path d="M{num(px0 + s * 0.12)} {num(py0 + s)}'
            f'C{num(px0 + s * 0.12)} {num(py0 + s * 0.62)} {num(px0 + s * 0.3)} {num(py0 + s * 0.55)} {num(cx)} {num(py0 + s * 0.55)}'
            f'C{num(px0 + s * 0.7)} {num(py0 + s * 0.55)} {num(px0 + s * 0.88)} {num(py0 + s * 0.62)} {num(px0 + s * 0.88)} {num(py0 + s)}Z"/></g>')
    elif n.image is not None and (uri := _image_uri(n.image)):
        out.append(f'<image xmlns:xlink="http://www.w3.org/1999/xlink" x="{num(cx - s / 2)}" y="{num(y0)}" width="{num(s)}" height="{num(s)}" '
                   f'preserveAspectRatio="xMidYMid meet" xlink:href="{uri}"/>')
    else:
        out.append(_tile(n, cx, y0, s, col))
    # label below, inside the node footprint
    fp = n.rect
    runs = [TextRun(r.text, c.readable(r.style, secondary=i > 0)) for i, r in enumerate(n.runs)]
    avail_h = c.Y(fp.bottom) - (y0 + s + 6)
    lines = fit_text(runs, (c.X(fp.right) - c.X(fp.left)) - 4, max(avail_h, 14))
    out.append(text_svg(lines, cx, y0 + s + 6))
    return "".join(out)


def _tile(n: PlannedNode, cx: float, y0: float, s: float, col: str) -> str:
    """A colored rounded square with a white line drawing or a short text glyph."""
    rx = s * 0.18
    tx0, ty0 = snap(cx - s / 2), y0
    out = [f'<rect x="{num(tx0)}" y="{num(ty0)}" width="{num(s)}" height="{num(s)}" rx="{num(rx)}" '
           f'fill="{esc(col)}" stroke="none" filter="url(#shadow)"/>',
           # soft top highlight keeps the tile from looking flat
           f'<rect x="{num(tx0 + 0.5)}" y="{num(ty0 + 0.5)}" width="{num(s - 1)}" height="{num(s - 1)}" rx="{num(rx)}" '
           f'fill="none" stroke="#FFFFFF" stroke-opacity="0.22"/>']
    vec = None if n.glyph else _vector_glyph(n.kind, cx, ty0 + s / 2, s)
    if vec:
        out.append(vec)
        return "".join(out)
    glyph = n.glyph or n.kind.split("-")[-1][:2].upper()
    if glyph:
        gsize = s * (0.40 if len(glyph) <= 1 else 0.34 if len(glyph) == 2 else 0.27)
        gst = TextStyle(font=n.style.text.font, size=gsize / PT, color="#FFFFFF", bold=True)
        gl = single_line(glyph, gst, gsize)
        out.append(text_svg([gl], cx, ty0 + (s - gl.height) / 2))
    return "".join(out)


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
    a = f'fill="none" stroke="#FFFFFF" stroke-width="{num(sw)}" stroke-linecap="round" stroke-linejoin="round"'
    u = s / 100.0

    def R(x: float, y: float, w: float, h: float, r: float = 0) -> str:
        return (f'<rect x="{num(cx + x * u)}" y="{num(cy + y * u)}" width="{num(w * u)}" height="{num(h * u)}" '
                f'rx="{num(r * u)}"/>')

    def L(x1: float, y1: float, x2: float, y2: float) -> str:
        return f'<path d="M{num(cx + x1 * u)} {num(cy + y1 * u)}L{num(cx + x2 * u)} {num(cy + y2 * u)}"/>'

    def Dot(x: float, y: float) -> str:
        return f'<circle cx="{num(cx + x * u)}" cy="{num(cy + y * u)}" r="{num(sw * 0.6)}" fill="#FFFFFF" stroke="none"/>'

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
    else:
        return None
    return f'<g {a}>{body}</g>'
