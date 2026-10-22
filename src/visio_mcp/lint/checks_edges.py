"""Rules about edge direction and repetition, and colour/emphasis overrides."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from visio_mcp.lint.context import Context, quoted
from visio_mcp.lint.finding import Finding

MAX_EMPHASIS = 2
MAX_CUSTOM_COLORS = 3


def check_bidirectional(c: Context) -> Iterator[Finding]:
    edges = c.spec.edges
    pairs = {(e.source, e.target) for e in edges}
    both = sum(e.arrow == "both" for e in edges)
    recip = sum(1 for (s, t) in pairs if s < t and (t, s) in pairs)
    count = both + recip
    if count > 2 and count * 5 > len(edges):
        yield Finding("bidirectional", "low", f"{count} edges are two-way; show the direction of the call or "
                      "data flow (who initiates) and keep two-way arrows for truly symmetric links.")


def check_self_loop(c: Context) -> Iterator[Finding]:
    if c.type == "state":
        return
    loops = [e.source for e in c.spec.edges if e.source == e.target]
    if loops:
        yield Finding("self-loop", "low", f"Self-loops on {quoted(loops)}; describe repetition in the node's "
                      "description or model it as an explicit retry step.")


def check_duplicate_edge(c: Context) -> Iterator[Finding]:
    counts = Counter((e.source, e.target, e.label.lower()) for e in c.spec.edges)
    dup = [f"{s}->{t}" for (s, t, _), k in counts.items() if k > 1]
    if dup:
        yield Finding("duplicate-edge", "low", f"Edges {quoted(dup)} are repeated with the same label; keep one.")


def check_emphasis(c: Context) -> Iterator[Finding]:
    hot = [n.id for n in c.spec.nodes if n.emphasis]
    if len(hot) > MAX_EMPHASIS:
        yield Finding("emphasis", "medium", f"{len(hot)} nodes are emphasized ({quoted(hot)}); emphasize at most "
                      f"{MAX_EMPHASIS} so the highlight still means something.")


def check_colors(c: Context) -> Iterator[Finding]:
    fills = {x.fill.upper() for x in [*c.spec.nodes, *c.spec.groups] if x.fill}
    lines = {e.color.upper() for e in c.spec.edges if e.color}
    if len(fills) > MAX_CUSTOM_COLORS or len(lines) > 2:
        yield Finding("colors", "low", f"{len(fills)} custom fills and {len(lines)} custom line colors; let the "
                      "theme color by category and keep overrides to 1-2 for emphasis.")
