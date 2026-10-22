"""Run every check over a spec and report the findings, capped for the agent."""

from __future__ import annotations

from visio_mcp.lint.checks_cloud import check_providers, check_unknown_kind
from visio_mcp.lint.checks_edges import (
    check_bidirectional,
    check_colors,
    check_duplicate_edge,
    check_emphasis,
    check_self_loop,
)
from visio_mcp.lint.checks_flow import (
    check_c4_context,
    check_decision,
    check_erd,
    check_state_events,
    check_terminal,
)
from visio_mcp.lint.checks_labels import (
    check_duplicate_label,
    check_edge_label_length,
    check_edge_labels,
    check_label_length,
    check_title,
)
from visio_mcp.lint.checks_structure import (
    check_external,
    check_lane,
    check_layout,
    check_nesting,
    check_orphan,
    check_single_member,
    check_size,
)
from visio_mcp.lint.context import Context
from visio_mcp.lint.finding import SEVERITY_RANK, Finding
from visio_mcp.spec import DiagramSpec

MAX_FINDINGS = 15

# Each check takes the context and yields findings. Order within a severity = list order.
CHECKS = (
    check_size, check_decision, check_lane,
    check_orphan, check_terminal, check_c4_context, check_providers, check_unknown_kind, check_label_length,
    check_duplicate_label, check_erd, check_state_events, check_edge_labels, check_external, check_nesting,
    check_layout, check_emphasis, check_title, check_single_member, check_bidirectional, check_self_loop,
    check_duplicate_edge, check_edge_label_length, check_colors,
)


def findings(spec: DiagramSpec) -> list[Finding]:
    """All rule findings, most important first (uncapped)."""
    c = Context(spec)
    out: list[Finding] = []
    for rule in CHECKS:
        out.extend(rule(c))
    return sorted(out, key=lambda f: SEVERITY_RANK[f.severity])  # stable: rule order within a severity


def lint(spec: DiagramSpec) -> list[str]:
    """Rule findings for a normalized spec. Empty when it follows the ground rules."""
    found = [str(f) for f in findings(spec)]
    if len(found) > MAX_FINDINGS:
        rest = len(found) - (MAX_FINDINGS - 1)
        found = found[: MAX_FINDINGS - 1] + [f"[more] {rest} more findings not shown; fix these and re-check."]
    return found
