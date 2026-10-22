"""Small edits to the open diagram, and inspection."""

from __future__ import annotations

from typing import Any

from visio_mcp.backend import ShapeInfo, VisioBackend
from visio_mcp.render import draw_node, find_overlaps, unique_edge_name
from visio_mcp.spec import (
    AddEdge,
    AddNode,
    Move,
    PatchOp,
    Relayout,
    RenderResult,
    Remove,
    UpdateNode,
)


def apply_ops(backend: VisioBackend, ops: list[PatchOp]) -> RenderResult:
    """Apply ops in order. Bad ops become warnings, they don't abort the batch."""
    warnings: list[str] = []
    for i, op in enumerate(ops, 1):
        try:
            warnings += _apply(backend, op) or []
        except (KeyError, ValueError, RuntimeError) as e:
            msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
            warnings.append(f"op {i} ({op.op} {_target(op)!r}): {msg}")

    shapes = backend.shapes()
    return RenderResult(
        shapes=sum(1 for s in shapes if not s.is_connector),
        connectors=sum(1 for s in shapes if s.is_connector),
        warnings=list(dict.fromkeys(warnings)),
        overlaps=find_overlaps(shapes),
    )


def inspect(backend: VisioBackend) -> dict[str, Any]:
    """{'shapes': [...], 'connectors': [...], 'overlaps': [...]} for the agent to review."""
    shapes = backend.shapes()
    return {
        "shapes": [
            {
                "id": s.name,
                "text": s.text,
                "master": s.master,
                "x": round(s.x, 2),
                "y": round(s.y, 2),
                "width": round(s.width, 2),
                "height": round(s.height, 2),
                "container": s.is_container,
            }
            for s in shapes
            if not s.is_connector
        ],
        "connectors": [
            {"id": s.name, **_ends(s.name), "label": s.text} for s in shapes if s.is_connector
        ],
        "overlaps": find_overlaps(shapes),
    }


def _apply(backend: VisioBackend, op: PatchOp) -> list[str] | None:
    if isinstance(op, AddNode):
        if op.node.x is not None and op.node.y is not None:
            x, y = op.node.x, op.node.y
        else:
            x, y = _free_spot(backend.shapes())
        warnings = draw_node(backend, op.node, x, y)
        if op.node.group:
            warnings.append(f"node {op.node.id!r}: group {op.node.group!r} ignored when patching")
        return warnings
    if isinstance(op, UpdateNode):
        if op.label is not None:
            backend.set_text(op.id, op.label)
        if op.fill is not None:
            backend.set_fill(op.id, op.fill)
    elif isinstance(op, Remove):
        backend.delete(op.id)
    elif isinstance(op, AddEdge):
        e = op.edge
        taken = {s.name for s in backend.shapes()}
        name = unique_edge_name(f"{e.source}->{e.target}", taken)
        backend.connect(name, e.source, e.target, e.label, e.style, e.arrow)
    elif isinstance(op, Move):
        backend.move(op.id, op.x, op.y)
    elif isinstance(op, Relayout):
        backend.layout(op.layout)
    return None


def _target(op: PatchOp) -> str:
    """The id an op is about, for warning messages."""
    if isinstance(op, AddNode):
        return op.node.id
    if isinstance(op, AddEdge):
        return f"{op.edge.source}->{op.edge.target}"
    if isinstance(op, Relayout):
        return op.layout
    return op.id


def _free_spot(shapes: list[ShapeInfo]) -> tuple[float, float]:
    """A center to the right of everything on the page, level with the lowest shape."""
    boxes = [s for s in shapes if not s.is_connector]
    if not boxes:
        return 1.0, 1.0
    right = max(s.x + s.width / 2 for s in boxes)
    return right + 1.0, min(s.y for s in boxes)


def _ends(name: str) -> dict[str, str]:
    """Source/target from a connector name like 'a->b' or 'a->b#2'."""
    base, _, n = name.rpartition("#")
    if not (base and n.isdigit()):
        base = name
    source, _, target = base.partition("->")
    return {"source": source, "target": target}
