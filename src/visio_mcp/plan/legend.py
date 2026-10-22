"""Legend: which entries to show, how big the box is and where each sample sits."""

from __future__ import annotations

from dataclasses import replace

from visio_mcp.layout import Rect
from visio_mcp.style import TextRun
from visio_mcp.plan.model import LegendEntry, TextBlock
from visio_mcp.plan.runs import line_width
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import Theme

_CATEGORY_NAMES = {
    "terminal": "Start / end", "flow": "Process step", "decision": "Decision", "data": "Data store",
    "compute": "Service / compute", "integration": "Messaging / integration", "client": "Client app",
    "person": "Person / actor", "external": "External system", "network": "Network", "security": "Security",
    "org": "Position", "entity": "Entity", "note": "Note", "generic": "Component",
}
_PATTERN_NAMES = {"solid": "Synchronous call", "dashed": "Asynchronous / event", "dotted": "Optional / weak"}


def legend_entries(spec: DiagramSpec, theme: Theme, resolved: dict) -> list[LegendEntry]:
    """One entry per node category used, per line pattern used and per group kind used."""
    entries: list[LegendEntry] = []
    seen: set[str] = set()
    for n in spec.nodes:
        kind, _, icon = resolved[n.id]
        cat = kind.category if kind else "generic"
        if cat in seen or icon:
            continue  # icons explain themselves
        seen.add(cat)
        entries.append(LegendEntry(_CATEGORY_NAMES.get(cat, cat.title()), "node", theme.node_style(cat),
                                   kind.geometry if kind else "rounded"))
    patterns = list(dict.fromkeys(e.style for e in spec.edges))
    if len(patterns) > 1:
        for p in patterns:
            entries.append(LegendEntry(_PATTERN_NAMES[p], "edge", pattern=p, color=theme.edge.color))
    special = [g for g in spec.groups if g.kind in ("boundary", "external", "network", "subnet", "region", "zone")]
    for kind in dict.fromkeys(g.kind for g in special):
        entries.append(LegendEntry({"boundary": "Trust boundary", "external": "External", "network": "Virtual network",
                                    "subnet": "Subnet", "region": "Region", "zone": "Availability zone"}[kind],
                                   "group", theme.group_style(kind).shape))
    # a legend that only repeats one entry adds nothing
    return entries if len(entries) >= 2 else []


LEGEND_ROW = 0.32
LEGEND_SAMPLE_W = 0.5
LEGEND_PAD = 0.18


def legend_size(entries: list[LegendEntry], theme: Theme) -> tuple[float, float]:
    if not entries:
        return 0.0, 0.0
    st = theme.legend.text
    text_w = max(line_width(e.label, replace(st, size=9)) for e in entries)
    cols = 1 if len(entries) <= 5 else 2
    rows = -(-len(entries) // cols)
    col_w = LEGEND_SAMPLE_W + 0.15 + text_w + 0.2
    return round(cols * col_w + 2 * LEGEND_PAD, 3), round(rows * LEGEND_ROW + 0.35 + 2 * LEGEND_PAD, 3)


def place_legend(frame: Rect, entries: list[LegendEntry], theme: Theme) -> tuple[TextBlock, list]:
    st = replace(theme.legend.text, size=9)
    head = TextBlock(Rect(frame.left + LEGEND_PAD + 0.6, frame.top - LEGEND_PAD - 0.12, 1.2, 0.24),
                     [TextRun("Legend", replace(st, bold=True))])
    cols = 1 if len(entries) <= 5 else 2
    rows = -(-len(entries) // cols)
    col_w = (frame.w - 2 * LEGEND_PAD) / cols
    out = []
    for i, e in enumerate(entries):
        c, r = divmod(i, rows)
        x0 = frame.left + LEGEND_PAD + c * col_w
        y = frame.top - LEGEND_PAD - 0.35 - r * LEGEND_ROW - LEGEND_ROW / 2
        sample = Rect(x0 + LEGEND_SAMPLE_W / 2, y, LEGEND_SAMPLE_W, 0.2)
        text_w = col_w - LEGEND_SAMPLE_W - 0.15
        text = Rect(x0 + LEGEND_SAMPLE_W + 0.15 + text_w / 2, y, text_w, 0.24)
        out.append((sample, text, e))
    return head, out
