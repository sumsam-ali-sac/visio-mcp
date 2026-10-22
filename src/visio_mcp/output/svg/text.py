"""Text layout for SVG: wrap styled runs into lines, shrink to fit, emit <text>/<tspan>."""

from __future__ import annotations

from dataclasses import dataclass

from visio_mcp.output.svg.markup import LINE_H, PT, PX, esc, font_stack, num
from visio_mcp.output.visio.backend import TextRun
from visio_mcp.style import TextStyle, text_width


@dataclass
class Seg:
    text: str
    style: TextStyle
    size: float  # px


@dataclass
class Line:
    segs: list[Seg]
    width: float  # px
    height: float  # px


def single_line(text: str, style: TextStyle, size_px: float) -> Line:
    """One unwrapped line in one style (headers, legend entries, glyphs)."""
    return Line([Seg(text, style, size_px)], 0, size_px * LINE_H)


def _word_w(word: str, st: TextStyle, scale: float) -> float:
    return text_width(word, st.size * scale, st.bold) * PX


def layout_text(runs: list[TextRun], max_w_px: float, scale: float = 1.0) -> list[Line]:
    """Split runs into paragraphs on '\\n', wrap words greedily to max_w_px."""
    paras: list[list[tuple[str, TextStyle]]] = [[]]
    for r in runs:
        for i, part in enumerate(r.text.split("\n")):
            if i > 0:
                paras.append([])
            for w in part.split():
                paras[-1].append((w, r.style))
    lines: list[Line] = []
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


def _finish_line(words: list[tuple[str, TextStyle]], scale: float) -> Line:
    segs: list[Seg] = []
    width = 0.0
    for i, (w, st) in enumerate(words):
        width += _word_w(w, st, scale) + (_word_w(" ", st, scale) if i else 0)
        if segs and segs[-1].style == st:
            segs[-1].text += " " + w
        else:
            if segs:
                segs[-1].text += " "
            segs.append(Seg(w, st, st.size * scale * PT))
    height = max(s.size for s in segs) * LINE_H
    return Line(segs, width, height)


def fit_text(runs: list[TextRun], max_w: float, max_h: float, min_scale: float = 0.72) -> list[Line]:
    """Lay out text, shrinking the font a little when it would overflow max_h."""
    lines = layout_text(runs, max_w)
    total = block_h(lines)
    if total > max_h > 0:
        scale = max(min_scale, max_h / total)
        lines = layout_text(runs, max_w / scale, scale)
    return lines


def block_h(lines: list[Line]) -> float:
    return sum(ln.height for ln in lines)


def text_svg(lines: list[Line], x: float, top: float, anchor: str = "middle") -> str:
    """One <text> per line, starting at top, anchored at x."""
    out: list[str] = []
    y = top
    for ln in lines:
        fs = max(s.size for s in ln.segs)
        base = y + ln.height / 2 + fs * 0.34
        spans = []
        for s in ln.segs:
            st = s.style
            attrs = (f' font-family="{esc(font_stack(st.font))}" font-size="{num(s.size)}" fill="{esc(st.color)}"')
            if st.bold:
                attrs += ' font-weight="600"'
            if st.italic:
                attrs += ' font-style="italic"'
            spans.append(f"<tspan{attrs}>{esc(s.text)}</tspan>")
        out.append(f'<text x="{num(x)}" y="{num(base)}" text-anchor="{anchor}" xml:space="preserve">{"".join(spans)}</text>')
        y += ln.height
    return "".join(out)
