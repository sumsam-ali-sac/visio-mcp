"""Read back what is on the Visio page: shapes, connectors and overlapping pairs."""

from __future__ import annotations

from typing import Any

from visio_mcp.output.visio.backend import ShapeInfo, VisioBackend

EPS = 1e-6


def inspect(backend: VisioBackend) -> dict[str, Any]:
    """{'shapes': [...], 'connectors': [...], 'overlaps': [...]} for an agent to review."""
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
            {"id": s.name, **connector_ends(s.name), "label": s.text} for s in shapes if s.is_connector
        ],
        "overlaps": find_overlaps(shapes),
    }


def find_overlaps(shapes: list[ShapeInfo]) -> list[tuple[str, str]]:
    """Pairs of node shapes whose boxes intersect (connectors, containers, decorations ignored)."""
    boxes = [s for s in shapes if not (s.is_connector or s.is_container or s.name.startswith("__"))]
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


def connector_ends(name: str) -> dict[str, str]:
    """Source/target from a connector name like 'a->b' or 'a->b#2'."""
    base, _, n = name.rpartition("#")
    if not (base and n.isdigit()):
        base = name
    source, _, target = base.partition("->")
    return {"source": source, "target": target}
