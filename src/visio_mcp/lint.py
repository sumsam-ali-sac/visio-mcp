"""Diagram rules: normalize a spec (fill in 'auto', fix casing) and lint it. PLACEHOLDER."""

from __future__ import annotations

from visio_mcp.spec import DiagramSpec
from visio_mcp.style import sentence_case, title_case


def normalize(spec: DiagramSpec) -> tuple[DiagramSpec, list[str]]:
    """Resolve type/layout/theme 'auto' and apply label casing. Returns (spec, notes)."""
    layout = "flowchart-tb" if spec.layout == "auto" else spec.layout
    theme = "professional" if spec.theme == "auto" else spec.theme
    nodes = [n.model_copy(update={"label": title_case(n.label or n.id)}) for n in spec.nodes]
    edges = [e.model_copy(update={"label": sentence_case(e.label)}) for e in spec.edges]
    groups = [g.model_copy(update={"label": title_case(g.label or g.id)}) for g in spec.groups]
    return spec.model_copy(update={"layout": layout, "theme": theme, "nodes": nodes, "edges": edges,
                                   "groups": groups}), []


def lint(spec: DiagramSpec) -> list[str]:
    """Rule findings for a normalized spec. Empty when it follows the ground rules."""
    return []
