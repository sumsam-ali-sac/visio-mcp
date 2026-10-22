"""DiagramPlan -> native .vsdx file, no Visio needed (Mac, Linux, CI).

Writes a Visio 2013+ OPC package ([MS-VSDX]) by hand with the standard library:

    [Content_Types].xml
    _rels/.rels
    docProps/app.xml, docProps/core.xml
    visio/document.xml               style sheets, face names, colors
    visio/_rels/document.xml.rels
    visio/windows.xml
    visio/pages/pages.xml            one page, sized to the plan
    visio/pages/_rels/pages.xml.rels
    visio/pages/page1.xml            shapes + connects
    visio/pages/_rels/page1.xml.rels icons (only when the plan has images)
    visio/media/imageN.png           official cloud icons / custom icons, as Foreign shapes

No masters: every shape carries its own Geometry sections, so the file opens the same
everywhere. Nodes, groups and connectors are named like the COM backend names them
(node id, group id, 'source->target'), and connectors are glued to their nodes with
dynamic glue so they stay attached when shapes move in Visio.

Coordinates in the plan already match Visio's: inches, origin bottom-left, center pins.
"""

from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal
from xml.sax.saxutils import escape, quoteattr

from visio_mcp.output.visio.backend import TextRun
from visio_mcp.layout import Rect
from visio_mcp.plan import DiagramPlan, LegendEntry, PlannedEdge, PlannedGroup, PlannedNode, TextBlock
from visio_mcp.style import ShapeStyle, TextStyle, replace, text_width

__all__ = ["write_vsdx"]

# --- OPC / VSDX constants -------------------------------------------------------------------

NS = "http://schemas.microsoft.com/office/visio/2012/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"

REL_DOCUMENT = "http://schemas.microsoft.com/visio/2010/relationships/document"
REL_PAGES = "http://schemas.microsoft.com/visio/2010/relationships/pages"
REL_PAGE = "http://schemas.microsoft.com/visio/2010/relationships/page"
REL_WINDOWS = "http://schemas.microsoft.com/visio/2010/relationships/windows"
REL_CORE = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
REL_APP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"

CT_DOCUMENT = "application/vnd.ms-visio.drawing.main+xml"
CT_PAGES = "application/vnd.ms-visio.pages+xml"
CT_PAGE = "application/vnd.ms-visio.page+xml"
CT_WINDOWS = "application/vnd.ms-visio.windows+xml"
CT_CORE = "application/vnd.openxmlformats-package.core-properties+xml"
CT_APP = "application/vnd.openxmlformats-officedocument.extended-properties+xml"
CT_RELS = "application/vnd.openxmlformats-package.relationships+xml"
CT_PNG = "image/png"

# Style sheet ids in document.xml
STYLE_NONE = 0  # 'No Style': root of every inheritance chain, defines every cell
STYLE_NORMAL = 1
STYLE_CONNECTOR = 2
STYLE_TEXT = 3  # 'Text Only'

ARROW_FILLED = 13  # same arrowhead the COM backend uses
ARROW_SIZE = 2  # medium
LINE_PATTERNS = {"solid": 1, "dashed": 2, "dotted": 3}
H_ALIGN = {"left": 0, "center": 1, "right": 2}
V_TOP, V_MIDDLE, V_BOTTOM = 0, 1, 2

# ObjType: 1 placeable (connectors route around it), 2 routable (a connector),
# 4 neither (backgrounds, frames, decorations: connectors ignore them)
OBJ_PLACEABLE, OBJ_ROUTABLE, OBJ_IGNORE = 1, 2, 4

# Connect parts: begin/end of a 1-D shape glued to the whole target (dynamic glue)
PART_BEGIN, PART_END, PART_WHOLE_SHAPE = 9, 12, 3

ICON_LABEL_GAP = 0.06  # inches between an icon tile and its label below


# --- small helpers ----------------------------------------------------------------------------


def _n(v: float) -> str:
    """Compact number for a V attribute."""
    if abs(v) < 5e-10:
        return "0"
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def _color(c: str | None, default: str = "#000000") -> str:
    c = (c or default).strip()
    if len(c) == 4 and c.startswith("#"):
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c.upper()


