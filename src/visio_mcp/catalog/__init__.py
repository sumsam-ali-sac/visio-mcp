"""Semantic shape kinds -> Visio stencil masters."""

from visio_mcp.catalog.aliases import ALIASES
from visio_mcp.catalog.describe import (
    describe_kinds,
    kinds,
    kinds_by_category,
    providers,
)
from visio_mcp.catalog.model import FALLBACK, Kind, Resolved, Shape
from visio_mcp.catalog.resolve import lookup, resolve, suggest

__all__ = [
    "ALIASES", "FALLBACK", "Kind", "Resolved", "Shape", "describe_kinds", "kinds",
    "kinds_by_category", "lookup", "providers", "resolve", "suggest",
]
