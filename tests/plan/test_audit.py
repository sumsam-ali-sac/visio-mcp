"""Geometry audit of finished plans: clean for every example and preset, loud when broken."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from visio_mcp.layout import Rect
from visio_mcp.plan import build_plan
from visio_mcp.plan.audit import audit
from visio_mcp.spec import DiagramSpec

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "examples").glob("*.json"))
PRESETS = ["flowchart-tb", "flowchart-lr", "tree-tb", "tree-lr", "swimlane-lr", "swimlane-tb",
           "radial", "circular", "grid", "none"]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
@pytest.mark.parametrize("preset", [None, *PRESETS])
def test_examples_pass_geometry_audit(path: Path, preset: str | None):
    spec = DiagramSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if preset:
        spec = spec.model_copy(update={"layout": preset})
    assert audit(build_plan(spec)) == []


def test_audit_reports_overlapping_nodes():
    spec = DiagramSpec.model_validate({"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]})
    plan = build_plan(spec)
    a, b = plan.nodes
    plan.nodes[1] = replace(b, rect=Rect(a.rect.x, a.rect.y, b.rect.w, b.rect.h))
    assert audit(plan)
