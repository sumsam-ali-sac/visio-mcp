"""The Finding record, its severity ranking and the list of rule codes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["high", "medium", "low"]
SEVERITY_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


RULE_CODES: tuple[str, ...] = (
    "size", "decision", "lane", "orphan", "terminal", "c4-context", "provider-kinds", "mixed-providers",
    "unknown-kind", "label-length", "duplicate-label", "erd-cardinality", "state-events", "edge-labels",
    "external-placement", "nesting", "nesting-order", "layout", "emphasis", "title", "single-member",
    "bidirectional", "self-loop", "duplicate-edge", "edge-label-length", "colors",
)