def _clean(text: str) -> str:
    """Drop characters XML 1.0 cannot hold; Visio's paragraph separator is LF."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 0x20)


def _attrs(**kw: object) -> str:
    return "".join(f" {k}={quoteattr(str(v))}" for k, v in kw.items() if v is not None)


@dataclass(frozen=True)
class Lin:
    """A geometry coordinate kw*Width + kh*Height + c, written with a formula so the
    shape resizes like a real Visio master."""

    kw: float = 0.0
    kh: float = 0.0
    c: float = 0.0

    def value(self, w: float, h: float) -> float:
        return self.kw * w + self.kh * h + self.c

    def formula(self) -> str | None:
        if not self.kw and not self.kh:
            return None
        parts = []
        if self.kw:
            parts.append(f"Width*{_n(self.kw)}")
        if self.kh:
            parts.append(f"Height*{_n(self.kh)}")
        f = "+".join(parts)
        if self.c:
            f += f"{'+' if self.c > 0 else '-'}{_n(abs(self.c))}"
        return f.replace("+-", "-")


Val = float | int | Lin | tuple  # tuple = (value, formula)


def _cell(name: str, v: object, u: str | None = None, f: str | None = None) -> str:
    if isinstance(v, float):
        v = _n(v)
    return f"<Cell{_attrs(N=name, V=v, U=u, F=f)}/>"


def _len(name: str, inches: float, f: str | None = None) -> str:
    return _cell(name, float(inches), None, f)


def _pt(name: str, points: float) -> str:
    """A length shown in points; V is always inches."""
    return _cell(name, points / 72.0, "PT")


# --- geometry -------------------------------------------------------------------------------


@dataclass
class Section:
    rows: list[tuple[str, dict[str, Val]]]
    no_fill: bool = False
    no_line: bool = False


def W(k: float = 1.0, c: float = 0.0) -> Lin:
    return Lin(kw=k, c=c)


def H(k: float = 1.0, c: float = 0.0) -> Lin:
    return Lin(kh=k, c=c)


def _poly(pts: list[tuple[Val, Val]], no_fill: bool = False, closed: bool = True) -> Section:
    rows = [("MoveTo", {"X": pts[0][0], "Y": pts[0][1]})]
    rows += [("LineTo", {"X": x, "Y": y}) for x, y in pts[1:]]
    if closed:
        rows.append(("LineTo", {"X": pts[0][0], "Y": pts[0][1]}))
    return Section(rows, no_fill=no_fill)


def _rect() -> Section:
    return _poly([(0.0, 0.0), (W(), 0.0), (W(), H()), (0.0, H())])


def _ellipse(cx: Val, cy: Val, ax: Val, ay: Val, bx: Val, by: Val, no_fill: bool = False) -> Section:
    """Ellipse row: center, end of one axis, end of the other axis."""
    return Section([("Ellipse", {"X": cx, "Y": cy, "A": ax, "B": ay, "C": bx, "D": by})], no_fill=no_fill)


def _earc(x: Val, y: Val, ax: Val, ay: Val, ratio: float) -> tuple[str, dict[str, Val]]:
    """EllipticalArcTo to (x, y) through (ax, ay); ratio = x-radius / y-radius."""
    return ("EllipticalArcTo", {"X": x, "Y": y, "A": ax, "B": ay, "C": 0.0, "D": ratio})


def _rounded_rect(r: float, w: float, h: float) -> Section:
    """Rectangle with corners drawn as real quarter circles (renders identically in every
    viewer, unlike the Rounding cell which some importers ignore)."""
    r = max(0.0, min(r, w / 2, h / 2))
    if r < 1e-3:
        return _rect()
    k = 1 - math.sqrt(0.5)  # arc midpoint inset from the corner, as a fraction of r
    rows: list[tuple[str, dict[str, Val]]] = [
        ("MoveTo", {"X": r, "Y": 0.0}),
        ("LineTo", {"X": W(1, -r), "Y": 0.0}),
        _earc(W(), r, W(1, -r * k), r * k, 1.0),
        ("LineTo", {"X": W(), "Y": H(1, -r)}),
        _earc(W(1, -r), H(), W(1, -r * k), H(1, -r * k), 1.0),
        ("LineTo", {"X": r, "Y": H()}),
        _earc(0.0, H(1, -r), r * k, H(1, -r * k), 1.0),
        ("LineTo", {"X": 0.0, "Y": r}),
        _earc(r, 0.0, r * k, r * k, 1.0),
    ]
    return Section(rows)


def geometry(kind: str, w: float, h: float, rounding: float = 0.0) -> list[Section]:
    """Geometry sections for a node geometry (style.GEOMETRY_MIN keys) in a w x h box."""
    if kind == "rounded":
        return [_rounded_rect(rounding or 0.08, w, h)]
    if kind == "rect":
        return [_rounded_rect(rounding, w, h)] if rounding else [_rect()]
    if kind == "terminator":
        r = h / 2
        return [Section([
            ("MoveTo", {"X": H(0.5), "Y": 0.0}),
            ("LineTo", {"X": Lin(1, -0.5), "Y": 0.0}),
            _earc(Lin(1, -0.5), H(), W(), H(0.5), 1.0),
            ("LineTo", {"X": H(0.5), "Y": H()}),
            _earc(H(0.5), 0.0, 0.0, H(0.5), 1.0),
        ])] if w >= 2 * r else [_ellipse(W(0.5), H(0.5), W(), H(0.5), W(0.5), H())]
    if kind == "decision":
        return [_poly([(W(0.5), 0.0), (W(), H(0.5)), (W(0.5), H()), (0.0, H(0.5))])]
    if kind == "parallelogram":
        s = min(0.2 * w, 0.6 * h, 0.3)
        return [_poly([(0.0, 0.0), (W(1, -s), 0.0), (W(), H()), (s, H())])]
    if kind == "trapezoid":  # manual operation: wide top
        s = min(0.15 * w, 0.5 * h, 0.3)
        return [_poly([(s, 0.0), (W(1, -s), 0.0), (W(), H()), (0.0, H())])]
    if kind == "hexagon":
        s = min(0.2 * w, 0.35 * h, 0.3)
        return [_poly([(s, 0.0), (W(1, -s), 0.0), (W(), H(0.5)), (W(1, -s), H()), (s, H()), (0.0, H(0.5))])]
    if kind in ("ellipse", "circle"):
        return [_ellipse(W(0.5), H(0.5), W(), H(0.5), W(0.5), H())]
    if kind == "document":
        b = min(0.12 * h, 0.12)  # wave baseline
        a = b * 0.9
        return [Section([
            ("MoveTo", {"X": 0.0, "Y": b}),
            ("LineTo", {"X": 0.0, "Y": H()}),
            ("LineTo", {"X": W(), "Y": H()}),
            ("LineTo", {"X": W(), "Y": b}),
            _earc(W(0.5), b, W(0.75), b - a, (w / 4) / a),
            _earc(0.0, b, W(0.25), b + a, (w / 4) / a),
        ])]
    # Visio fills overlapping geometry sections alternately (overlaps become holes), so
    # caps and bodies share an edge instead of overlapping
    if kind == "cylinder":
        ry = min(0.14 * h, 0.16 * w, 0.16)
        ratio = (w / 2) / ry
        body = Section([
            ("MoveTo", {"X": 0.0, "Y": H(1, -ry)}),
            ("LineTo", {"X": 0.0, "Y": ry}),
            _earc(W(), ry, W(0.5), 0.0, ratio),
            ("LineTo", {"X": W(), "Y": H(1, -ry)}),
            _earc(0.0, H(1, -ry), W(0.5), H(1, -2 * ry), ratio),
        ])
        top = _ellipse(W(0.5), H(1, -ry), W(), H(1, -ry), W(0.5), H())
        return [body, top]
    if kind == "queue":
        rx = min(0.1 * w, 0.25 * h, 0.16)
        ratio = rx / (h / 2)
        body = Section([
            ("MoveTo", {"X": rx, "Y": H()}),
            _earc(rx, 0.0, 0.0, H(0.5), ratio),
            ("LineTo", {"X": W(1, -rx), "Y": 0.0}),
            _earc(W(1, -rx), H(), W(1, -2 * rx), H(0.5), ratio),
            ("LineTo", {"X": rx, "Y": H()}),
        ])
        cap = _ellipse(W(1, -rx), H(0.5), W(), H(0.5), W(1, -rx), H())
        return [body, cap]
    if kind == "cloud":
        return [_cloud(w, h)]
    if kind == "note":
        f = min(0.2 * min(w, h), 0.2)
        body = _poly([(0.0, 0.0), (W(), 0.0), (W(), H(1, -f)), (W(1, -f), H()), (0.0, H())])
        fold = _poly([(W(1, -f), H()), (W(1, -f), H(1, -f)), (W(), H(1, -f))], no_fill=True, closed=False)
        return [body, fold]
    if kind == "subprocess":
        d = min(0.1, 0.08 * w)
        bars = [
            Section([("MoveTo", {"X": d, "Y": 0.0}), ("LineTo", {"X": d, "Y": H()})], no_fill=True),
            Section([("MoveTo", {"X": W(1, -d), "Y": 0.0}), ("LineTo", {"X": W(1, -d), "Y": H()})], no_fill=True),
        ]
        return [_rounded_rect(min(rounding, 0.04), w, h), *bars]
    if kind == "person":
        r = 0.2 * min(w, h)
        cy = h - r - 0.04 * h
        body = Section([
            ("MoveTo", {"X": W(0.1), "Y": 0.0}),
            ("LineTo", {"X": W(0.1), "Y": H(0.18)}),
            _earc(W(0.9), H(0.18), W(0.5), H(0.52), (0.4 * w) / (0.34 * h)),
            ("LineTo", {"X": W(0.9), "Y": 0.0}),
            ("LineTo", {"X": W(0.1), "Y": 0.0}),
        ])
        head = _ellipse(W(0.5), cy, W(0.5, r), cy, W(0.5), cy + r)
        return [body, head]
    if kind == "icon":
        return [_rounded_rect(min(0.14, w * 0.2), w, h)]
    if kind == "entity":
        return [_rounded_rect(rounding, w, h)]  # header divider added by the caller
    return [_rounded_rect(rounding, w, h)] if rounding else [_rect()]


def _cloud(w: float, h: float) -> Section:
    """Puffy cloud: arcs bulging outward between points on an inner ellipse."""
    n = 9
    cx, cy, rx, ry = w / 2, h / 2, w / 2 * 0.86, h / 2 * 0.78
    pts = []
    for i in range(n):
        t = math.pi * 1.5 + 2 * math.pi * i / n  # start at the bottom
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    rows: list[tuple[str, dict[str, Val]]] = [("MoveTo", {"X": W(pts[0][0] / w), "Y": H(pts[0][1] / h)})]
    for i in range(1, n + 1):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i % n]
        chord = math.hypot(x1 - x0, y1 - y0)
        bulge = 0.42 * chord * (1.15 if i % 2 else 0.9)
        # counterclockwise around the center: the outside is on the right of the direction
        rows.append(("ArcTo", {"X": W(x1 / w), "Y": H(y1 / h), "A": bulge}))
    return Section(rows)


def _geometry_xml(sections: list[Section], w: float, h: float, start_ix: int = 0) -> str:
    out = []
    for i, sec in enumerate(sections):
        cells = [
            _cell("NoFill", 1 if sec.no_fill else 0),
            _cell("NoLine", 1 if sec.no_line else 0),
            _cell("NoShow", 0),
            _cell("NoSnap", 0),
            _cell("NoQuickDrag", 0),
        ]
        for ix, (t, vals) in enumerate(sec.rows, start=1):
            cs = []
            for k, v in vals.items():
                if isinstance(v, Lin):
                    cs.append(_cell(k, float(v.value(w, h)), None, v.formula()))
                elif isinstance(v, tuple):
                    cs.append(_cell(k, float(v[0]), None, v[1]))
                else:
                    cs.append(_cell(k, float(v)))
            cells.append(f'<Row T="{t}" IX="{ix}">{"".join(cs)}</Row>')
        out.append(f'<Section N="Geometry" IX="{start_ix + i}">{"".join(cells)}</Section>')
    return "".join(out)


# --- text ---------------------------------------------------------------------------------


def _char_row(ix: int, st: TextStyle) -> str:
    style = (1 if st.bold else 0) | (2 if st.italic else 0)
    return (
        f'<Row IX="{ix}">'
        + _cell("Font", st.font)
        + _cell("Color", _color(st.color))
        + _cell("Style", style)
        + _cell("Case", 0)
        + _cell("Pos", 0)
        + _cell("FontScale", 1)
        + _pt("Size", st.size)
        + _cell("ColorTrans", 0)
        + "</Row>"
    )


def _text_xml(runs: list[TextRun], align: str = "center") -> tuple[str, str]:
    """(Character + Paragraph sections, <Text> element) for styled runs."""
    runs = [r for r in runs if r.text]
    if not runs:
        return "", ""
    styles: list[TextStyle] = []
    for r in runs:
        if r.style not in styles:
            styles.append(r.style)
    char = '<Section N="Character">' + "".join(_char_row(i, s) for i, s in enumerate(styles)) + "</Section>"
    para = (
        '<Section N="Paragraph"><Row IX="0">'
        + _cell("IndFirst", 0.0) + _cell("IndLeft", 0.0) + _cell("IndRight", 0.0)
        + _cell("SpLine", -1.1) + _cell("SpBefore", 0.0) + _cell("SpAfter", 0.0)
        + _cell("HorzAlign", H_ALIGN.get(align, 1)) + _cell("Bullet", 0)
        + "</Row></Section>"
    )
    body = ['<pp IX="0"/>']
    for r in runs:
        body.append(f'<cp IX="{styles.index(r.style)}"/>{escape(_clean(r.text))}')
    return char + para, "<Text>" + "".join(body) + "</Text>"


def _text_height(runs: list[TextRun]) -> float:
    """Rough height of runs in inches (each paragraph sized by its largest run)."""
    h, line = 0.0, 0.0
    for r in runs:
        parts = r.text.split("\n")
        for j, _ in enumerate(parts):
            if j > 0:
                h += line
                line = 0.0
            line = max(line, r.style.size * 1.2 / 72)
    return h + line


# --- shapes -------------------------------------------------------------------------------


@dataclass
class _Shape:
    """One <Shape> being assembled."""

    id: int
    name: str
    style: int = STYLE_NORMAL
    cells: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    text: str = ""
    type: Literal["Shape", "Group", "Foreign"] = "Shape"
    children: list["_Shape"] = field(default_factory=list)
    foreign: str = ""  # <ForeignData> of a picture shape

    def xml(self) -> str:
        a = _attrs(ID=self.id, NameU=self.name, Name=self.name, IsCustomNameU=1, IsCustomName=1,
                   Type=self.type, LineStyle=self.style, FillStyle=self.style, TextStyle=self.style)
        kids = ""
        if self.children:
            kids = "<Shapes>" + "".join(c.xml() for c in self.children) + "</Shapes>"
        return f"<Shape{a}>{''.join(self.cells)}{''.join(self.sections)}{self.text}{self.foreign}{kids}</Shape>"


def _xform(x: float, y: float, w: float, h: float) -> list[str]:
    return [
        _len("PinX", x), _len("PinY", y), _len("Width", w), _len("Height", h),
        _len("LocPinX", w / 2, "Width*0.5"), _len("LocPinY", h / 2, "Height*0.5"),
        _cell("Angle", 0.0), _cell("FlipX", 0), _cell("FlipY", 0), _cell("ResizeMode", 0),
    ]


def _line_cells(style: ShapeStyle) -> list[str]:
    if not style.line:
        return [_cell("LinePattern", 0), _pt("LineWeight", 0.75), _cell("LineColor", "#000000")]
    return [
        _pt("LineWeight", style.line_weight),
        _cell("LineColor", _color(style.line)),
        _cell("LinePattern", LINE_PATTERNS.get(style.line_pattern, 1)),
        _len("Rounding", 0.0),
        _cell("LineCap", 0),
        _cell("BeginArrow", 0),
        _cell("EndArrow", 0),
    ]


def _fill_cells(style: ShapeStyle) -> list[str]:
    if not style.fill:
        return [_cell("FillPattern", 0), _cell("FillForegnd", "#FFFFFF")]
    cells = [_cell("FillForegnd", _color(style.fill)), _cell("FillBkgnd", _color(style.fill)),
             _cell("FillPattern", 1), _cell("FillForegndTrans", 0), _cell("FillBkgndTrans", 0)]
    if style.shadow:
        cells += [_cell("ShdwForegnd", "#000000"), _cell("ShdwForegndTrans", 0.82), _cell("ShdwPattern", 1),
                  _cell("ShapeShdwType", 1), _len("ShapeShdwOffsetX", 0.03), _len("ShapeShdwOffsetY", -0.03)]
    else:
        cells.append(_cell("ShdwPattern", 0))
    return cells


def _text_block(w: float, h: float, *, valign: int = V_MIDDLE, margins_pt: tuple[float, float, float, float]
                = (4, 4, 2, 2), bkgnd: str | None = None, txt: tuple[float, float, float, float] | None = None,
                txt_f: tuple[str | None, str | None, str | None, str | None] | None = None) -> list[str]:
    """Text block cells. txt = (TxtPinX, TxtPinY, TxtWidth, TxtHeight) in local inches; default
    is the whole shape."""
    left, right, top, bottom = margins_pt
    if txt is None:
        txt = (w / 2, h / 2, w, h)
        txt_f = ("Width*0.5", "Height*0.5", "Width*1", "Height*1")
    txt_f = txt_f or (None, None, None, None)
    tx, ty, tw, th = txt
    return [
        _pt("LeftMargin", left), _pt("RightMargin", right), _pt("TopMargin", top), _pt("BottomMargin", bottom),
        _cell("VerticalAlign", valign),
        *([_cell("TextBkgnd", _color(bkgnd)), _cell("TextBkgndTrans", 0)] if bkgnd else []),
        _cell("TextDirection", 0),
        _len("TxtPinX", tx, txt_f[0]), _len("TxtPinY", ty, txt_f[1]),
        _len("TxtWidth", tw, txt_f[2]), _len("TxtHeight", th, txt_f[3]),
        _len("TxtLocPinX", tw / 2, "TxtWidth*0.5"), _len("TxtLocPinY", th / 2, "TxtHeight*0.5"),
        _cell("TxtAngle", 0.0),
    ]


def _user_section(rows: dict[str, tuple[str, str | None, str | None]]) -> str:
    """User-defined cells: name -> (value, unit, formula)."""
    out = []
    for name, (v, u, f) in rows.items():
        out.append(f'<Row N="{name}">{_cell("Value", v, u, f)}{_cell("Prompt", "", "STR")}</Row>')
    return '<Section N="User">' + "".join(out) + "</Section>"


class _Page:
    def __init__(self) -> None:
        self.shapes: list[_Shape] = []
        self.connects: list[str] = []
        self.ids: dict[str, int] = {}  # shape name -> id (top-level, addressable)
        self._next = 1
        self.fonts: list[str] = []
        self.pngs: dict[Path, Path | None] = {}  # node image -> bitmap to embed (None: draw the glyph tile)
        self.media: dict[Path, tuple[str, str]] = {}  # bitmap -> (rel id, part name 'imageN.png')

    def new_id(self) -> int:
        i = self._next
        self._next += 1
        return i

    def font(self, name: str) -> None:
        if name not in self.fonts:
            self.fonts.append(name)

    def fonts_of(self, runs: Iterable[TextRun]) -> None:
        for r in runs:
            self.font(r.style.font)

    def add(self, shape: _Shape) -> _Shape:
        self.shapes.append(shape)
        self.ids[shape.name] = shape.id
        return shape

    # --- primitives ---------------------------------------------------------------------

    def box(self, name: str, r: Rect, style: ShapeStyle, geom: str = "rect", runs: list[TextRun] | None = None,
            align: str = "center", valign: int = V_MIDDLE, obj: int = OBJ_PLACEABLE, rounding: float | None = None,
            margins_pt: tuple[float, float, float, float] = (4, 4, 2, 2)) -> _Shape:
        s = _Shape(self.new_id(), name)
        s.cells += _xform(r.x, r.y, r.w, r.h)
        s.cells += _line_cells(style) + _fill_cells(style)
        s.cells.append(_cell("ObjType", obj))
        s.cells += _text_block(r.w, r.h, valign=valign, margins_pt=margins_pt)
        rnd = style.rounding if rounding is None else rounding
        s.sections.append(_geometry_xml(geometry(geom, r.w, r.h, rnd), r.w, r.h))
        if runs:
            self.fonts_of(runs)
            sec, txt = _text_xml(runs, align)
            s.sections.insert(0, sec)
            s.text = txt
        return s

    def text(self, name: str, r: Rect, runs: list[TextRun], align: str = "left",
             valign: int = V_MIDDLE) -> _Shape:
        s = _Shape(self.new_id(), name, style=STYLE_TEXT)
        s.cells += _xform(r.x, r.y, r.w, r.h)
        s.cells += [_cell("LinePattern", 0), _cell("FillPattern", 0), _cell("ObjType", OBJ_IGNORE)]
        s.cells += _text_block(r.w, r.h, valign=valign, margins_pt=(0, 0, 0, 0))
        sec = Section(_rect().rows, no_fill=True, no_line=True)
        s.sections.append(_geometry_xml([sec], r.w, r.h))
        self.fonts_of(runs)
        chars, txt = _text_xml(runs, align)
        s.sections.insert(0, chars)
        s.text = txt
        return s

    def picture(self, name: str, r: Rect, png: Path) -> _Shape:
        """A Foreign (picture) shape showing png, fitted into r keeping its aspect ratio."""
        if png not in self.media:
            n = len(self.media) + 1
            self.media[png] = (f"rId{n}", f"image{n}.png")
        rid = self.media[png][0]
        iw, ih = _png_size(png)
        k = min(r.w / iw, r.h / ih) if iw and ih else 1.0
        w, h = (iw * k, ih * k) if iw and ih else (r.w, r.h)
        s = _Shape(self.new_id(), name, style=STYLE_TEXT, type="Foreign")
        s.cells += _xform(r.x, r.y, w, h)
        # transparent PNGs: no fill or line behind the picture (renderers fall back to the style's)
        s.sections.append(_geometry_xml([Section(_rect().rows, no_fill=True, no_line=True)], w, h))
        s.cells += [_cell("LinePattern", 0), _cell("FillPattern", 0), _cell("ShdwPattern", 0),
                    _cell("ObjType", OBJ_IGNORE),
                    _len("ImgOffsetX", 0.0, "ImgWidth*0"), _len("ImgOffsetY", 0.0, "ImgHeight*0"),
                    _len("ImgWidth", w, "Width*1"), _len("ImgHeight", h, "Height*1"),
                    _cell("LockAspect", 1)]
        s.foreign = f'<ForeignData ForeignType="Bitmap" CompressionType="PNG"><Rel r:id="{rid}"/></ForeignData>'
        return s

    def line(self, name: str, pts: list[tuple[float, float]], color: str, weight_pt: float, pattern: str,
             arrow: str, rounding: float = 0.0, routable: bool = False, arrow_size: int = ARROW_SIZE) -> _Shape:
        """A 1-D shape following pts (page inches): connector-style transform, begin at local (0, 0)."""
        (bx, by), (ex, ey) = pts[0], pts[-1]
        w, h = ex - bx, ey - by
        s = _Shape(self.new_id(), name, style=STYLE_CONNECTOR)
        s.cells += [
            _len("PinX", (bx + ex) / 2, "GUARD((BeginX+EndX)/2)"),
            _len("PinY", (by + ey) / 2, "GUARD((BeginY+EndY)/2)"),
            _len("Width", w, "GUARD(EndX-BeginX)"),
            _len("Height", h, "GUARD(EndY-BeginY)"),
            _len("LocPinX", w / 2, "GUARD(Width*0.5)"),
            _len("LocPinY", h / 2, "GUARD(Height*0.5)"),
            _cell("Angle", 0.0, None, "GUARD(0DEG)"),
            _cell("FlipX", 0, None, "GUARD(FALSE)"),
            _cell("FlipY", 0, None, "GUARD(FALSE)"),
            _cell("ResizeMode", 0),
            _len("BeginX", bx), _len("BeginY", by), _len("EndX", ex), _len("EndY", ey),
            _pt("LineWeight", weight_pt),
            _cell("LineColor", _color(color)),
            _cell("LinePattern", LINE_PATTERNS.get(pattern, 1)),
            _len("Rounding", rounding),
            _cell("BeginArrow", ARROW_FILLED if arrow == "both" else 0),
            _cell("EndArrow", 0 if arrow == "none" else ARROW_FILLED),
            _cell("BeginArrowSize", arrow_size),
            _cell("EndArrowSize", arrow_size),
            _cell("LineCap", 0),
            _cell("FillPattern", 0),
            _cell("ObjType", OBJ_ROUTABLE if routable else OBJ_IGNORE),
        ]
        rows: list[tuple[str, dict[str, Val]]] = [("MoveTo", {"X": 0.0, "Y": 0.0})]
        for x, y in pts[1:]:
            rows.append(("LineTo", {"X": x - bx, "Y": y - by}))
        s.sections.append(_geometry_xml([Section(rows, no_fill=True)], w, h))
        return s


# --- drawing the plan ---------------------------------------------------------------------


def _draw_background(page: _Page, plan: DiagramPlan) -> None:
    r = Rect(plan.width / 2, plan.height / 2, plan.width, plan.height)
    s = page.box("__background", r, ShapeStyle(fill=plan.theme.background, line=None), obj=OBJ_IGNORE)
    s.cells += [_cell(c, 1) for c in ("LockMoveX", "LockMoveY", "LockWidth", "LockHeight", "LockRotate",
                                      "LockDelete", "LockSelect", "LockTextEdit")]
    page.add(s)


def _draw_group(page: _Page, g: PlannedGroup) -> None:
    st = g.style
    header = [TextRun(g.label, st.header)] if g.label else []
    pad_top = max(2.0, (st.header_height * 72 - st.header.size * 1.2) / 2)
    s = page.box(g.id, g.rect, st.shape, "rect", header, align="left", valign=V_TOP, obj=OBJ_IGNORE,
                 margins_pt=(9, 9, pad_top, 4))
    # a real Visio container (custom containers only need User.msvStructureType); members are
    # not pre-registered, Visio adds shapes to it as they are moved or dropped
    s.sections.insert(0, _user_section({
        "msvStructureType": ("Container", "STR", '"Container"'),
        "msvSDContainerMargin": (_n(min(st.padding, 0.25)), "IN", None),
        "msvSDContainerResize": ("0", None, None),
    }))
    page.add(s)


def _label_below(n: PlannedNode) -> tuple[float, float, float, float]:
    """Text block under an icon/person shape, inside the node footprint (local coords)."""
    s, r = n.shape, n.rect
    top = s.bottom - ICON_LABEL_GAP
    bottom = min(r.bottom, top - _text_height(n.runs) - 0.04)
    th = max(0.2, top - bottom)
    tw = max(r.w, s.w)
    return (s.w / 2, (top - th / 2) - s.bottom, tw, th)


def _luma(color: str) -> float:
    c = _color(color)
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return (r * 299 + g * 587 + b * 114) / 1000


def _readable_below(runs: list[TextRun], plan: DiagramPlan) -> list[TextRun]:
    """A label under an icon sits on the page, not the shape: text styled for a dark node fill
    (C4 people: white) would vanish, so it takes the page's text colors instead."""
    bg = _luma(plan.theme.background)
    out = []
    for i, r in enumerate(runs):
        if abs(_luma(r.style.color) - bg) < 90:
            color = plan.theme.title.color if i == 0 else plan.theme.subtitle.color
            r = TextRun(r.text, replace(r.style, color=color))
        out.append(r)
    return out


