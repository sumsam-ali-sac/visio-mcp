"""DiagramPlan -> SVG preview (and an interactive HTML viewer, and best-effort PNG).

Pure standard library. The plan is in inches with a bottom-left origin; the SVG is in
CSS pixels (1 inch = 96 px) with y flipped, so a shape with a larger plan y is drawn higher.

    render_svg(plan)        standalone SVG string                     (render.py)
    write_html(plan, path)  single-file viewer: inline SVG, pan/zoom  (html.py)
    svg_to_png(svg, png)    rasterize; None when no renderer works    (raster.py)
"""

from visio_mcp.output.svg.html import write_html
from visio_mcp.output.svg.raster import find_chromium, svg_to_png
from visio_mcp.output.svg.render import render_svg


__all__ = ["find_chromium", "render_svg", "svg_to_png", "write_html"]
