"""ShapeSheet constants, formula builders and safe cell writes."""

from __future__ import annotations

import re
from typing import Any

import pywintypes

# Visio type-library constants (names in comments).
LINE_PATTERNS = {"solid": 1, "dashed": 2, "dotted": 3}  # visLPatSolid / ...
ARROW_FILLED = 13  # standard filled arrowhead
ARROW_SIZE_MEDIUM = 2  # visArrowSizeMedium
SECTION_CHARACTER = 3  # visSectionCharacter
SECTION_PARAGRAPH = 4  # visSectionParagraph
CHAR_FONT, CHAR_COLOR, CHAR_STYLE, CHAR_SIZE = 0, 1, 2, 7  # visCharacterFont / Color / Style / Size
PARA_HORZ_ALIGN = 6  # visHorzAlign
STYLE_BOLD, STYLE_ITALIC = 1, 2  # visBold, visItalic (Char.Style bits)
HORZ_ALIGN = {"left": 0, "center": 1, "right": 2}  # visHorzLeft / visHorzCenter / visHorzRight
VERT_TOP, VERT_MIDDLE = 0, 1  # visVertTop, visVertMiddle
OBJ_TYPE_NONE = 4  # ObjType: neither placeable nor routable (layout and routing ignore it)


def rgb(color: str) -> str:
    """'#RRGGBB' -> 'RGB(r,g,b)'."""
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", color)
    if not m:
        raise ValueError(f"color must be '#RRGGBB', got {color!r}")
    r, g, b = (int(m.group(1)[i : i + 2], 16) for i in (0, 2, 4))
    return f"RGB({r},{g},{b})"


def pt(v: float) -> str:
    return f"{v:g} pt"


def inch(v: float) -> str:
    return f"{v:g} in"


def _force(cell: Any, formula: str) -> None:
    try:
        cell.FormulaForceU = formula  # also replaces GUARD()ed master formulas
    except pywintypes.com_error:
        cell.FormulaU = formula


def set_cell(shape: Any, cell: str, formula: str) -> bool:
    """Set a cell by universal name; a missing or refusing cell is skipped, never fatal."""
    try:
        if not shape.CellExistsU(cell, 0):
            return False
        _force(shape.CellsU(cell), formula)
        return True
    except pywintypes.com_error:
        return False


def set_cells(shape: Any, formulas: dict[str, str]) -> None:
    for cell, formula in formulas.items():
        set_cell(shape, cell, formula)


def set_cell_src(shape: Any, section: int, row: int, column: int, formula: str) -> bool:
    """Set a cell by section/row/column index (Character and Paragraph rows)."""
    try:
        _force(shape.CellsSRC(section, row, column), formula)
        return True
    except pywintypes.com_error:
        return False


def row_count(shape: Any, section: int) -> int:
    """Rows in a section, at least 1."""
    try:
        return max(1, int(shape.RowCount(section)))
    except pywintypes.com_error:
        return 1
