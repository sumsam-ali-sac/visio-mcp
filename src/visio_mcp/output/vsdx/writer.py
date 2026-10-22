"""write_vsdx: lay the plan's shapes out on a page in z-order and zip the package."""

from __future__ import annotations

import zipfile
from pathlib import Path

from visio_mcp.output.vsdx import package
from visio_mcp.output.vsdx.connectors import draw_edge
from visio_mcp.output.vsdx.containers import draw_group
from visio_mcp.output.vsdx.decorations import draw_background, draw_legend, draw_title
from visio_mcp.output.vsdx.nodes import draw_node
from visio_mcp.output.vsdx.page import Page
from visio_mcp.plan import DiagramPlan


def build_page(plan: DiagramPlan) -> Page:
    """All shapes in z-order: background, group frames (outer first), legend, connectors,
    nodes, title. Nodes are drawn before connectors are written so glue can name their ids;
    connectors are then moved below the nodes."""
    page = Page()
    wanted = [n.image for n in plan.nodes if n.image is not None and n.geometry == "icon"]
    if wanted:
        from visio_mcp.output.vsdx import raster

        page.pngs = raster.pngs_for(wanted)  # SVG icons rasterized once; None -> glyph tile
    draw_background(page, plan)
    for g in sorted(plan.groups, key=lambda g: g.depth):
        draw_group(page, g)
    if plan.legend:
        draw_legend(page, plan)
    first_node = len(page.shapes)
    for n in plan.nodes:
        draw_node(page, plan, n)
    nodes = page.shapes[first_node:]
    page.shapes = page.shapes[:first_node]
    for e in plan.edges:
        draw_edge(page, plan, e)
    page.shapes += nodes
    if plan.title:
        draw_title(page, plan.title)
    return page


def write_vsdx(plan: DiagramPlan, path: str | Path) -> Path:
    """Write plan as a native Visio drawing (written to a temp file, then swapped in). Returns the absolute path."""
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    page = build_page(plan)
    for st in (plan.theme.title, plan.theme.subtitle):
        page.font(st.font)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in package.parts(plan, page).items():
            z.writestr(name, data.encode("utf-8"))
        for png, (_, part) in page.media.items():
            z.write(png, f"visio/media/{part}", compress_type=zipfile.ZIP_STORED)
    tmp.replace(out)
    return out
