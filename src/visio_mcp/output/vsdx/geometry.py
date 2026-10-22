"""Geometry sections that draw each node geometry, written as formulas so shapes resize like masters."""

from __future__ import annotations

import math
from dataclasses import dataclass

from visio_mcp.output.vsdx.cells import cell, num


@dataclass(frozen=True)
class Lin:
    """A geometry coordinate kw*Width + kh*Height + c."""

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
            parts.append(f"Width*{num(self.kw)}")
        if self.kh:
            parts.append(f"Height*{num(self.kh)}")
        f = "+".join(parts)
        if self.c:
            f += f"{'+' if self.c > 0 else '-'}{num(abs(self.c))}"
        return f.replace("+-", "-")


Val = float | int | Lin | tuple  # tuple = (value, formula)
Row = tuple[str, dict[str, Val]]


@dataclass
class Section:
    rows: list[Row]
    no_fill: bool = False
    no_line: bool = False


def W(k: float = 1.0, c: float = 0.0) -> Lin:
    return Lin(kw=k, c=c)


def H(k: float = 1.0, c: float = 0.0) -> Lin:
    return Lin(kh=k, c=c)


def poly(pts: list[tuple[Val, Val]], no_fill: bool = False, closed: bool = True) -> Section:
    rows: list[Row] = [("MoveTo", {"X": pts[0][0], "Y": pts[0][1]})]
    rows += [("LineTo", {"X": x, "Y": y}) for x, y in pts[1:]]
    if closed:
        rows.append(("LineTo", {"X": pts[0][0], "Y": pts[0][1]}))
    return Section(rows, no_fill=no_fill)


def rect() -> Section:
    return poly([(0.0, 0.0), (W(), 0.0), (W(), H()), (0.0, H())])


def ellipse(cx: Val, cy: Val, ax: Val, ay: Val, bx: Val, by: Val, no_fill: bool = False) -> Section:
    """Ellipse row: center, end of one axis, end of the other axis."""
    return Section([("Ellipse", {"X": cx, "Y": cy, "A": ax, "B": ay, "C": bx, "D": by})], no_fill=no_fill)


def hline(y: Val) -> Section:
    """An unfilled line across the shape at height y."""
    return Section([("MoveTo", {"X": 0.0, "Y": y}), ("LineTo", {"X": W(), "Y": y})], no_fill=True)


def _earc(x: Val, y: Val, ax: Val, ay: Val, ratio: float) -> Row:
    """EllipticalArcTo to (x, y) through (ax, ay); ratio = x-radius / y-radius."""
    return ("EllipticalArcTo", {"X": x, "Y": y, "A": ax, "B": ay, "C": 0.0, "D": ratio})


