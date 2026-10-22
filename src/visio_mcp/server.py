"""MCP server: thin tool wrappers. All Visio work runs on the COM thread."""

from __future__ import annotations

import functools
import os
import re
from pathlib import Path
from typing import Any, Callable, Literal

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

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
# Touched only on the COM thread.
_current: dict[str, Any] = {"vsdx": None, "formats": ["png"]}


def out_dir() -> Path:
    default = Path.home() / "Documents" / "visio-mcp"
    d = Path(os.environ.get("VISIO_MCP_OUT") or default)
    d.mkdir(parents=True, exist_ok=True)
    return d


def backend() -> VisioBackend:
    """Lazily start Visio. Must be called on the COM thread."""
    global _backend
    if _backend is None:
        from visio_mcp.visio_com import VisioCom

        _backend = VisioCom(visible=os.environ.get("VISIO_MCP_VISIBLE") == "1")
    return _backend


def _readable(fn: Callable) -> Callable:
    """Send expected failures to the client as ToolError; MCP hides other exceptions' text."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except (ValueError, KeyError, RuntimeError, OSError) as e:
            msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
            raise ToolError(msg) from e

    return wrapper


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "diagram"


def _save(vsdx: Path) -> tuple[Path, str | None]:
    """Save, or save under a free name when the file is open elsewhere (e.g. in Visio)."""
    try:
        return Path(backend().save(str(vsdx))), None
    except PermissionError:
        n = 2
        while (alt := vsdx.with_name(f"{vsdx.stem}-{n}{vsdx.suffix}")).exists():
            n += 1
        backend().save(str(alt))
        return alt, f"{vsdx.name} is open in another program; saved as {alt.name}"


def _write(result: RenderResult, formats: list[str]) -> RenderResult:
    vsdx, warning = _save(Path(_current["vsdx"]))
    _current["vsdx"] = str(vsdx)
    files = [str(vsdx)] + [backend().export(str(vsdx.with_suffix(f".{f}"))) for f in formats]
    warnings = result.warnings + ([warning] if warning else [])
    return result.model_copy(update={"files": files, "warnings": warnings})


def _reply(result: RenderResult, preview: bool) -> list[Any]:
    out: list[Any] = [result.model_dump_json(indent=1)]
    png = next((f for f in result.files if f.lower().endswith(".png")), None)
    if preview and png:
        out.append(Image(path=png))
    return out


def _render(spec: DiagramSpec, name: str | None, formats: list[str]) -> RenderResult:
    vsdx = out_dir() / f"{_slug(name or spec.title)}.vsdx"
    _current["vsdx"] = None  # a failed render leaves nothing to patch over
    result = render.render_spec(backend(), spec)
    _current.update(vsdx=str(vsdx), formats=formats)
    return _write(result, formats)


def _patch(ops: list[PatchOp], formats: list[str] | None) -> RenderResult:
    if not _current["vsdx"]:
        raise ValueError("no diagram open: call render_diagram or open_diagram first")
    result = edit.apply_ops(backend(), ops)
    return _write(result, formats if formats is not None else _current["formats"])


def _open(path: str) -> dict[str, Any]:
    p = Path(path).resolve()
    if p.suffix.lower() not in (".vsdx", ".vsd") or not p.is_file():
        raise ValueError(f"not an existing .vsdx/.vsd file: {p}")
    _current["vsdx"] = None
    backend().open_document(str(p))
    _current["vsdx"] = str(p)
    return edit.inspect(backend())


def _export(format: str, path: str | None) -> str:
    if path:
        target = Path(path).with_suffix(f".{format}")
    elif _current["vsdx"]:
        target = Path(_current["vsdx"]).with_suffix(f".{format}")
    else:
        raise ValueError("no diagram open")
    return backend().export(str(target))


@mcp.tool(structured_output=False)
@_readable
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


@mcp.tool(structured_output=False)
@_readable
async def patch_diagram(
    ops: list[PatchOp], formats: list[Format] | None = None, preview: bool = True
) -> list[Any]:
    """Apply small edits (add/update/remove/move nodes and edges, relayout) to the open diagram,
    then re-save and re-export. Use after reviewing a preview."""
    result = await com_thread.call(_patch, ops, formats)
    return _reply(result, preview)


@mcp.tool()
@_readable
async def inspect_diagram() -> dict[str, Any]:
    """List shapes (id, text, position, size), connectors and overlapping pairs on the open page."""
    return await com_thread.call(lambda: edit.inspect(backend()))


@mcp.tool()
@_readable
async def open_diagram(path: str) -> dict[str, Any]:
    """Open an existing .vsdx so it can be inspected, patched and exported.
    Patching saves over that file."""
    return await com_thread.call(_open, path)


@mcp.tool()
@_readable
async def export_diagram(format: Format, path: str | None = None) -> str:
    """Export the open page to png/svg/pdf/jpg. Defaults to next to the .vsdx. Returns the path."""
    return await com_thread.call(_export, format, path)


@mcp.tool()
def list_kinds() -> dict[str, str]:
    """Semantic node kinds usable in a spec, with what each is for."""
    return {k.name: k.description for k in catalog.kinds().values()}


@mcp.tool()
@_readable
async def list_stencils() -> list[str]:
    """Built-in Visio stencil files available on this machine."""
    return await com_thread.call(lambda: backend().list_stencils())


@mcp.tool()
@_readable
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


def _shutdown() -> None:
    close = getattr(_backend, "close", None)
    if close:
        close()


def main() -> None:
    try:
        mcp.run()
    finally:
        # Quit the headless Visio so it doesn't linger holding files open.
        com_thread._executor.submit(_shutdown).result(timeout=30)
