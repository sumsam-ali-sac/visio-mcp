"""Render without Visio: native .vsdx plus SVG/PNG/HTML/PDF previews, and plan-based inspection."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from visio_mcp.output import svg
from visio_mcp.output.files import save_free
from visio_mcp.output.result import DrawOutput
from visio_mcp.output.visio.backend import ShapeInfo
from visio_mcp.output.visio.inspect import find_overlaps
from visio_mcp.output.vsdx import write_vsdx
from visio_mcp.plan import DiagramPlan, build_plan
from visio_mcp.spec import DiagramSpec, RenderResult

Progress = Callable[[str], None]


def render(spec: DiagramSpec, vsdx: Path, formats: list[str], progress: Progress | None = None) -> DrawOutput:
    """Plan the spec, write vsdx (or a free name next to it) and the requested previews."""
    say = progress or (lambda _m: None)
    say("Planning layout")
    plan = build_plan(spec)
    say("Writing .vsdx")
    vsdx.parent.mkdir(parents=True, exist_ok=True)
    saved, warning = save_free(lambda p: write_vsdx(plan, p), vsdx)
    say("Rendering previews")
    files = previews(plan, saved, formats)
    warnings = list(plan.warnings) + ([warning] if warning else [])
    missing = [f for f in formats if f not in files]
    if missing:
        warnings.append(f"no renderer for {', '.join(missing)} on this machine; skipped")
    result = RenderResult(
        shapes=len(plan.nodes) + len(plan.groups), connectors=len(plan.edges), warnings=warnings,
        suggestions=plan.suggestions, overlaps=plan_overlaps(plan),
        files=[str(saved)] + [str(p) for p in files.values()],
    )
    return DrawOutput(result, Path(saved), "native", plan, files)


def previews(plan: DiagramPlan, base: Path, formats: list[str]) -> dict[str, Path]:
    """Preview files next to base (same stem) for the formats that can be made here."""
    out: dict[str, Path] = {}
    wanted = set(formats)
    svg_path = base.with_suffix(".svg")
    if wanted & {"svg", "png", "pdf"}:
        svg_path.write_text(svg.render_svg(plan), encoding="utf-8")
        if "svg" in wanted:
            out["svg"] = svg_path
    if "png" in wanted:
        png = svg.svg_to_png(svg_path, base.with_suffix(".png")) or soffice_convert(base.with_suffix(".vsdx"), "png")
        if png:
            out["png"] = Path(png)
    if "pdf" in wanted and (pdf := soffice_convert(base.with_suffix(".vsdx"), "pdf")):
        out["pdf"] = pdf
    if "html" in wanted:
        out["html"] = Path(svg.write_html(plan, base.with_suffix(".html")))
    if "svg" not in wanted:
        svg_path.unlink(missing_ok=True)  # only drawn as the source of png/pdf
    return out


def soffice_convert(vsdx: Path, fmt: str) -> Path | None:
    """Convert a .vsdx with LibreOffice, when it is installed (PDF/PNG without Visio)."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe or not vsdx.exists():
        return None
    try:
        subprocess.run([exe, "--headless", "--convert-to", fmt, "--outdir", str(vsdx.parent), str(vsdx)],
                       check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None
    out = vsdx.with_suffix(f".{fmt}")
    return out if out.exists() else None


def inspect_plan(plan: DiagramPlan) -> dict[str, Any]:
    """Shapes, groups, connectors and overlaps of a planned diagram, like visio.inspect reports them."""
    return {
        "shapes": [{"id": n.id, "text": n.label, "kind": n.kind, "x": round(n.shape.x, 2),
                    "y": round(n.shape.y, 2), "width": n.shape.w, "height": n.shape.h} for n in plan.nodes],
        "groups": [{"id": g.id, "label": g.label, "members": g.members} for g in plan.groups],
        "connectors": [{"id": e.name, "source": e.source, "target": e.target, "label": e.label}
                       for e in plan.edges],
        "overlaps": plan_overlaps(plan),
    }


def plan_overlaps(plan: DiagramPlan) -> list[tuple[str, str]]:
    return find_overlaps([
        ShapeInfo(n.id, n.label, None, n.rect.x, n.rect.y, n.rect.w, n.rect.h) for n in plan.nodes
    ])
