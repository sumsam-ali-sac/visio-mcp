"""Normalize a spec: resolve 'auto' type/layout/theme, fill empty labels and apply label casing."""

from __future__ import annotations

import re

from visio_mcp.lint.infer import LAYOUTS, dominant_provider, infer_type
from visio_mcp.spec import DiagramSpec
from visio_mcp.style import sentence_case, title_case


def humanize(ident: str) -> str:
    """'orders_db' -> 'Orders DB', 'paymentService' -> 'Payment Service'."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", ident)
    return title_case(" ".join(re.sub(r"[_\-.]+", " ", text).split()))


def _clean(text: str) -> str:
    return " ".join(text.split())


def normalize(spec: DiagramSpec) -> tuple[DiagramSpec, list[str]]:
    """Resolve type/layout/theme 'auto', fill empty labels, tidy whitespace and apply label
    casing (Title Case for nodes and groups, lowercase phrases for edges).

    Returns a new spec and a short list of human-readable notes on what changed.
    """
    notes: list[str] = []
    dtype = spec.type
    if dtype == "auto":
        dtype = infer_type(spec)
        notes.append(f"type auto -> {dtype}")
    layout = spec.layout
    if layout == "auto":
        layout = LAYOUTS.get(dtype, "flowchart-lr")
        notes.append(f"layout auto -> {layout}")
    theme = spec.theme
    if theme.strip().lower() in ("auto", ""):
        if dtype == "cloud":
            theme = dominant_provider(spec) or "professional"
        elif dtype.startswith("c4-"):
            theme = "c4"
        else:
            theme = "professional"
        notes.append(f"theme auto -> {theme}")

    recased = filled = 0

    def node_label(label: str, ident: str) -> str:
        nonlocal recased, filled
        clean = _clean(label)
        if not clean:
            filled += 1
            return humanize(ident)
        out = title_case(clean)
        recased += out != label
        return out

    def edge_label(label: str) -> str:
        nonlocal recased
        clean = _clean(label)
        out = sentence_case(clean) if clean else ""
        recased += out != label
        return out

    nodes = [n.model_copy(update={
        "label": node_label(n.label, n.id),
        "technology": _clean(n.technology),
        "description": _clean(n.description),
    }) for n in spec.nodes]
    groups = [g.model_copy(update={"label": node_label(g.label, g.id)}) for g in spec.groups]
    edges = [e.model_copy(update={"label": edge_label(e.label)}) for e in spec.edges]
    if filled:
        notes.append(f"filled {filled} empty label(s) from ids")
    if recased:
        notes.append(f"recased {recased} label(s) (Title Case nodes/groups, lowercase edge phrases)")
    out = spec.model_copy(update={
        "type": dtype, "layout": layout, "theme": theme, "title": _clean(spec.title),
        "subtitle": _clean(spec.subtitle), "nodes": nodes, "edges": edges, "groups": groups,
    })
    return out, notes
