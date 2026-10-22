"""Picture (Foreign) shapes showing embedded PNG icons."""

from __future__ import annotations

from pathlib import Path

from visio_mcp.layout import Rect
from visio_mcp.output.vsdx.cells import OBJ_IGNORE, cell, length
from visio_mcp.output.vsdx.geometry import Section, geometry_xml, rect
from visio_mcp.output.vsdx.page import STYLE_TEXT, Page, Shape
from visio_mcp.output.vsdx.shapes import xform


def png_size(path: Path) -> tuple[int, int]:
    """Pixel size from a PNG header ((0, 0) when unreadable)."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except OSError:
        pass
    return 0, 0


def picture(page: Page, name: str, r: Rect, png: Path) -> Shape:
    """A Foreign (picture) shape showing png, fitted into r keeping its aspect ratio."""
    rid = page.media_rel(png)
    iw, ih = png_size(png)
    k = min(r.w / iw, r.h / ih) if iw and ih else 1.0
    w, h = (iw * k, ih * k) if iw and ih else (r.w, r.h)
    s = Shape(page.new_id(), name, style=STYLE_TEXT, type="Foreign")
    s.cells += xform(r.x, r.y, w, h)
    # transparent PNGs: no fill or line behind the picture (renderers fall back to the style's)
    s.sections.append(geometry_xml([Section(rect().rows, no_fill=True, no_line=True)], w, h))
    s.cells += [cell("LinePattern", 0), cell("FillPattern", 0), cell("ShdwPattern", 0),
                cell("ObjType", OBJ_IGNORE),
                length("ImgOffsetX", 0.0, "ImgWidth*0"), length("ImgOffsetY", 0.0, "ImgHeight*0"),
                length("ImgWidth", w, "Width*1"), length("ImgHeight", h, "Height*1"),
                cell("LockAspect", 1)]
    s.foreign = f'<ForeignData ForeignType="Bitmap" CompressionType="PNG"><Rel r:id="{rid}"/></ForeignData>'
    return s
