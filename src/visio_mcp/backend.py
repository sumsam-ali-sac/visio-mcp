"""The contract between diagram logic and Visio.

render/edit only talk to this Protocol, so they can be tested against FakeVisio.
Shapes are addressed by name: nodes and groups use their spec id, connectors
use "source->target", decorations (title, legend, background) start with "__".
Coordinates are inches, (x, y) is the shape's center, origin is the page's
bottom-left corner. Colors are '#RRGGBB'.

Every method must be called from the COM thread (see com_thread.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from visio_mcp.style import EdgeStyle, GroupStyle, ShapeStyle, TextStyle

LinePattern = Literal["solid", "dashed", "dotted"]
ArrowMode = Literal["end", "both", "none"]
Align = Literal["left", "center", "right"]


@dataclass
class ShapeInfo:
    name: str
    text: str
    master: str | None
    x: float
    y: float
    width: float
    height: float
    is_connector: bool = False
    is_container: bool = False


@dataclass(frozen=True)
class TextRun:
    """A piece of text with its own style; runs are joined as-is (include '\\n' yourself)."""

    text: str
    style: TextStyle


class VisioBackend(Protocol):
    # documents
    def new_document(self, title: str) -> None: ...
    def open_document(self, path: str) -> None: ...
    def save(self, path: str) -> str:
        """Save as .vsdx, return the absolute path."""
        ...

    def export(self, path: str) -> str:
        """Export the active page; format from extension (.png .svg .pdf .jpg). Return abs path."""
        ...

    # stencils
    def list_stencils(self) -> list[str]:
        """Built-in stencil file names available on this machine, e.g. 'BASFLO_U.VSSX'."""
        ...

    def list_masters(self, stencil: str) -> list[str]:
        """Universal master names (NameU) in a stencil. Empty list if the stencil is missing."""
        ...

    def has_master(self, stencil: str, master: str) -> bool: ...

    # shapes
    def drop_shape(
        self,
        name: str,
        stencil: str,
        master: str,
        x: float,
        y: float,
        width: float | None = None,
        height: float | None = None,
    ) -> None: ...
    def set_text(self, name: str, text: str) -> None: ...
    def set_rich_text(self, name: str, runs: list[TextRun]) -> None:
        """Replace the shape's text with styled runs (label bold, technology small, ...)."""
        ...

    def set_fill(self, name: str, color: str) -> None: ...
    def style_shape(
        self, name: str, style: ShapeStyle, keep_fill: bool = False, label_below: bool = False
    ) -> None:
        """Apply fill, line, rounding, shadow and base text style.

        keep_fill leaves an icon master's own colors and outline alone (text style still applies);
        label_below moves the text block under the shape (icons), wide enough for two lines.
        """
        ...

    def connect(
        self,
        name: str,
        source: str,
        target: str,
        label: str = "",
        pattern: LinePattern = "solid",
        arrow: ArrowMode = "end",
    ) -> None: ...
    def style_connector(self, name: str, style: EdgeStyle, color: str | None = None) -> None:
        """Line color/weight, right-angle routing with rounded corners, label font and backdrop."""
        ...

    def add_container(
        self,
        name: str,
        label: str,
        members: list[str],
        style: GroupStyle | None = None,
        bounds: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Wrap existing shapes (nodes or inner containers) in a labeled container.

        bounds = (center x, center y, width, height) fixes its frame (no auto-resize);
        None sizes it to fit the members. The label sits top-left in style.header.
        """
        ...

    def add_box(self, name: str, x: float, y: float, width: float, height: float, style: ShapeStyle) -> None:
        """A plain rectangle (background, legend frame, swatch). Not a node."""
        ...

    def add_text(
        self,
        name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        runs: list[TextRun],
        align: Align = "left",
    ) -> None:
        """A borderless, transparent text block (title, subtitle, legend entries)."""
        ...

    def add_line(
        self, name: str, x1: float, y1: float, x2: float, y2: float, style: EdgeStyle,
        pattern: LinePattern = "solid", arrow: ArrowMode = "end",
    ) -> None:
        """A free line not glued to shapes (legend samples)."""
        ...

    def send_to_back(self, name: str) -> None: ...
    def move(self, name: str, x: float, y: float) -> None: ...
    def delete(self, name: str) -> None: ...
    def shapes(self) -> list[ShapeInfo]: ...

    # page
    def set_page(self, width: float, height: float, background: str | None = None) -> None:
        """Page size in inches; background fills the whole page (None = white/none)."""
        ...

    def layout(self, preset: str) -> None:
        """Run Visio's own auto-layout with a spec Layout preset ('none' = no-op), then fit page."""
        ...

    def fit_page(self, margin: float = 0.5) -> None:
        """Resize the page to its contents plus margin, keeping the background covering it."""
        ...

    def present(self) -> None:
        """Make the result easy to look at: zoom to page, clear selection. No-op when headless."""
        ...
