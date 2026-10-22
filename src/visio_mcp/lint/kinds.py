"""Category and provider of a node kind, from the catalog with name-based fallbacks."""

from __future__ import annotations

from dataclasses import dataclass

from visio_mcp import catalog

PREFIXES = {"azure-": "azure", "aws-": "aws", "gcp-": "gcp", "google-": "gcp", "amazon-": "aws"}

# Category by kind name, used when the catalog does not know a kind or leaves it generic.
NAME_CATEGORY: dict[str, str] = {
    **dict.fromkeys(("start", "end", "initial", "final", "initial-state", "final-state", "terminator"), "terminal"),
    **dict.fromkeys(("process", "subprocess", "manual", "document", "data", "state", "composite-state"), "flow"),
    **dict.fromkeys(("decision", "choice"), "decision"),
    **dict.fromkeys(("database", "cache", "storage"), "data"),
    **dict.fromkeys(("service", "function", "server", "container", "c4-container"), "compute"),
    **dict.fromkeys(("queue", "api", "gateway"), "integration"),
    **dict.fromkeys(("client", "mobile", "webapp", "pc"), "client"),
    **dict.fromkeys(("user", "person"), "person"),
    **dict.fromkeys(("external", "external-system", "system-external"), "external"),
    **dict.fromkeys(("router", "switch", "loadbalancer", "cloud", "internet"), "network"),
    "firewall": "security",
    **dict.fromkeys(("executive", "manager", "position"), "org"),
    "entity": "entity",
    "note": "note",
}

STATE_NAMES = {"state", "composite-state", "initial-state", "final-state", "initial", "final"}
START_NAMES = {"start", "initial", "initial-state", "terminator"}
END_NAMES = {"end", "final", "final-state"}
SYSTEM_NAMES = {"system", "software-system", "c4-system", "external-system", "system-external"}
CONTAINER_NAMES = {"container", "c4-container"}
MINDMAP_NAMES = {"mindmap-root", "mindmap-topic", "central-idea"}
PIPELINE_NAMES = {"pipeline", "build", "test", "deploy"}
DATAFLOW_NAMES = {"etl", "data-lake", "data-warehouse"}


@dataclass(frozen=True)
class KindInfo:
    name: str  # canonical kind name (or the raw kind, lowercased, when unknown)
    category: str
    provider: str | None
    known: bool


def kind_info(kind: str) -> KindInfo:
    """Category and provider of a kind, from the catalog with name-based fallbacks."""
    raw = kind.strip().lower()
    k = catalog.lookup(kind)
    name = k.name if k else raw
    provider = k.provider if k else None
    if not provider:
        provider = next((p for pre, p in PREFIXES.items() if raw.startswith(pre) or name.startswith(pre)), None)
    category = k.category if k else "generic"
    if category in ("", "generic"):
        category = NAME_CATEGORY.get(name, NAME_CATEGORY.get(raw, category or "generic"))
    return KindInfo(name, category, provider, k is not None)
