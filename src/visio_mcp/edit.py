"""Small edits to the open diagram, and inspection.  (F3: implement)"""

from __future__ import annotations

from typing import Any

from visio_mcp.backend import VisioBackend
from visio_mcp.spec import PatchOp, RenderResult


def apply_ops(backend: VisioBackend, ops: list[PatchOp]) -> RenderResult:
    """Apply ops in order. Bad ops become warnings, they don't abort the batch."""
    raise NotImplementedError


def inspect(backend: VisioBackend) -> dict[str, Any]:
    """{'shapes': [...], 'connectors': [...], 'overlaps': [...]} for the agent to review."""
    raise NotImplementedError
