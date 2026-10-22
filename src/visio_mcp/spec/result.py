"""What render and patch report back to the agent."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RenderResult(BaseModel):
    shapes: int
    connectors: int
    warnings: list[str] = []
    suggestions: list[str] = Field(
        [], description="Diagramming-rule findings (lint). Fix them with patch_diagram or a re-render."
    )
    overlaps: list[tuple[str, str]] = Field(
        [], description="Pairs of node ids whose shapes overlap. Should be empty."
    )
    files: list[str] = Field([], description="Absolute paths written (vsdx and exports).")
