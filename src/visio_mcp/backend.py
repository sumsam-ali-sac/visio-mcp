"""The contract between diagram logic and Visio.

render/edit only talk to this Protocol, so they can be tested against FakeVisio.
Shapes are addressed by name: nodes and groups use their spec id, connectors
use "source->target". Coordinates are inches, (x, y) is the shape's center,
origin is the page's bottom-left corner.

Every method must be called from the COM thread (see com_thread.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

LinePattern = Literal["solid", "dashed", "dotted"]
ArrowMode = Literal["end", "both", "none"]


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
    def set_fill(self, name: str, color: str) -> None:
        """color is '#RRGGBB'."""
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
    def add_container(self, name: str, label: str, members: list[str]) -> None:
        """Wrap existing shapes in a labeled container sized to fit them."""
        ...

    def move(self, name: str, x: float, y: float) -> None: ...
    def delete(self, name: str) -> None: ...
    def shapes(self) -> list[ShapeInfo]: ...

    # page
    def layout(self, preset: str) -> None:
        """Run auto-layout with a spec Layout preset ('none' = no-op), then fit page to contents."""
        ...
