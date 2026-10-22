"""DrawOutput: what one render or patch produced (result, saved drawing, previews, plan)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from visio_mcp.plan import DiagramPlan
from visio_mcp.spec import RenderResult


@dataclass
class DrawOutput:
    result: RenderResult
    vsdx: Path | None
    target: Literal["visio", "native"]
    plan: DiagramPlan | None = None
    previews: dict[str, Path] = field(default_factory=dict)  # format -> file

    @property
    def png(self) -> Path | None:
        return self.previews.get("png")
