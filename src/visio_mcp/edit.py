"""Small edits to a diagram, and inspection.

Two modes:
- apply_to_spec: the diagram was drawn from a spec in this session. Ops edit the spec,
  which is then re-rendered, so styling and layout stay consistent.
- apply_ops: the diagram was opened from disk. Ops edit the shapes directly.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from visio_mcp.backend import ShapeInfo, VisioBackend
from visio_mcp.plan import unique_edge_name
from visio_mcp.render import draw_node, find_overlaps
from visio_mcp.spec import (
    AddEdge,
    AddGroup,
    AddNode,
    DiagramSpec,
    Move,
    PatchOp,
    Relayout,
    RenderResult,
    Remove,
    UpdateDiagram,
    UpdateEdge,
    UpdateNode,
)


def apply_to_spec(spec: DiagramSpec, ops: list[PatchOp]) -> tuple[DiagramSpec, list[Move], list[str]]:
    """Apply ops to a copy of spec. Returns (new spec, moves to apply after re-render, warnings).

    Bad ops become warnings and are skipped; the rest still apply.
    """
    data = spec.model_dump()
    moves: list[Move] = []
    warnings: list[str] = []
    for i, op in enumerate(ops, 1):
        if isinstance(op, Move):
            moves.append(op)
            continue
        try:
            trial = _spec_op(_copy(data), op)
            DiagramSpec.model_validate(trial)
        except (ValidationError, ValueError, KeyError) as e:
            warnings.append(f"op {i} ({op.op} {_target(op)!r}): {_reason(e)}")
            continue
        data = trial
    return DiagramSpec.model_validate(data), moves, warnings


def apply_ops(backend: VisioBackend, ops: list[PatchOp]) -> RenderResult:
    """Apply ops to the open page's shapes, in order. Bad ops become warnings."""
    warnings: list[str] = []
    for i, op in enumerate(ops, 1):
        try:
            warnings += _apply(backend, op) or []
        except (KeyError, ValueError, RuntimeError) as e:
            msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
            warnings.append(f"op {i} ({op.op} {_target(op)!r}): {msg}")

    shapes = backend.shapes()
    nodes = [s for s in shapes if not (s.is_connector or s.name.startswith("__"))]
    return RenderResult(
        shapes=len(nodes),
        connectors=sum(1 for s in shapes if s.is_connector),
        warnings=list(dict.fromkeys(warnings)),
        overlaps=find_overlaps(shapes),
    )


def inspect(backend: VisioBackend) -> dict[str, Any]:
    """{'shapes': [...], 'connectors': [...], 'overlaps': [...]} for the agent to review."""
    shapes = [s for s in backend.shapes() if not s.name.startswith("__")]
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


# --- spec mode -------------------------------------------------------------------------------


def _copy(data: dict) -> dict:
    return DiagramSpec.model_validate(data).model_dump()


def _spec_op(d: dict, op: PatchOp) -> dict:
    nodes, edges, groups = d["nodes"], d["edges"], d["groups"]
    if isinstance(op, AddNode):
        nodes.append(op.node.model_dump())
    elif isinstance(op, UpdateNode):
        node = _find(nodes, op.id, "node")
        for field in ("label", "kind", "technology", "description", "emphasis", "fill"):
            if (v := getattr(op, field)) is not None:
                node[field] = v
        if op.group is not None:
            node["group"] = op.group or None
    elif isinstance(op, UpdateEdge):
        edge = edges[_edge_index(edges, op.id)]
        for field in ("label", "style", "arrow", "color"):
            if (v := getattr(op, field)) is not None:
                edge[field] = v
    elif isinstance(op, AddGroup):
        groups.append(op.group.model_dump())
        for nid in op.members:
            _find(nodes, nid, "node")["group"] = op.group.id
    elif isinstance(op, UpdateDiagram):
        for field in ("title", "subtitle", "theme", "layout", "legend"):
            if (v := getattr(op, field)) is not None:
                d[field] = v
    elif isinstance(op, AddEdge):
        edges.append(op.edge.model_dump())
    elif isinstance(op, Relayout):
        d["layout"] = op.layout
    elif isinstance(op, Remove):
        _remove(d, op.id)
    return d


def _remove(d: dict, target: str) -> None:
    if "->" in target:
        del d["edges"][_edge_index(d["edges"], target)]
    elif any(n["id"] == target for n in d["nodes"]):
        d["nodes"] = [n for n in d["nodes"] if n["id"] != target]
        d["edges"] = [e for e in d["edges"] if target not in (e["source"], e["target"])]
    elif any(g["id"] == target for g in d["groups"]):
        parent = _find(d["groups"], target, "group")["parent"]
        d["groups"] = [g for g in d["groups"] if g["id"] != target]
        for item in d["nodes"]:
            if item["group"] == target:
                item["group"] = parent  # members stay, they move up one level
        for g in d["groups"]:
            if g["parent"] == target:
                g["parent"] = parent
    else:
        raise KeyError(f"no node, group or edge named {target!r}")


def _find(items: list[dict], ident: str, what: str) -> dict:
    for item in items:
        if item["id"] == ident:
            return item
    raise KeyError(f"no {what} named {ident!r}")


def _edge_index(edges: list[dict], name: str) -> int:
    taken: set[str] = set()
    for i, e in enumerate(edges):
        n = unique_edge_name(f"{e['source']}->{e['target']}", taken)
        taken.add(n)
        if n == name:
            return i
    raise KeyError(f"no edge named {name!r}")


def _reason(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
    return e.args[0] if isinstance(e, KeyError) and e.args else str(e)


# --- shape mode ------------------------------------------------------------------------------


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
        rest = [f for f in ("kind", "group", "technology", "description", "emphasis") if getattr(op, f) is not None]
        if rest:
            return [f"update_node {op.id!r}: {', '.join(rest)} can only change on diagrams drawn from a spec"]
    elif isinstance(op, UpdateEdge):
        if op.label is not None:
            backend.set_text(op.id, op.label)
        if any(getattr(op, f) is not None for f in ("style", "arrow", "color")):
            return [f"update_edge {op.id!r}: only the label can change on a diagram opened from disk"]
    elif isinstance(op, AddGroup):
        backend.add_container(op.group.id, op.group.label or op.group.id, op.members)
    elif isinstance(op, UpdateDiagram):
        return ["update_diagram needs a diagram drawn from a spec; re-render instead"]
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
    if isinstance(op, AddGroup):
        return op.group.id
    if isinstance(op, Relayout):
        return op.layout
    if isinstance(op, UpdateDiagram):
        return "diagram"
    return op.id


def _free_spot(shapes: list[ShapeInfo]) -> tuple[float, float]:
    """A center to the right of everything on the page, level with the lowest shape."""
    boxes = [s for s in shapes if not (s.is_connector or s.name.startswith("__"))]
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