def _glyph(n: PlannedNode) -> str:
    if n.glyph:
        return n.glyph
    words = [w for w in n.label.split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def _png_size(path: Path) -> tuple[int, int]:
    """Pixel size from a PNG header ((0, 0) when unreadable)."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except OSError:
        pass
    return 0, 0


def _draw_node(page: _Page, plan: DiagramPlan, n: PlannedNode) -> None:
    st, sh = n.style, n.shape
    geom = n.geometry
    below = geom in ("icon", "person") or n.icon
    runs = _readable_below(n.runs, plan) if below else n.runs
    png = page.pngs.get(n.image) if n.image is not None else None
    if geom == "icon" and png is not None:
        # an invisible frame (glue target, label below) grouping the picture
        s = page.box(n.id, sh, replace(st, fill=None, line=None, shadow=False), "rect")
    elif geom == "icon":
        tile = replace(st, fill=st.line or st.fill or "#64748B", line=None, line_weight=0)
        s = page.box(n.id, sh, tile, "icon")
    else:
        s = page.box(n.id, sh, st, geom, valign=V_TOP if geom == "entity" else V_MIDDLE)
        if geom == "entity" and n.runs:
            band = sh.h - min(sh.h * 0.5, n.runs[0].style.size * 1.3 / 72 + 0.14)
            sec = Section([("MoveTo", {"X": 0.0, "Y": H(1, band - sh.h)}),
                           ("LineTo", {"X": W(), "Y": H(1, band - sh.h)})], no_fill=True)
            s.sections.append(_geometry_xml([sec], sh.w, sh.h, start_ix=1))
    page.fonts_of(runs)
    chars, txt = _text_xml(runs, "center")
    s.sections.insert(0, chars)
    s.text = txt
    if below:
        tx, ty, tw, th = _label_below(n)
        # replace the default whole-shape text block with one under the shape
        s.cells = [c for c in s.cells if not c.startswith(('<Cell N="Txt', '<Cell N="VerticalAlign"'))]
        s.cells += [_cell("VerticalAlign", V_TOP),
                    _len("TxtPinX", tx, "Width*0.5"), _len("TxtPinY", ty, _n(ty)),
                    _len("TxtWidth", tw), _len("TxtHeight", th),
                    _len("TxtLocPinX", tw / 2, "TxtWidth*0.5"), _len("TxtLocPinY", th / 2, "TxtHeight*0.5"),
                    _cell("TxtAngle", 0.0)]
    if geom == "icon":
        # glyph (or picture) rides along inside a group, so it and the label move as one node
        s.type = "Group"
        s.cells += [_cell("SelectMode", 0), _cell("DisplayMode", 2), _cell("IsTextEditTarget", 1),
                    _cell("IsSnapTarget", 1), _cell("DontMoveChildren", 0)]
    if geom == "icon" and png is not None:
        pic = page.picture(f"__icon_{n.id}", Rect(sh.w / 2, sh.h / 2, sh.w, sh.h), png)
        pic.cells += [_cell("LockSelect", 1), _cell("LockTextEdit", 1)]
        s.children.append(pic)
        page.add(s)
        return
    if geom == "icon":
        glyph = _glyph(n)
        size = 16 if len(glyph) <= 1 else 13 if len(glyph) == 2 else 10
        size = min(size, sh.h * 72 * 0.38)
        gst = TextStyle(font=st.text.font, size=size, color="#FFFFFF", bold=True)
        child = page.text(f"__glyph_{n.id}", Rect(sh.w / 2, sh.h / 2, sh.w, sh.h), [TextRun(glyph, gst)],
                          align="center")
        child.cells += [_cell("LockSelect", 1), _cell("LockTextEdit", 1)]
        s.children.append(child)
    page.add(s)


def _route(plan: DiagramPlan, e: PlannedEdge) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in e.points]
    if len(pts) < 2:
        a, b = plan.node(e.source).shape, plan.node(e.target).shape
        pts = [(a.x, a.y), (b.x, b.y)]
    out = [pts[0]]
    for p in pts[1:]:  # drop repeated points (zero-length segments confuse renderers)
        if abs(p[0] - out[-1][0]) > 1e-6 or abs(p[1] - out[-1][1]) > 1e-6:
            out.append(p)
    if len(out) < 2:
        out.append((out[0][0] + 1e-3, out[0][1]))
    return out


def _midpoint(pts: list[tuple[float, float]]) -> tuple[float, float]:
    segs = [(a, b, math.dist(a, b)) for a, b in zip(pts, pts[1:])]
    half = sum(s[2] for s in segs) / 2
    for a, b, d in segs:
        if half <= d and d > 0:
            t = half / d
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        half -= d
    return pts[-1]


def _draw_edge(page: _Page, plan: DiagramPlan, e: PlannedEdge) -> None:
    pts = _route(plan, e)
    st = e.style
    s = page.line(e.name, pts, e.color, st.weight, e.pattern, e.arrow, rounding=st.corner, routable=True)
    src, dst = page.ids.get(e.source), page.ids.get(e.target)
    # dynamic glue: endpoints follow the shapes (Visio's own connector formulas)
    s.cells = [c for c in s.cells if not c.startswith(('<Cell N="BeginX"', '<Cell N="BeginY"',
                                                        '<Cell N="EndX"', '<Cell N="EndY"'))]
    (bx, by), (ex, ey) = pts[0], pts[-1]
    if src is not None and dst is not None:
        s.cells += [
            _len("BeginX", bx, "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"),
            _len("BeginY", by, "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"),
            _len("EndX", ex, "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"),
            _len("EndY", ey, "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"),
            _cell("BegTrigger", 2, None, f"_XFTRIGGER(Sheet.{src}!EventXFMod)"),
            _cell("EndTrigger", 2, None, f"_XFTRIGGER(Sheet.{dst}!EventXFMod)"),
        ]
    else:
        s.cells += [_len("BeginX", bx), _len("BeginY", by), _len("EndX", ex), _len("EndY", ey)]
    s.cells += [
        _cell("ShapeRouteStyle", 1),  # right angle
        _cell("ConFixedCode", 1),  # keep our route; reroute only when a glued shape moves
        _cell("ConLineJumpCode", 1),  # no line jumps (the preview has none)
        _cell("ConLineRouteExt", 1),  # straight segments
        _cell("GlueType", 0),
        _cell("WalkPreference", 0),
    ]
    if e.label:
        runs = [TextRun(e.label, st.text)]
        mx, my = _midpoint(pts)
        tw = max(text_width(line, st.text.size, st.text.bold) for line in e.label.split("\n")) * 1.2 + 0.18
        th = _text_height(runs) + 0.06
        s.cells += _text_block(0, 0, valign=V_MIDDLE, margins_pt=(2, 2, 1, 1), bkgnd=st.label_bg,
                               txt=(mx - bx, my - by, tw, th), txt_f=(None, None, None, None))
        page.fonts_of(runs)
        chars, txt = _text_xml(runs, "center")
        s.sections.insert(0, chars)
        s.text = txt
    page.add(s)
    if src is not None:
        page.connects.append(f'<Connect{_attrs(FromSheet=s.id, FromCell="BeginX", FromPart=PART_BEGIN, ToSheet=src, ToCell="PinX", ToPart=PART_WHOLE_SHAPE)}/>')
    if dst is not None:
        page.connects.append(f'<Connect{_attrs(FromSheet=s.id, FromCell="EndX", FromPart=PART_END, ToSheet=dst, ToCell="PinX", ToPart=PART_WHOLE_SHAPE)}/>')


def _draw_title(page: _Page, title: TextBlock) -> None:
    page.add(page.text("__title", title.rect, title.runs, title.align))


def _draw_legend(page: _Page, plan: DiagramPlan) -> None:
    theme, frame = plan.theme, plan.legend
    assert frame is not None
    page.add(page.box("__legend", frame, theme.legend, "rect", obj=OBJ_IGNORE))
    if plan.legend_title:
        t = plan.legend_title
        page.add(page.text("__legend_title", t.rect, t.runs, t.align))
    text_style = replace(theme.legend.text, size=9)
    for i, (sample, text, entry) in enumerate(plan.legend_entries):
        name = f"__legend_{i}"
        page.add(_legend_sample(page, f"{name}_sample", sample, entry, plan))
        page.add(page.text(f"{name}_text", text, [TextRun(entry.label, text_style)], "left"))


def _legend_sample(page: _Page, name: str, r: Rect, entry: LegendEntry, plan: DiagramPlan) -> _Shape:
    theme = plan.theme
    if entry.sample == "edge":
        return page.line(name, [(r.left, r.y), (r.right, r.y)], entry.color or theme.edge.color,
                         theme.edge.weight, entry.pattern, "end", arrow_size=1)
    style = entry.style or ShapeStyle()
    if entry.sample == "group":
        return page.box(name, r, replace(style, rounding=min(style.rounding, 0.04)), "rect", obj=OBJ_IGNORE)
    geom = entry.geometry if entry.geometry not in ("icon", "person") else "rounded"
    rnd = min(style.rounding, 0.05)
    if geom == "icon":
        style = replace(style, fill=style.line, line=None)
    return page.box(name, r, style, geom, obj=OBJ_IGNORE, rounding=rnd)


# --- package parts ----------------------------------------------------------------------------

_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _page_xml(page: _Page) -> str:
    connects = f"<Connects>{''.join(page.connects)}</Connects>" if page.connects else ""
    return (f'{_XML}<PageContents xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">'
            f"<Shapes>{''.join(s.xml() for s in page.shapes)}</Shapes>{connects}</PageContents>")


def _pages_xml(plan: DiagramPlan) -> str:
    w, h = plan.width, plan.height
    sheet = "".join([
        _len("PageWidth", w), _len("PageHeight", h),
        _len("ShdwOffsetX", 0.125), _len("ShdwOffsetY", -0.125),
        _cell("PageScale", 1.0, "IN_F"), _cell("DrawingScale", 1.0, "IN_F"),
        _cell("DrawingSizeType", 3),  # custom size
        _cell("DrawingScaleType", 0),
        _cell("InhibitSnap", 0), _cell("PageLockReplace", 0, "BOOL"), _cell("PageLockDuplicate", 0, "BOOL"),
        _cell("UIVisibility", 0), _cell("ShdwType", 0), _cell("ShdwObliqueAngle", 0.0),
        _cell("ShdwScaleFactor", 1.0), _cell("DrawingResizeType", 2),  # keep our size
        _cell("PageShapeSplit", 1),
        _cell("PrintPageOrientation", 2 if w > h else 1),
        _cell("LineJumpCode", 0),  # no line jumps on this page
        _cell("RouteStyle", 1),
        _len("PageLeftMargin", 0.25), _len("PageRightMargin", 0.25),
        _len("PageTopMargin", 0.25), _len("PageBottomMargin", 0.25),
    ])
    page = (f'<Page{_attrs(ID=0, NameU="Page-1", Name="Page-1", ViewScale=-1, ViewCenterX=_n(w / 2), ViewCenterY=_n(h / 2))}>'
            f'<PageSheet LineStyle="0" FillStyle="0" TextStyle="0">{sheet}</PageSheet>'
            f'<Rel r:id="rId1"/></Page>')
    return f'{_XML}<Pages xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">{page}</Pages>'


_COLORS = ["#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF",
           "#800000", "#008000", "#000080", "#808000", "#800080", "#008080", "#C0C0C0", "#E6E6E6",
           "#CDCDCD", "#B3B3B3", "#9A9A9A", "#808080", "#666666", "#4D4D4D", "#333333", "#1A1A1A"]


def _style_sheet(sid: int, name: str, parent: int | None, cells: list[str], sections: str = "") -> str:
    p = "" if parent is None else _attrs(LineStyle=parent, FillStyle=parent, TextStyle=parent)
    return f'<StyleSheet{_attrs(ID=sid, NameU=name, IsCustomNameU=1, Name=name, IsCustomName=1)}{p}>{"".join(cells)}{sections}</StyleSheet>'


def _document_xml(fonts: list[str]) -> str:
    base_font = fonts[0] if fonts else "Calibri"
    no_style = [
        _cell("EnableLineProps", 1), _cell("EnableFillProps", 1), _cell("EnableTextProps", 1),
        _cell("HideForApply", 0),
        _pt("LineWeight", 0.75), _cell("LineColor", "#000000"), _cell("LinePattern", 1),
        _len("Rounding", 0.0), _cell("EndArrowSize", 2), _cell("BeginArrow", 0), _cell("EndArrow", 0),
        _cell("LineCap", 0), _cell("BeginArrowSize", 2), _cell("LineColorTrans", 0), _cell("CompoundType", 0),
        _cell("FillForegnd", "#FFFFFF"), _cell("FillBkgnd", "#000000"), _cell("FillPattern", 1),
        _cell("ShdwForegnd", "#000000"), _cell("ShdwPattern", 0), _cell("FillForegndTrans", 0),
        _cell("FillBkgndTrans", 0), _cell("ShdwForegndTrans", 0), _cell("ShapeShdwType", 0),
        _len("ShapeShdwOffsetX", 0.0), _len("ShapeShdwOffsetY", 0.0), _cell("ShapeShdwObliqueAngle", 0.0),
        _cell("ShapeShdwScaleFactor", 1.0), _cell("ShapeShdwBlur", 0.0), _cell("ShapeShdwShow", 0),
        _pt("LeftMargin", 0), _pt("RightMargin", 0), _pt("TopMargin", 0), _pt("BottomMargin", 0),
        _cell("VerticalAlign", 1), _len("DefaultTabStop", 0.5),
        _cell("TextDirection", 0),
        _cell("LockTextEdit", 0), _cell("LockVtxEdit", 0), _cell("LockCalcWH", 0),
    ]
    char = ('<Section N="Character"><Row IX="0">' + _cell("Font", base_font) + _cell("Color", "#000000")
            + _cell("Style", 0) + _cell("Case", 0) + _cell("Pos", 0) + _cell("FontScale", 1) + _pt("Size", 12)
            + _cell("ColorTrans", 0) + "</Row></Section>")
    para = ('<Section N="Paragraph"><Row IX="0">' + _cell("IndFirst", 0.0) + _cell("IndLeft", 0.0)
            + _cell("IndRight", 0.0) + _cell("SpLine", -1.2) + _cell("SpBefore", 0.0) + _cell("SpAfter", 0.0)
            + _cell("HorzAlign", 1) + _cell("Bullet", 0) + "</Row></Section>")
    normal = [_pt("LeftMargin", 4), _pt("RightMargin", 4), _pt("TopMargin", 4), _pt("BottomMargin", 4),
              _pt("LineWeight", 1), _cell("LineColor", "#94A3B8")]
    connector = [_cell("EndArrow", ARROW_FILLED), _cell("EndArrowSize", ARROW_SIZE), _cell("FillPattern", 0),
                 _pt("LineWeight", 1.25), _cell("LineColor", "#64748B")]
    text_only = [_cell("LinePattern", 0), _cell("FillPattern", 0), _pt("LeftMargin", 0), _pt("RightMargin", 0),
                 _pt("TopMargin", 0), _pt("BottomMargin", 0)]
    sheets = "".join([
        _style_sheet(STYLE_NONE, "No Style", None, no_style, char + para),
        _style_sheet(STYLE_NORMAL, "Normal", STYLE_NONE, normal),
        _style_sheet(STYLE_CONNECTOR, "Connector", STYLE_NORMAL, connector),
        _style_sheet(STYLE_TEXT, "Text Only", STYLE_NORMAL, text_only),
    ])
    colors = "".join(f'<ColorEntry IX="{i}" RGB="{c}"/>' for i, c in enumerate(_COLORS))
    faces = "".join(f"<FaceName{_attrs(NameU=f)}/>" for f in (fonts or ["Calibri"]))
    settings = (f'<DocumentSettings TopPage="0" DefaultTextStyle="{STYLE_NORMAL}" DefaultLineStyle="{STYLE_NORMAL}" '
                f'DefaultFillStyle="{STYLE_NORMAL}" DefaultGuideStyle="{STYLE_NONE}">'
                "<GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings><SnapExtensions>34</SnapExtensions>"
                "<SnapAngles/><DynamicGridEnabled>1</DynamicGridEnabled><ProtectStyles>0</ProtectStyles>"
                "<ProtectShapes>0</ProtectShapes><ProtectMasters>0</ProtectMasters><ProtectBkgnds>0</ProtectBkgnds>"
                "</DocumentSettings>")
    doc_sheet = ('<DocumentSheet NameU="TheDoc" IsCustomNameU="1" Name="TheDoc" IsCustomName="1" '
                 'LineStyle="0" FillStyle="0" TextStyle="0">'
                 + _cell("OutputFormat", 0) + _cell("LockPreview", 0) + _cell("AddMarkup", 0)
                 + _cell("ViewMarkup", 0) + _cell("DocLockReplace", 0, "BOOL") + _cell("NoCoauth", 0, "BOOL")
                 + _cell("DocLockDuplicatePage", 0, "BOOL") + _cell("PreviewQuality", 0)
                 + _cell("PreviewScope", 0) + _cell("DocLangID", 1033) + "</DocumentSheet>")
    return (f'{_XML}<VisioDocument xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">'
            f"{settings}<Colors>{colors}</Colors><FaceNames>{faces}</FaceNames>"
            f"<StyleSheets>{sheets}</StyleSheets>{doc_sheet}</VisioDocument>")


def _windows_xml(plan: DiagramPlan) -> str:
    win = (f'<Window{_attrs(ID=0, WindowType="Drawing", WindowState=1073741824, WindowLeft=-8, WindowTop=-31, WindowWidth=1600, WindowHeight=900, ContainerType="Page", Page=0, ViewScale=-1, ViewCenterX=_n(plan.width / 2), ViewCenterY=_n(plan.height / 2))}>'
           "<ShowRulers>1</ShowRulers><ShowGrid>0</ShowGrid><ShowPageBreaks>0</ShowPageBreaks>"
           "<ShowGuides>1</ShowGuides><ShowConnectionPoints>1</ShowConnectionPoints>"
           "<GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings><SnapExtensions>34</SnapExtensions>"
           "<SnapAngles/><DynamicGridEnabled>1</DynamicGridEnabled><TabSplitterPos>0.5</TabSplitterPos>"
           "</Window>")
    return f'{_XML}<Windows ClientWidth="1600" ClientHeight="900" xmlns="{NS}" xmlns:r="{NS_R}" xml:space="preserve">{win}</Windows>'


def _rels(rels: list[tuple[str, str, str]]) -> str:
    body = "".join(f"<Relationship{_attrs(Id=i, Type=t, Target=tg)}/>" for i, t, tg in rels)
    return f'{_XML}<Relationships xmlns="{NS_PKG_REL}">{body}</Relationships>'


def _content_types(images: bool = False) -> str:
    overrides = [
        ("/visio/document.xml", CT_DOCUMENT),
        ("/visio/pages/pages.xml", CT_PAGES),
        ("/visio/pages/page1.xml", CT_PAGE),
        ("/visio/windows.xml", CT_WINDOWS),
        ("/docProps/core.xml", CT_CORE),
        ("/docProps/app.xml", CT_APP),
    ]
    body = (f'<Default Extension="rels" ContentType="{CT_RELS}"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + (f'<Default Extension="png" ContentType="{CT_PNG}"/>' if images else "")
            + "".join(f'<Override PartName="{p}" ContentType="{c}"/>' for p, c in overrides))
    return f'{_XML}<Types xmlns="{NS_CT}">{body}</Types>'


def _core_xml(title: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f'{_XML}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{escape(_clean(title))}</dc:title><dc:creator>visio-mcp</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
            "</cp:coreProperties>")


def _app_xml() -> str:
    return (f'{_XML}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            "<Application>visio-mcp</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>"
            "<HeadingPairs><vt:vector size=\"2\" baseType=\"variant\"><vt:variant><vt:lpstr>Pages</vt:lpstr></vt:variant>"
            "<vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>"
            "<TitlesOfParts><vt:vector size=\"1\" baseType=\"lpstr\"><vt:lpstr>Page-1</vt:lpstr></vt:vector></TitlesOfParts>"
            "<Company></Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc>"
            "<HyperlinksChanged>false</HyperlinksChanged><AppVersion>16.0000</AppVersion></Properties>")


# --- entry point ----------------------------------------------------------------------------


def build_page(plan: DiagramPlan) -> _Page:
    """All shapes in z-order: background, group frames (outer first), legend, connectors,
    nodes, title. Nodes are drawn before connectors are written so glue can name their ids;
    connectors are then moved below the nodes."""
    page = _Page()
    wanted = [n.image for n in plan.nodes if n.image is not None and n.geometry == "icon"]
    if wanted:
        from visio_mcp import icons

        page.pngs = icons.pngs_for(wanted)  # SVG icons rasterized once; None -> glyph tile
    _draw_background(page, plan)
    for g in sorted(plan.groups, key=lambda g: g.depth):
        _draw_group(page, g)
    if plan.legend:
        _draw_legend(page, plan)
    first_node = len(page.shapes)
    for n in plan.nodes:
        _draw_node(page, plan, n)
    nodes = page.shapes[first_node:]
    page.shapes = page.shapes[:first_node]
    for e in plan.edges:
        _draw_edge(page, plan, e)
    page.shapes += nodes
    if plan.title:
        _draw_title(page, plan.title)
    return page


def write_vsdx(plan: DiagramPlan, path: str | Path) -> Path:
    """Write plan as a native Visio drawing. Returns the absolute path."""
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    page = build_page(plan)
    for st in (plan.theme.title, plan.theme.subtitle):
        page.font(st.font)
    title = plan.spec.title or "Diagram"
    parts = {
        "[Content_Types].xml": _content_types(),
        "_rels/.rels": _rels([
            ("rId1", REL_DOCUMENT, "visio/document.xml"),
            ("rId2", REL_CORE, "docProps/core.xml"),
            ("rId3", REL_APP, "docProps/app.xml"),
        ]),
        "docProps/app.xml": _app_xml(),
        "docProps/core.xml": _core_xml(title),
        "visio/document.xml": _document_xml(page.fonts),
        "visio/_rels/document.xml.rels": _rels([
            ("rId1", REL_PAGES, "pages/pages.xml"),
            ("rId2", REL_WINDOWS, "windows.xml"),
        ]),
        "visio/windows.xml": _windows_xml(plan),
        "visio/pages/pages.xml": _pages_xml(plan),
        "visio/pages/_rels/pages.xml.rels": _rels([("rId1", REL_PAGE, "page1.xml")]),
        "visio/pages/page1.xml": _page_xml(page),
    }
    if page.media:
        parts["[Content_Types].xml"] = _content_types(images=True)
        parts["visio/pages/_rels/page1.xml.rels"] = _rels(
            [(rid, REL_IMAGE, f"../media/{part}") for rid, part in page.media.values()])
    media = {f"visio/media/{part}": png for png, (_, part) in page.media.items()}
    tmp = out.with_suffix(out.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data.encode("utf-8"))
        for name, png in media.items():
            z.write(png, name, compress_type=zipfile.ZIP_STORED)
    tmp.replace(out)
    return out
