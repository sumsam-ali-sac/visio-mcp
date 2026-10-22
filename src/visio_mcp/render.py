"""DiagramSpec -> shapes on the active Visio page.  (F3: implement)"""

from __future__ import annotations

from visio_mcp.backend import ShapeInfo, VisioBackend
from visio_mcp.spec import DiagramSpec, RenderResult


def render_spec(backend: VisioBackend, spec: DiagramSpec) -> RenderResult:
    """Build the whole diagram in a fresh document. Does not save or export (server does)."""
    raise NotImplementedError


def find_overlaps(shapes: list[ShapeInfo]) -> list[tuple[str, str]]:
    """Pairs of non-connector, non-container shapes whose boxes intersect."""
    raise NotImplementedError
