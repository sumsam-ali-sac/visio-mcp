"""MCP server: thin tool wrappers. All drawing runs on the COM thread."""

from __future__ import annotations

import functools
from typing import Any, Callable, Literal

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from visio_mcp import catalog, lint, rules, style
from visio_mcp.output.visio import com_thread
from visio_mcp.mcp import guide, state
from visio_mcp.mcp.state import drawer
from visio_mcp.output.drawer import DrawOutput, default_out_dir, slug
from visio_mcp.spec import DiagramSpec, PatchOp

Format = Literal["png", "svg", "pdf", "jpg", "html"]

mcp = MCPServer(
    name="visio",
    instructions=(
        "Draws professional, native Microsoft Visio diagrams, live in the user's Visio app. "
        "Read get_authoring_guide and get_diagram_rules for the diagram type first. Describe the "
        "diagram as one DiagramSpec (nodes, edges, groups, type, theme) and call render_diagram once; "
        "then review the preview, warnings and suggestions and fix them with patch_diagram."
    ),
)


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


def _reply(out: DrawOutput, preview: bool) -> list[Any]:
    content: list[Any] = [out.result.model_dump_json(indent=1)]
    if preview and out.png and out.png.exists():
        content.append(Image(path=str(out.png)))
    return content


def _preview_formats(formats: list[str], preview: bool) -> list[str]:
    return list(dict.fromkeys(formats + (["png"] if preview else [])))


@mcp.tool(structured_output=False)
@_readable
async def render_diagram(
    spec: DiagramSpec,
    name: str | None = None,
    formats: list[Format] = ["png"],
    preview: bool = True,
) -> list[Any]:
    """Draw a whole diagram from a spec in one call: laid out, themed, saved as .vsdx plus exports.

    In Visio it is drawn live in the user's Visio window. Returns a summary (overlaps, warnings,
    rule suggestions, file paths) and a PNG preview to review. `name` sets the file name.
    """
    vsdx = default_out_dir() / f"{slug(name or spec.title)}.vsdx"
    out = await com_thread.call(lambda: drawer().render(spec, vsdx, _preview_formats(list(formats), preview)))
    return _reply(out, preview)


@mcp.tool(structured_output=False)
@_readable
async def patch_diagram(
    ops: list[PatchOp], formats: list[Format] | None = None, preview: bool = True
) -> list[Any]:
    """Edit the open diagram: add/update/remove nodes, edges and groups, change title, theme or
    layout. Diagrams drawn from a spec are re-laid-out and keep consistent styling. Re-saves."""
    fmts = None if formats is None else _preview_formats(list(formats), preview)
    out = await com_thread.call(lambda: drawer().patch(ops, fmts))
    return _reply(out, preview)


@mcp.tool()
@_readable
async def inspect_diagram() -> dict[str, Any]:
    """List shapes (id, text, position, size), connectors and overlapping pairs on the open page."""
    return await com_thread.call(lambda: drawer().inspect())


@mcp.tool()
@_readable
async def open_diagram(path: str) -> dict[str, Any]:
    """Open an existing .vsdx in Visio so it can be inspected, patched and exported.
    Patching saves over that file."""
    return await com_thread.call(lambda: drawer().open(path))


@mcp.tool()
@_readable
async def export_diagram(format: Format, path: str | None = None) -> str:
    """Export the open page to png/svg/pdf/jpg/html. Defaults to next to the .vsdx. Returns the path."""
    return str(await com_thread.call(lambda: drawer().export(format, path)))


@mcp.tool()
def list_kinds(provider: str | None = None) -> str:
    """Semantic node kinds usable in a spec, grouped by category. Pass provider ('azure', 'aws',
    'gcp') to include that cloud's service kinds."""
    return catalog.describe_kinds(provider)


@mcp.tool()
def list_themes() -> dict[str, str]:
    """Visual themes for spec.theme, with when to use each."""
    return {t.name: t.description for t in style.THEMES.values()}


@mcp.tool()
def get_diagram_rules(diagram_type: str, provider: str | None = None) -> str:
    """Ground rules for one diagram type (flowchart, architecture, cloud, c4-context, c4-container,
    deployment, network, dataflow, pipeline, erd, org, swimlane, state, mindmap): layout, shapes,
    groups, edge conventions, checklist and an example spec. provider adds cloud specifics."""
    try:
        return rules.get_rules(diagram_type, provider)
    except ValueError as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def lint_diagram(spec: DiagramSpec) -> dict[str, Any]:
    """Check a spec against the diagramming rules without drawing it. Returns the normalized
    type/layout/theme and findings to fix."""
    normalized, notes = lint.normalize(spec)
    return {
        "type": normalized.type,
        "layout": normalized.layout,
        "theme": normalized.theme,
        "notes": notes,
        "findings": lint.lint(normalized),
    }


@mcp.tool()
@_readable
async def list_stencils() -> list[str]:
    """Built-in Visio stencil files available on this machine."""
    return await com_thread.call(lambda: drawer().backend().list_stencils())


@mcp.tool()
@_readable
async def list_masters(stencil: str) -> list[str]:
    """Master shape names inside a stencil (for diagnosing kinds that fell back)."""
    return await com_thread.call(lambda: drawer().backend().list_masters(stencil))


@mcp.tool()
@_readable
async def install_icons(provider: str = "all") -> dict[str, Any]:
    """Download the official cloud architecture icons ('azure', 'aws', 'gcp' or 'all') once, so
    cloud kinds (azure-*, aws-*, gcp-*) draw with the real service icons. Returns what was
    installed and the status of every pack. Re-render afterwards to use them."""
    import asyncio

    from visio_mcp import icons

    try:
        installed = await asyncio.to_thread(icons.install, None if provider == "all" else provider)
    except icons.IconInstallError as e:
        raise ToolError(f"{e}. {e.hint}") from e
    return {"installed": installed, "status": icons.status()}


@mcp.tool()
def get_authoring_guide() -> str:
    """How to write a great DiagramSpec and run the review loop. Read before the first render."""
    return guide.GUIDE


@mcp.resource("visio://rules/{diagram_type}")
def rules_resource(diagram_type: str) -> str:
    """Ground rules for a diagram type, as markdown."""
    return rules.get_rules(diagram_type)


@mcp.prompt()
def diagram(subject: str, source: Literal["prompt", "repo"] = "prompt", diagram_type: str = "auto") -> str:
    """Draw a Visio diagram of a subject, from a description or by exploring a repo."""
    return guide.diagram_prompt(subject, source, diagram_type)


def main() -> None:
    try:
        mcp.run()
    finally:
        com_thread._executor.submit(state.close).result(timeout=30)


if __name__ == "__main__":
    main()