def rounded_rect(r: float, w: float, h: float) -> Section:
    """Rectangle with corners drawn as real quarter circles (renders identically in every
    viewer, unlike the Rounding cell which some importers ignore)."""
    r = max(0.0, min(r, w / 2, h / 2))
    if r < 1e-3:
        return rect()
    k = 1 - math.sqrt(0.5)  # arc midpoint inset from the corner, as a fraction of r
    rows: list[Row] = [
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
        return [rounded_rect(rounding or 0.08, w, h)]
    if kind == "rect":
        return [rounded_rect(rounding, w, h)] if rounding else [rect()]
    if kind == "terminator":
        r = h / 2
        return [Section([
            ("MoveTo", {"X": H(0.5), "Y": 0.0}),
            ("LineTo", {"X": Lin(1, -0.5), "Y": 0.0}),
            _earc(Lin(1, -0.5), H(), W(), H(0.5), 1.0),
            ("LineTo", {"X": H(0.5), "Y": H()}),
            _earc(H(0.5), 0.0, 0.0, H(0.5), 1.0),
        ])] if w >= 2 * r else [ellipse(W(0.5), H(0.5), W(), H(0.5), W(0.5), H())]
    if kind == "decision":
        return [poly([(W(0.5), 0.0), (W(), H(0.5)), (W(0.5), H()), (0.0, H(0.5))])]
    if kind == "parallelogram":
        s = min(0.2 * w, 0.6 * h, 0.3)
        return [poly([(0.0, 0.0), (W(1, -s), 0.0), (W(), H()), (s, H())])]
    if kind == "trapezoid":  # manual operation: wide top
        s = min(0.15 * w, 0.5 * h, 0.3)
        return [poly([(s, 0.0), (W(1, -s), 0.0), (W(), H()), (0.0, H())])]
    if kind == "hexagon":
        s = min(0.2 * w, 0.35 * h, 0.3)
        return [poly([(s, 0.0), (W(1, -s), 0.0), (W(), H(0.5)), (W(1, -s), H()), (s, H()), (0.0, H(0.5))])]
    if kind in ("ellipse", "circle"):
        return [ellipse(W(0.5), H(0.5), W(), H(0.5), W(0.5), H())]
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
        top = ellipse(W(0.5), H(1, -ry), W(), H(1, -ry), W(0.5), H())
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
        cap = ellipse(W(1, -rx), H(0.5), W(), H(0.5), W(1, -rx), H())
        return [body, cap]
    if kind == "cloud":
        return [_cloud(w, h)]
    if kind == "note":
        f = min(0.2 * min(w, h), 0.2)
        body = poly([(0.0, 0.0), (W(), 0.0), (W(), H(1, -f)), (W(1, -f), H()), (0.0, H())])
        fold = poly([(W(1, -f), H()), (W(1, -f), H(1, -f)), (W(), H(1, -f))], no_fill=True, closed=False)
        return [body, fold]
    if kind == "subprocess":
        d = min(0.1, 0.08 * w)
        bars = [
            Section([("MoveTo", {"X": d, "Y": 0.0}), ("LineTo", {"X": d, "Y": H()})], no_fill=True),
            Section([("MoveTo", {"X": W(1, -d), "Y": 0.0}), ("LineTo", {"X": W(1, -d), "Y": H()})], no_fill=True),
        ]
        return [rounded_rect(min(rounding, 0.04), w, h), *bars]
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
        head = ellipse(W(0.5), cy, W(0.5, r), cy, W(0.5), cy + r)
        return [body, head]
    if kind == "icon":
        return [rounded_rect(min(0.14, w * 0.2), w, h)]
    if kind == "entity":
        return [rounded_rect(rounding, w, h)]  # header divider added by the caller
    return [rounded_rect(rounding, w, h)] if rounding else [rect()]


def _cloud(w: float, h: float) -> Section:
    """Puffy cloud: arcs bulging outward between points on an inner ellipse."""
    n = 9
    cx, cy, rx, ry = w / 2, h / 2, w / 2 * 0.86, h / 2 * 0.78
    pts = []
    for i in range(n):
        t = math.pi * 1.5 + 2 * math.pi * i / n  # start at the bottom
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    rows: list[Row] = [("MoveTo", {"X": W(pts[0][0] / w), "Y": H(pts[0][1] / h)})]
    for i in range(1, n + 1):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i % n]
        chord = math.hypot(x1 - x0, y1 - y0)
        bulge = 0.42 * chord * (1.15 if i % 2 else 0.9)
        # counterclockwise around the center: the outside is on the right of the direction
        rows.append(("ArcTo", {"X": W(x1 / w), "Y": H(y1 / h), "A": bulge}))
    return Section(rows)


def geometry_xml(sections: list[Section], w: float, h: float, start_ix: int = 0) -> str:
    """<Section N="Geometry"> elements, numbered from start_ix."""
    out = []
    for i, sec in enumerate(sections):
        cells = [
            cell("NoFill", 1 if sec.no_fill else 0),
            cell("NoLine", 1 if sec.no_line else 0),
            cell("NoShow", 0),
            cell("NoSnap", 0),
            cell("NoQuickDrag", 0),
        ]
        for ix, (t, vals) in enumerate(sec.rows, start=1):
            cs = []
            for k, v in vals.items():
                if isinstance(v, Lin):
                    cs.append(cell(k, float(v.value(w, h)), None, v.formula()))
                elif isinstance(v, tuple):
                    cs.append(cell(k, float(v[0]), None, v[1]))
                else:
                    cs.append(cell(k, float(v)))
            cells.append(f'<Row T="{t}" IX="{ix}">{"".join(cs)}</Row>')
        out.append(f'<Section N="Geometry" IX="{start_ix + i}">{"".join(cells)}</Section>')
    return "".join(out)
