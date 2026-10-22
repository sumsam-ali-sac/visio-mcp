"""Group frames written as real Visio containers with a header label."""

from __future__ import annotations

from visio_mcp.output.visio.backend import TextRun
from visio_mcp.output.vsdx import shapes
from visio_mcp.output.vsdx.cells import OBJ_IGNORE, V_TOP, num
from visio_mcp.output.vsdx.page import Page
from visio_mcp.plan import PlannedGroup


def draw_group(page: Page, g: PlannedGroup) -> None:
    st = g.style
    header = [TextRun(g.label, st.header)] if g.label else []
    pad_top = max(2.0, (st.header_height * 72 - st.header.size * 1.2) / 2)
    s = shapes.box(page, g.id, g.rect, st.shape, "rect", header, align="left", valign=V_TOP, obj=OBJ_IGNORE,
                   margins_pt=(9, 9, pad_top, 4))
    # a real Visio container (custom containers only need User.msvStructureType); members are
    # not pre-registered, Visio adds shapes to it as they are moved or dropped
    s.sections.insert(0, shapes.user_section({
        "msvStructureType": ("Container", "STR", '"Container"'),
        "msvSDContainerMargin": (num(min(st.padding, 0.25)), "IN", None),
        "msvSDContainerResize": ("0", None, None),
    }))
    page.add(s)
