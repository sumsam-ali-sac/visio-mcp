"""Apply patch ops to a spec. The patched spec is then redrawn, so styling and layout stay consistent."""

from __future__ import annotations

from pydantic import ValidationError

from visio_mcp.spec import (
    edge_name,
    AddEdge,
    AddGroup,
    AddNode,
    DiagramSpec,
    Move,
    PatchOp,
    Relayout,
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
            warnings.append(f"op {i} ({op.op} {op_target(op)!r}): {_reason(e)}")
            continue
        data = trial
    return DiagramSpec.model_validate(data), moves, warnings


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
        n = edge_name(f"{e['source']}->{e['target']}", taken)
        taken.add(n)
        if n == name:
            return i
    raise KeyError(f"no edge named {name!r}")


def _reason(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
    return e.args[0] if isinstance(e, KeyError) and e.args else str(e)


def op_target(op: PatchOp) -> str:
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
