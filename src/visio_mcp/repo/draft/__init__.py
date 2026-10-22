"""No-AI fallback: turn profiled repos into a valid, decent-looking DiagramSpec."""

from __future__ import annotations

from visio_mcp.spec import DiagramSpec, Node

from ..model import RepoInfo
from .architecture import build_architecture
from .builder import catalog_kind
from .deployment import build_deployment
from .pipeline import build_pipeline


def heuristic_spec(repos: list[RepoInfo], diagram_type: str = "architecture") -> DiagramSpec:
    """A no-AI diagram of the scanned repos. Always returns a valid DiagramSpec."""
    repos = list(repos)
    if not repos:
        return DiagramSpec(title="Architecture", subtitle="Generated from repository scan", type="architecture",
                           nodes=[Node(id="system", label="System", kind=catalog_kind("service"))])
    if diagram_type == "pipeline":
        return build_pipeline(repos)
    if diagram_type == "deployment":
        return build_deployment(repos)
    return build_architecture(repos, "cloud" if diagram_type == "cloud" else "architecture")


__all__ = ["heuristic_spec"]
