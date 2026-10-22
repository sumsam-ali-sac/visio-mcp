"""The page being assembled: shape ids, z-order, glue, fonts and embedded media."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from visio_mcp.output.visio.backend import TextRun
from visio_mcp.output.vsdx.cells import attrs

STYLE_NONE = 0  # 'No Style': root of every inheritance chain, defines every cell
STYLE_NORMAL = 1
STYLE_CONNECTOR = 2
STYLE_TEXT = 3  # 'Text Only'


@dataclass
class Shape:
    """One <Shape> being assembled."""

    id: int
    name: str
    style: int = STYLE_NORMAL
    cells: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    text: str = ""
    type: Literal["Shape", "Group", "Foreign"] = "Shape"
    children: list["Shape"] = field(default_factory=list)
    foreign: str = ""  # <ForeignData> of a picture shape

    def set_text(self, sections: str, text: str) -> None:
        """Character/Paragraph sections go first, before Geometry."""
        self.sections.insert(0, sections)
        self.text = text

    def xml(self) -> str:
        a = attrs(ID=self.id, NameU=self.name, Name=self.name, IsCustomNameU=1, IsCustomName=1,
                  Type=self.type, LineStyle=self.style, FillStyle=self.style, TextStyle=self.style)
        kids = ""
        if self.children:
            kids = "<Shapes>" + "".join(c.xml() for c in self.children) + "</Shapes>"
        return f"<Shape{a}>{''.join(self.cells)}{''.join(self.sections)}{self.text}{self.foreign}{kids}</Shape>"


class Page:
    def __init__(self) -> None:
        self.shapes: list[Shape] = []  # top level, back to front
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

    def add(self, shape: Shape) -> Shape:
        self.shapes.append(shape)
        self.ids[shape.name] = shape.id
        return shape

    def media_rel(self, png: Path) -> str:
        """Relationship id of an embedded bitmap, registering it on first use."""
        if png not in self.media:
            n = len(self.media) + 1
            self.media[png] = (f"rId{n}", f"image{n}.png")
        return self.media[png][0]
