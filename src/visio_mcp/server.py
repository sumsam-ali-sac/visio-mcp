"""MCP server: thin tool wrappers. All Visio work runs on the COM thread."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import Image, MCPServer

from visio_mcp import catalog, com_thread, edit, prompts, render
from visio_mcp.backend import VisioBackend
from visio_mcp.spec import DiagramSpec, PatchOp, RenderResult

Format = Literal["png", "svg", "pdf", "jpg"]

mcp = MCPServer(
    name="visio",
    instructions=(
        "Draws native Microsoft Visio diagrams. Describe the diagram as a DiagramSpec "
        "(nodes, edges, groups, layout) and call render_diagram once; then look at the "
        "preview, fix issues with patch_diagram. Call get_authoring_guide first if unsure."
    ),
)

_backend: VisioBackend | None = None
_current: dict[str, Any] = {"vsdx": None, "formats": ["png"]}


def out_dir() -> Path:
    d = Path(os.environ.get("VISIO_MCP_OUT", Path.cwd() / "diagrams"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def backend() -> VisioBackend:
    """Lazily start Visio. Must be called on the COM thread."""
    global _backend
    if _backend is None:
        from visio_mcp.visio_com import VisioCom

        _backend = VisioCom(visible=os.environ.get("VISIO_MCP_VISIBLE") == "1")
    return _backend


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "diagram"


def _write(result: RenderResult, formats: list[str]) -> RenderResult:
    vsdx = Path(_current["vsdx"])
    files = [backend().save(str(vsdx))]
    files += [backend().export(str(vsdx.with_suffix(f".{f}"))) for f in formats]
    return result.model_copy(update={"files": files})


def _reply(result: RenderResult, preview: bool) -> list[Any]:
    out: list[Any] = [result.model_dump_json(indent=1)]
    png = next((f for f in result.files if f.lower().endswith(".png")), None)
    if preview and png:
        out.append(Image(path=png))
    return out


def _render(spec: DiagramSpec, name: str | None, formats: list[str]) -> RenderResult:
    _current["vsdx"] = str(out_dir() / f"{_slug(name or spec.title)}.vsdx")
    _current["formats"] = formats
    return _write(render.render_spec(backend(), spec), formats)


def _patch(ops: list[PatchOp], formats: list[str] | None) -> RenderResult:
    if not _current["vsdx"]:
        raise ValueError("no diagram open: call render_diagram or open_diagram first")
    result = edit.apply_ops(backend(), ops)
    return _write(result, formats if formats is not None else _current["formats"])


def _open(path: str) -> dict[str, Any]:
    p = Path(path).resolve()
    backend().open_document(str(p))
    _current["vsdx"] = str(p)
    return edit.inspect(backend())


@mcp.tool()
async def render_diagram(
    spec: DiagramSpec,
    name: str | None = None,
    formats: list[Format] = ["png"],
    preview: bool = True,
) -> list[Any]:
    """Draw a whole diagram from a spec in one call, auto-laid-out, saved as .vsdx plus exports.

    Returns a summary (overlaps, warnings, file paths) and a PNG preview to review.
    `name` sets the file name (defaults to the title).
    """
    result = await com_thread.call(_render, spec, name, list(formats))
    return _reply(result, preview)


@mcp.tool()
async def patch_diagram(
    ops: list[PatchOp], formats: list[Format] | None = None, preview: bool = True
) -> list[Any]:
    """Apply small edits (add/update/remove/move nodes and edges, relayout) to the open diagram,
    then re-save and re-export. Use after reviewing a preview."""
    result = await com_thread.call(_patch, ops, formats)
    return _reply(result, preview)


@mcp.tool()
async def inspect_diagram() -> dict[str, Any]:
    """List shapes (id, text, position, size), connectors and overlapping pairs on the open page."""
    return await com_thread.call(lambda: edit.inspect(backend()))


@mcp.tool()
async def open_diagram(path: str) -> dict[str, Any]:
    """Open an existing .vsdx so it can be inspected, patched and exported."""
    return await com_thread.call(_open, path)


@mcp.tool()
async def export_diagram(format: Format, path: str | None = None) -> str:
    """Export the open page to png/svg/pdf/jpg. Defaults to next to the .vsdx. Returns the path."""
    if not path:
        if not _current["vsdx"]:
            raise ValueError("no diagram open")
        path = str(Path(_current["vsdx"]).with_suffix(f".{format}"))
    return await com_thread.call(lambda: backend().export(path))


@mcp.tool()
def list_kinds() -> dict[str, str]:
    """Semantic node kinds usable in a spec, with what each is for."""
    return {k.name: k.description for k in catalog.kinds().values()}


@mcp.tool()
async def list_stencils() -> list[str]:
    """Built-in Visio stencil files available on this machine."""
    return await com_thread.call(lambda: backend().list_stencils())


@mcp.tool()
async def list_masters(stencil: str) -> list[str]:
    """Master shape names inside a stencil (for diagnosing kinds that fell back)."""
    return await com_thread.call(lambda: backend().list_masters(stencil))


@mcp.tool()
def get_authoring_guide() -> str:
    """How to write a good DiagramSpec and run the review loop. Read before the first render."""
    return prompts.GUIDE


@mcp.prompt()
def diagram(subject: str, source: Literal["prompt", "repo"] = "prompt") -> str:
    """Draw a Visio diagram of a subject, from a description or by exploring a repo."""
    return prompts.diagram_prompt(subject, source)


def main() -> None:
    mcp.run()
