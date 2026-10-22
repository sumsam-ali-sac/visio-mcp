"""DiagramSpec -> shapes on the active Visio page."""

from __future__ import annotations

import math

from visio_mcp import catalog
from visio_mcp.backend import ShapeInfo, VisioBackend
from visio_mcp.spec import DiagramSpec, Node, RenderResult

# Provisional grid (inches): roomy enough that default-size shapes never touch.
CELL_W, CELL_H = 2.0, 1.5
EPS = 1e-6


def render_spec(backend: VisioBackend, spec: DiagramSpec) -> RenderResult:
    """Build the whole diagram in a fresh document. Does not save or export (server does)."""
    backend.new_document(spec.title)
    warnings: list[str] = []

    nodes = _group_adjacent(spec)
    manual = spec.layout == "none"
    fixed = [(n.x, n.y) for n in nodes if manual and n.x is not None and n.y is not None]  # type: ignore[misc]
    cols = max(1, math.ceil(math.sqrt(len(nodes))))
    slot = 0
    for node in nodes:
        if manual and node.x is not None and node.y is not None:
            x, y = node.x, node.y
        else:
            x, y, slot = _next_slot(slot, cols, fixed)
        warnings += draw_node(backend, node, x, y)

    taken: set[str] = set()
    for e in spec.edges:
        name = unique_edge_name(f"{e.source}->{e.target}", taken)
        taken.add(name)
        backend.connect(name, e.source, e.target, e.label, e.style, e.arrow)

    backend.layout(spec.layout)

    groups = 0
    for g in spec.groups:
        members = [n.id for n in spec.nodes if n.group == g.id]
        if not members:
            warnings.append(f"group {g.id!r} has no members; skipped")
            continue
        backend.add_container(g.id, g.label or g.id, members)
        groups += 1

    return RenderResult(
        shapes=len(spec.nodes) + groups,
        connectors=len(spec.edges),
        warnings=_dedupe(warnings),
        overlaps=find_overlaps(backend.shapes()),
    )


def draw_node(backend: VisioBackend, node: Node, x: float, y: float) -> list[str]:
    """Drop one node (shape, text, fill) at (x, y). Returns warnings."""
    resolved = catalog.resolve(node.kind, backend.has_master)
    backend.drop_shape(node.id, resolved.shape.stencil, resolved.shape.master, x, y)
    backend.set_text(node.id, node.label or node.id)
    fill = node.fill or resolved.fill
    if fill:
        backend.set_fill(node.id, fill)
    return [resolved.warning] if resolved.warning else []


def unique_edge_name(base: str, taken: set[str]) -> str:
    """'a->b', then 'a->b#2', 'a->b#3' ... for repeated edges."""
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}#{n}"
    return name


def find_overlaps(shapes: list[ShapeInfo]) -> list[tuple[str, str]]:
    """Pairs of non-connector, non-container shapes whose boxes intersect."""
    boxes = [s for s in shapes if not (s.is_connector or s.is_container)]
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            dx = abs(a.x - b.x) - (a.width + b.width) / 2
            dy = abs(a.y - b.y) - (a.height + b.height) / 2
            if dx < -EPS and dy < -EPS:
                pair = tuple(sorted((a.name, b.name)))
                if pair not in pairs:
                    pairs.append(pair)  # type: ignore[arg-type]
    return pairs


def _group_adjacent(spec: DiagramSpec) -> list[Node]:
    """Node order with each group's members next to each other."""
    out: list[Node] = []
    seen: set[str] = set()
    for n in spec.nodes:
        if n.group is None:
            out.append(n)
        elif n.group not in seen:
            seen.add(n.group)
            out += [m for m in spec.nodes if m.group == n.group]
    return out


def _next_slot(slot: int, cols: int, fixed: list[tuple[float, float]]) -> tuple[float, float, int]:
    """First grid slot from `slot` on that doesn't crowd a fixed-position node."""
    while True:
        x, y = 1 + (slot % cols) * CELL_W, 1 + (slot // cols) * CELL_H
        slot += 1
        if all(abs(x - fx) >= CELL_W or abs(y - fy) >= CELL_H for fx, fy in fixed):
            return x, y, slot


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
