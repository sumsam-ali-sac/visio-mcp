"""render_svg: the whole plan as one standalone SVG document."""

from __future__ import annotations

from visio_mcp.output.svg.canvas import Canvas
from visio_mcp.output.svg.decorations import group, legend, text_block
from visio_mcp.output.svg.edges import edge
from visio_mcp.output.svg.markup import esc, num
from visio_mcp.output.svg.nodes import node
from visio_mcp.plan import DiagramPlan

_SHADOW = ('<filter id="shadow" x="-10%" y="-10%" width="125%" height="135%" color-interpolation-filters="sRGB">'
           '<feDropShadow dx="0" dy="1" stdDeviation="{blur}" flood-color="{color}" flood-opacity="{opacity}"/></filter>')


def render_svg(plan: DiagramPlan) -> str:
    """Draw the plan as a standalone SVG document (groups, edges, nodes, title, legend)."""
    c = Canvas(plan)
    th = plan.theme
    body = [f'<rect class="page" width="{num(c.W)}" height="{num(c.H)}" fill="{esc(th.background)}"/>']
    if plan.groups:
        body += ['<g id="groups">', *(group(c, g, i) for i, g in enumerate(plan.groups)), "</g>"]
    if plan.edges:
        body += ['<g id="edges" fill="none">', *(edge(c, e, i) for i, e in enumerate(plan.edges)), "</g>"]
    if plan.nodes:
        body += ['<g id="nodes">', *(node(c, n, i) for i, n in enumerate(plan.nodes)), "</g>"]
    if plan.title:
        body.append(f'<g id="title" data-id="title">{text_block(c, plan.title)}</g>')
    if plan.legend:
        body.append(legend(c))

    title = plan.spec.title or "Diagram"
    desc = plan.spec.subtitle or f"{len(plan.nodes)} nodes, {len(plan.edges)} connections"
    shadow = (_SHADOW.format(blur="2", color="#000000", opacity="0.35") if th.dark
              else _SHADOW.format(blur="1.4", color="#0F172A", opacity="0.10"))
    defs = "<defs>" + shadow + "".join(c.markers.values()) + "</defs>"
    w, h = num(c.W), num(c.H)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-labelledby="svg-title svg-desc" text-rendering="geometricPrecision" '
        f'data-theme="{esc(th.name)}">'
        f'<title id="svg-title">{esc(title)}</title><desc id="svg-desc">{esc(desc)}</desc>'
        + defs + "".join(body) + "</svg>\n"
    )
