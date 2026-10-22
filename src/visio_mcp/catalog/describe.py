"""Listings of the catalog for tools and LLM prompts."""

from __future__ import annotations

from visio_mcp.catalog.cloud import CLOUD_KINDS
from visio_mcp.catalog.generic import GENERIC_KINDS
from visio_mcp.catalog.model import Kind
from visio_mcp.catalog.registry import BY_NAME


def kinds() -> dict[str, Kind]:
    """All known kinds, keyed by name."""
    return dict(BY_NAME)


def providers() -> tuple[str, ...]:
    """Cloud providers that have service kinds."""
    return tuple(sorted({k.provider for k in BY_NAME.values() if k.provider}))


def kinds_by_category() -> dict[str, list[Kind]]:
    """Generic (non-provider) kinds grouped by style category, in catalog order."""
    out: dict[str, list[Kind]] = {}
    for k in GENERIC_KINDS:
        out.setdefault(k.category, []).append(k)
    return out


def describe_kinds(provider: str | None = None) -> str:
    """Compact markdown listing of kinds for LLM prompts: generic by category, then a provider's cloud kinds."""
    lines = ["## Kinds (generic)"]
    for cat, ks in kinds_by_category().items():
        lines.append(f"- **{cat}**: " + "; ".join(f"`{k.name}` {k.description.rstrip('.')}" for k in ks))
    wanted = [p for p in providers() if provider is None or p == provider.strip().lower()]
    for p in wanted:
        lines.append(f"## Kinds ({p})")
        ks = [k for k in CLOUD_KINDS if k.provider == p]
        lines.append("- " + "; ".join(f"`{k.name}` {k.description.rstrip('.')}" for k in ks))
    return "\n".join(lines)
