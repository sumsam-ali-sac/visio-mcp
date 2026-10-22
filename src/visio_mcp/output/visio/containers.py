"""Containers: wrap member shapes in a labeled frame and pin it to exact bounds."""

from __future__ import annotations

from typing import Any

import pywintypes

from visio_mcp.output.visio import formatting, text
from visio_mcp.output.visio.cells import inch, set_cell
from visio_mcp.output.visio.names import find, is_container, set_name
from visio_mcp.output.visio.text import FontFormula
from visio_mcp.style import GroupStyle

STENCIL, MASTER = "SDCONT_U.VSSX", "Plain"
SEL_SELECT = 2  # visSelect
CONTAINER_NO_RESIZE = 0  # visContainerAutoResizeNone (1 = expand, 2 = expand and contract)

Bounds = tuple[float, float, float, float]  # center x, center y, width, height


def drop(page: Any, name: str, master: Any, label: str, members: list[str], bounds: Bounds | None) -> Any:
    """Around the members when there are any, else a bare container at the bounds' center."""
    if members:
        selection = page.CreateSelection(0, 0)  # empty selection
        for m in members:
            selection.Select(find(page, m), SEL_SELECT)
        container = page.DropContainer(master, selection)
    else:
        x, y = (bounds[0], bounds[1]) if bounds else (1.0, 1.0)
        container = page.Drop(master, x, y)
    set_name(container, name)
    container.Text = label
    return container


def style(container: Any, st: GroupStyle, font: FontFormula) -> None:
    """Padding, frame and a left-aligned header, also on the master's heading sub-shapes."""
    set_cell(container, "User.msvSDContainerMargin", inch(st.padding))
    formatting.frame(container, st.shape)
    formatting.shadow(container, False)
    text.text_style(container, st.header, font)
    text.paragraphs(container, "left")
    for sub in _subshapes(container):
        if sub.Text:
            text.text_style(sub, st.header, font)
            text.paragraphs(sub, "left")


def pin(page: Any, container: Any, bounds: Bounds, members: list[str]) -> None:
    """Fix the frame to bounds (no auto-resize); moving it may drag members, so put them back."""
    _no_auto_resize(container)
    cx, cy, w, h = bounds
    inside = _inside(page, members)
    before = {n: (s.CellsU("PinX").ResultIU, s.CellsU("PinY").ResultIU) for n, s in inside}
    container.CellsU("Width").ResultIU = w
    container.CellsU("Height").ResultIU = h
    container.CellsU("PinX").ResultIU = cx - w / 2 + container.CellsU("LocPinX").ResultIU
    container.CellsU("PinY").ResultIU = cy - h / 2 + container.CellsU("LocPinY").ResultIU
    # outer containers first: restoring one also brings back everything inside it
    order = sorted(inside, key=lambda p: (not is_container(p[1]),
                                          -p[1].CellsU("Width").ResultIU * p[1].CellsU("Height").ResultIU))
    for n, s in order:
        x, y = before[n]
        if abs(s.CellsU("PinX").ResultIU - x) > 1e-6 or abs(s.CellsU("PinY").ResultIU - y) > 1e-6:
            s.CellsU("PinX").ResultIU = x
            s.CellsU("PinY").ResultIU = y


def _no_auto_resize(container: Any) -> None:
    try:
        container.ContainerProperties.ResizeAsNeeded = CONTAINER_NO_RESIZE
    except (pywintypes.com_error, AttributeError):
        set_cell(container, "User.msvSDContainerResize", str(CONTAINER_NO_RESIZE))


def _inside(page: Any, members: list[str]) -> list[tuple[str, Any]]:
    """Members and, for member containers, everything they hold (by name)."""
    out: dict[str, Any] = {}
    todo = list(members)
    while todo:
        n = todo.pop()
        if n in out:
            continue
        s = find(page, n)
        if s.OneD:  # glued connectors follow their shapes by themselves
            continue
        out[n] = s
        if is_container(s):
            try:
                ids = s.ContainerProperties.GetMemberShapes(0)  # 0: all members, as shape IDs
                todo += [page.Shapes.ItemFromID(i).NameU for i in ids or ()]
            except (pywintypes.com_error, AttributeError, TypeError):
                pass
    return list(out.items())


def _subshapes(shape: Any) -> list[Any]:
    try:
        return list(shape.Shapes)
    except (pywintypes.com_error, TypeError):
        return []
