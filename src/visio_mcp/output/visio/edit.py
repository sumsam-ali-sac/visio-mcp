"""Patch a diagram opened from disk by editing its Visio shapes directly.

Diagrams drawn from a spec are patched as specs instead (spec/edit.py) and redrawn; this
path only exists for .vsdx files we didn't draw, so it supports the ops that make sense
shape by shape.
"""

from __future__ import annotations

from visio_mcp import catalog
from visio_mcp.output.visio.backend import ShapeInfo, VisioBackend
from visio_mcp.output.visio.inspect import find_overlaps
from visio_mcp.spec import (
    AddEdge,
    AddGroup,
    AddNode,
    Move,
    Node,
    PatchOp,
    Relayout,
    Remove,
    RenderResult,
    UpdateDiagram,
    UpdateEdge,
    UpdateNode,
    edge_name,
)
from visio_mcp.spec.edit import op_target
from visio_mcp.style import PROFESSIONAL, replace

SPEC_ONLY = "can only change on diagrams drawn from a spec"


def apply_ops(backend: VisioBackend, ops: list[PatchOp]) -> RenderResult:
    """Apply ops to the open page's shapes, in order. Bad ops become warnings."""
    warnings: list[str] = []
    for i, op in enumerate(ops, 1):
        try:
            warnings += _apply(backend, op) or []
        except (KeyError, ValueError, RuntimeError) as e:
            msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
            warnings.append(f"op {i} ({op.op} {op_target(op)!r}): {msg}")

    shapes = backend.shapes()
    nodes = [s for s in shapes if not (s.is_connector or s.name.startswith("__"))]
    return RenderResult(
        shapes=len(nodes),
        connectors=sum(1 for s in shapes if s.is_connector),
        warnings=list(dict.fromkeys(warnings)),
        overlaps=find_overlaps(shapes),
    )


def _apply(backend: VisioBackend, op: PatchOp) -> list[str] | None:
    if isinstance(op, AddNode):
        if op.node.x is not None and op.node.y is not None:
            x, y = op.node.x, op.node.y
        else:
            x, y = _free_spot(backend.shapes())
        warnings = _draw_node(backend, op.node, x, y)
        if op.node.group:
            warnings.append(f"node {op.node.id!r}: group {op.node.group!r} {SPEC_ONLY}")
        return warnings
    if isinstance(op, UpdateNode):
        if op.label is not None:
            backend.set_text(op.id, op.label)
        if op.fill is not None:
            backend.set_fill(op.id, op.fill)
        rest = [f for f in ("kind", "group", "technology", "description", "emphasis") if getattr(op, f) is not None]
        if rest:
            return [f"update_node {op.id!r}: {', '.join(rest)} {SPEC_ONLY}"]
    elif isinstance(op, UpdateEdge):
        if op.label is not None:
            backend.set_text(op.id, op.label)
        if any(getattr(op, f) is not None for f in ("style", "arrow", "color")):
            return [f"update_edge {op.id!r}: style, arrow and color {SPEC_ONLY}"]
    elif isinstance(op, AddGroup):
        backend.add_container(op.group.id, op.group.label or op.group.id, op.members)
    elif isinstance(op, (UpdateDiagram, Relayout)):
        return [f"{op.op} {SPEC_ONLY}; render the diagram from a spec instead"]
    elif isinstance(op, Remove):
        backend.delete(op.id)
    elif isinstance(op, AddEdge):
        e = op.edge
        name = edge_name(f"{e.source}->{e.target}", {s.name for s in backend.shapes()})
        backend.connect(name, e.source, e.target, e.label, e.style, e.arrow)
    elif isinstance(op, Move):
        backend.move(op.id, op.x, op.y)
    return None


def _draw_node(backend: VisioBackend, node: Node, x: float, y: float) -> list[str]:
    """Drop one node at (x, y) in the default theme."""
    resolved = catalog.resolve(node.kind, backend.has_master)
    backend.drop_shape(node.id, resolved.shape.stencil, resolved.shape.master, x, y)
    style = PROFESSIONAL.node_style(resolved.kind.category if resolved.kind else "generic")
    if node.fill:
        style = replace(style, fill=node.fill)
    backend.style_shape(node.id, style, keep_fill=resolved.icon, label_below=resolved.icon)
    backend.set_text(node.id, node.label or node.id)
    return [resolved.warning] if resolved.warning else []


def _free_spot(shapes: list[ShapeInfo]) -> tuple[float, float]:
    """A center to the right of everything on the page, level with the lowest shape."""
    boxes = [s for s in shapes if not (s.is_connector or s.name.startswith("__"))]
    if not boxes:
        return 1.0, 1.0
    right = max(s.x + s.width / 2 for s in boxes)
    return right + 1.0, min(s.y for s in boxes)
