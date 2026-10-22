"""Character, Paragraph and <Text> XML for styled text runs."""

from __future__ import annotations

from xml.sax.saxutils import escape

from visio_mcp.output.visio.backend import TextRun
from visio_mcp.output.vsdx.cells import H_ALIGN, cell, clean, color, points
from visio_mcp.style import TextStyle


def char_row(ix: int, st: TextStyle) -> str:
    style = (1 if st.bold else 0) | (2 if st.italic else 0)
    return (
        f'<Row IX="{ix}">'
        + cell("Font", st.font)
        + cell("Color", color(st.color))
        + cell("Style", style)
        + cell("Case", 0)
        + cell("Pos", 0)
        + cell("FontScale", 1)
        + points("Size", st.size)
        + cell("ColorTrans", 0)
        + "</Row>"
    )


def text_xml(runs: list[TextRun], align: str = "center") -> tuple[str, str]:
    """(Character + Paragraph sections, <Text> element) for styled runs."""
    runs = [r for r in runs if r.text]
    if not runs:
        return "", ""
    styles: list[TextStyle] = []
    for r in runs:
        if r.style not in styles:
            styles.append(r.style)
    char = '<Section N="Character">' + "".join(char_row(i, s) for i, s in enumerate(styles)) + "</Section>"
    para = (
        '<Section N="Paragraph"><Row IX="0">'
        + cell("IndFirst", 0.0) + cell("IndLeft", 0.0) + cell("IndRight", 0.0)
        + cell("SpLine", -1.1) + cell("SpBefore", 0.0) + cell("SpAfter", 0.0)
        + cell("HorzAlign", H_ALIGN.get(align, 1)) + cell("Bullet", 0)
        + "</Row></Section>"
    )
    body = ['<pp IX="0"/>']
    for r in runs:
        body.append(f'<cp IX="{styles.index(r.style)}"/>{escape(clean(r.text))}')
    return char + para, "<Text>" + "".join(body) + "</Text>"


def text_height(runs: list[TextRun]) -> float:
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
