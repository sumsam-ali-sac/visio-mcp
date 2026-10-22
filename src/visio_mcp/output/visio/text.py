"""Shape text: styled runs, character and paragraph rows, and the label-below-icon block."""

from __future__ import annotations

from typing import Any, Callable

import pythoncom
import pywintypes

from visio_mcp.output.visio.backend import TextRun
from visio_mcp.output.visio.cells import (
    CHAR_COLOR,
    CHAR_FONT,
    CHAR_SIZE,
    CHAR_STYLE,
    HORZ_ALIGN,
    PARA_HORZ_ALIGN,
    SECTION_CHARACTER,
    SECTION_PARAGRAPH,
    STYLE_BOLD,
    STYLE_ITALIC,
    VERT_TOP,
    inch,
    pt,
    rgb,
    row_count,
    set_cell,
    set_cell_src,
)
from visio_mcp.style import TextStyle

BIAS_LET_VISIO_CHOOSE = 0  # visBiasLetVisioChoose (Characters.CharPropsRow)
LABEL_BELOW_HEIGHT = 0.45  # inches, text block under an icon

FontFormula = Callable[[str], str | None]


class Fonts:
    """Char.Font formulas for one document: the font's ID there (a FONT() formula as fallback)."""

    def __init__(self, doc: Callable[[], Any]) -> None:
        self._doc = doc
        self._cache: dict[str, str] = {}

    def __call__(self, name: str) -> str | None:
        if name not in self._cache:
            try:
                self._cache[name] = str(int(self._doc().Fonts(name).ID))
            except (pywintypes.com_error, TypeError, ValueError):
                self._cache[name] = f'FONT("{name}")'
        return self._cache[name]


def u16len(text: str) -> int:
    """Length as Visio counts characters (UTF-16 code units)."""
    return len(text.encode("utf-16-le")) // 2


def write_runs(shape: Any, runs: list[TextRun], font: FontFormula) -> None:
    """Set the text once, then give each run its own Character row and style that row."""
    shape.Text = "".join(r.text for r in runs)
    runs = [r for r in runs if r.text]
    if not runs:
        return
    if len(runs) > 1:
        try:
            pos = 0
            for i, run in enumerate(runs):
                n = u16len(run.text)
                chars = shape.Characters
                chars.Begin = pos
                chars.End = pos + n
                # A unique temporary size splits the range into its own row; real cells come next.
                _put_char_prop(chars, CHAR_SIZE, 100 + i)
                row = int(chars.CharPropsRow(BIAS_LET_VISIO_CHOOSE))
                if row < 0:
                    raise ValueError("run spans several character rows")
                char_row(shape, row, run.style, font)
                pos += n
            return
        except (pywintypes.com_error, ValueError, AttributeError):
            pass  # fall back to one style for the whole text
    text_style(shape, runs[0].style, font)


def char_row(shape: Any, row: int, st: TextStyle, font: FontFormula) -> None:
    formula = font(st.font)
    if formula:
        set_cell_src(shape, SECTION_CHARACTER, row, CHAR_FONT, formula)
    set_cell_src(shape, SECTION_CHARACTER, row, CHAR_COLOR, rgb(st.color))
    set_cell_src(shape, SECTION_CHARACTER, row, CHAR_STYLE,
                 str((STYLE_BOLD if st.bold else 0) | (STYLE_ITALIC if st.italic else 0)))
    set_cell_src(shape, SECTION_CHARACTER, row, CHAR_SIZE, pt(st.size))


def text_style(shape: Any, st: TextStyle, font: FontFormula) -> None:
    """One style for every character row of the shape."""
    for row in range(row_count(shape, SECTION_CHARACTER)):
        char_row(shape, row, st, font)


def paragraphs(shape: Any, align: str) -> None:
    """One horizontal alignment for every paragraph row of the shape."""
    for row in range(row_count(shape, SECTION_PARAGRAPH)):
        set_cell_src(shape, SECTION_PARAGRAPH, row, PARA_HORZ_ALIGN, str(HORZ_ALIGN[align]))


def label_below(shape: Any) -> None:
    """Text block under the shape (icons), wide enough for two lines, tracking its size."""
    if not shape.CellExistsU("TxtPinX", 0):
        try:
            shape.AddRow(1, 12, 0)  # visSectionObject, visRowTextXForm, visTagDefault
        except pywintypes.com_error:
            return
    for cell, formula in (
        ("TxtWidth", "MAX(1.7 in,Width*2)"),
        ("TxtHeight", inch(LABEL_BELOW_HEIGHT)),
        ("TxtPinX", "Width*0.5"),
        ("TxtPinY", "-TxtHeight*0.5-0.04 in"),
        ("TxtLocPinX", "TxtWidth*0.5"),
        ("TxtLocPinY", "TxtHeight*0.5"),
        ("TxtAngle", "0 deg"),
        ("VerticalAlign", str(VERT_TOP)),
    ):
        set_cell(shape, cell, formula)


def _put_char_prop(chars: Any, index: int, value: int) -> None:
    """Characters.CharProps(index) = value. pywin32 exposes indexed put properties as Set<Name>."""
    try:
        chars.SetCharProps(index, value)
    except AttributeError:
        ole = chars._oleobj_
        ole.Invoke(ole.GetIDsOfNames("CharProps"), 0, pythoncom.DISPATCH_PROPERTYPUT, 0, index, value)
