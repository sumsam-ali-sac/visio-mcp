"""Infer a diagram's type, default layout and dominant provider from its nodes."""

from __future__ import annotations

from collections import Counter

from visio_mcp.lint.kinds import (
    CONTAINER_NAMES,
    DATAFLOW_NAMES,
    MINDMAP_NAMES,
    PIPELINE_NAMES,
    STATE_NAMES,
    SYSTEM_NAMES,
    kind_info,
)
from visio_mcp.spec import DiagramSpec

# Default layout per diagram type.
LAYOUTS: dict[str, str] = {
    "flowchart": "flowchart-tb",
    "architecture": "flowchart-lr",
    "cloud": "flowchart-lr",
    "c4-context": "flowchart-lr",
    "c4-container": "flowchart-lr",
    "deployment": "flowchart-lr",
    "network": "flowchart-tb",
    "dataflow": "flowchart-lr",
    "pipeline": "flowchart-lr",
    "erd": "flowchart-lr",
    "org": "tree-tb",
    "swimlane": "swimlane-lr",
    "state": "flowchart-tb",
    "mindmap": "radial",
}


def infer_type(spec: DiagramSpec) -> str:
    """Guess the diagram type from node kinds and group kinds."""
    infos = [kind_info(n.kind) for n in spec.nodes]
    names = {i.name for i in infos}
    cats = Counter(i.category for i in infos)
    gkinds = {g.kind for g in spec.groups}
    if "lane" in gkinds:
        return "swimlane"
    if names & STATE_NAMES:
        return "state"
    if cats["entity"]:
        return "erd"
    if cats["org"]:
        return "org"
    if names & MINDMAP_NAMES:
        return "mindmap"
    if names & PIPELINE_NAMES:
        return "pipeline"
    if cats["decision"] or cats["terminal"]:
        return "flowchart"
    if any(i.provider for i in infos):
        return "cloud"
    if cats["person"] and (names & CONTAINER_NAMES or "system" in gkinds):
        return "c4-container"
    if cats["person"] and names & SYSTEM_NAMES:
        return "c4-context"
    if names & {"router", "switch"} or (cats["network"] + cats["security"]) * 2 >= len(infos):
        return "network"
    if gkinds & {"environment", "cluster"} or "server" in names:
        return "deployment"
    if names & DATAFLOW_NAMES:
        return "dataflow"
    return "architecture"


def dominant_provider(spec: DiagramSpec) -> str | None:
    """Most used provider among the nodes (ties go to the first one seen)."""
    counts = Counter(p for n in spec.nodes if (p := kind_info(n.kind).provider))
    if not counts:
        return None
    best = max(counts.values())
    return next(p for p in counts if counts[p] == best)
