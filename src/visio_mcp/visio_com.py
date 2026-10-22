"""VisioBackend implemented with Visio desktop over COM."""

from __future__ import annotations

import functools
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import pywintypes
import win32com.client

from visio_mcp.backend import ArrowMode, LinePattern, ShapeInfo

# Visio constants, verified on Visio 16 (names from the Visio type library).
OPEN_RO_HIDDEN = 2 + 64  # visOpenRO + visOpenHidden
ALERT_NO = 7  # AlertResponse: answer "No" to any prompt
SEL_SELECT = 2  # visSelect
FIXED_FORMAT_PDF = 1  # visFixedFormatPDF
PRINT_FROM_TO = 2  # visPrintFromTo
ARROW_FILLED = 13  # standard filled arrowhead
LINE_PATTERNS = {"solid": 1, "dashed": 2, "dotted": 3}  # visLPatSolid / ...

# layout preset -> (PlaceStyle, RouteStyle)
#   PlaceStyle: 1 top-to-bottom, 2 left-to-right, 3 radial, 6 circular, 7 compact tree
#   RouteStyle: 2 straight, 3 tree NS, 4 tree WE, 6 clean right-angle (found by trying; 1 gives a merged bus)
LAYOUTS = {
    "flowchart-tb": (1, 6),
    "flowchart-lr": (2, 6),
    "tree-tb": (1, 3),
    "tree-lr": (2, 4),
    "radial": (3, 2),
    "circular": (6, 2),
    "compact": (7, 6),
}
SPACING = 0.9  # inches between shapes, so boxes never touch after layout


def _message(exc: Exception) -> str:
    """Readable text for a COM error (no raw tuples)."""
    if isinstance(exc, pywintypes.com_error):
        info = exc.excepinfo
        if info and len(info) > 2 and info[2]:
            return str(info[2]).strip()
        return str(exc.strerror or exc.args[0]).strip()
    return str(exc)


def _guard(fn: Callable) -> Callable:
    """Turn pywintypes.com_error into RuntimeError with a readable message."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except pywintypes.com_error as e:
            raise RuntimeError(f"Visio {fn.__name__} failed: {_message(e)}") from None

    return wrapper


def _start_app(visible: bool) -> Any:
    """Start Visio, retrying while it is busy ('Call was rejected by callee')."""
    prog_id = "Visio.Application" if visible else "Visio.InvisibleApp"
    for attempt in range(6):
        try:
            return win32com.client.DispatchEx(prog_id)
        except pywintypes.com_error as e:
            if attempt == 5:
                raise RuntimeError(f"could not start Visio: {_message(e)}") from None
            time.sleep(1.0)
    raise AssertionError("unreachable")


class VisioCom:
    """Implements visio_mcp.backend.VisioBackend. Create and use only on the COM thread."""

    @_guard
    def __init__(self, visible: bool = False) -> None:
        self._app = _start_app(visible)
        self._app.AlertResponse = ALERT_NO
        # Some masters (org chart) run add-ons on drop, which hang a headless Visio.
        self._app.EventsEnabled = False
        self._doc: Any = None
        self._stencils: dict[str, Any] = {}
        self._app.Settings.SetRasterExportResolution(3, 150.0, 150.0, 0)  # custom, 150 dpi

    # lifecycle
    def close(self) -> None:
        """Quit Visio without saving anything."""
        try:
            self._close_doc()
            self._app.EventsEnabled = True
            self._app.Quit()
        except pywintypes.com_error:
            pass
        self._doc, self._stencils = None, {}

    quit = close

    # documents
    @_guard
    def new_document(self, title: str) -> None:
        self._close_doc()
        self._doc = self._app.Documents.Add("")
        self._doc.Title = title

    @_guard
    def open_document(self, path: str) -> None:
        self._close_doc()
        self._doc = self._app.Documents.Open(str(Path(path).resolve()))

    @_guard
    def save(self, path: str) -> str:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        doc = self._need_doc()
        if doc.FullName and Path(doc.FullName).resolve() == target:
            doc.Save()
            return str(target)
        target.unlink(missing_ok=True)  # SaveAs will not overwrite when alerts answer "No"
        doc.SaveAs(str(target))
        return str(target)

    @_guard
    def export(self, path: str) -> str:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        ext = target.suffix.lower()
        if ext in (".png", ".svg", ".jpg", ".jpeg"):
            self._page().Export(str(target))
        elif ext == ".pdf":
            index = self._page().Index
            self._need_doc().ExportAsFixedFormat(
                FIXED_FORMAT_PDF, str(target), 0, PRINT_FROM_TO, index, index
            )
        else:
            raise ValueError(f"unsupported export format {ext!r} (use png, svg, jpg or pdf)")
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError(f"Visio export produced no file at {target}")
        return str(target)

    # stencils
    @_guard
    def list_stencils(self) -> list[str]:
        base = Path(self._app.Path) / "Visio Content"
        folder = base / str(self._app.Language)
        if not folder.is_dir():
            folder = base / "1033"
        if not folder.is_dir():
            return []
        return sorted(p.name.upper() for p in folder.glob("*.vssx") if p.stem.upper().endswith("_U"))

    @_guard
    def list_masters(self, stencil: str) -> list[str]:
        doc = self._stencil(stencil)
        return [m.NameU for m in doc.Masters] if doc is not None else []

    def has_master(self, stencil: str, master: str) -> bool:
        try:
            return self._master(stencil, master) is not None
        except Exception:
            return False

    # shapes
    @_guard
    def drop_shape(
        self,
        name: str,
        stencil: str,
        master: str,
        x: float,
        y: float,
        width: float | None = None,
        height: float | None = None,
    ) -> None:
        m = self._master(stencil, master)
        if m is None:
            raise KeyError(f"no master {master!r} in {stencil!r}")
        if self._exists(name):
            raise KeyError(f"duplicate shape name {name!r}")
        shape = self._page().Drop(m, x, y)
        self._name(shape, name)
        if width is not None:
            shape.CellsU("Width").ResultIU = width
        if height is not None:
            shape.CellsU("Height").ResultIU = height

    @_guard
    def set_text(self, name: str, text: str) -> None:
        self._find(name).Text = text

    @_guard
    def set_fill(self, name: str, color: str) -> None:
        m = re.fullmatch(r"#([0-9a-fA-F]{6})", color)
        if not m:
            raise ValueError(f"color must be '#RRGGBB', got {color!r}")
        r, g, b = (int(m.group(1)[i : i + 2], 16) for i in (0, 2, 4))
        shape = self._find(name)
        shape.CellsU("FillForegnd").FormulaU = f"RGB({r},{g},{b})"
        shape.CellsU("FillPattern").FormulaU = "1"

    @_guard
    def connect(
        self,
        name: str,
        source: str,
        target: str,
        label: str = "",
        pattern: LinePattern = "solid",
        arrow: ArrowMode = "end",
    ) -> None:
        src, dst = self._find(source), self._find(target)
        if self._exists(name):
            raise KeyError(f"duplicate shape name {name!r}")
        conn = self._page().Drop(self._master("BASFLO_U.VSSX", "Dynamic connector"), 0, 0)
        conn.CellsU("BeginX").GlueTo(src.CellsU("PinX"))
        conn.CellsU("EndX").GlueTo(dst.CellsU("PinX"))
        self._name(conn, name)
        conn.Text = label
        conn.CellsU("LinePattern").FormulaU = str(LINE_PATTERNS[pattern])
        conn.CellsU("BeginArrow").FormulaU = str(ARROW_FILLED if arrow == "both" else 0)
        conn.CellsU("EndArrow").FormulaU = str(0 if arrow == "none" else ARROW_FILLED)

    @_guard
    def add_container(self, name: str, label: str, members: list[str]) -> None:
        if self._exists(name):
            raise KeyError(f"duplicate shape name {name!r}")
        page = self._page()
        selection = page.CreateSelection(0, 0)  # empty selection
        for m in members:
            selection.Select(self._find(m), SEL_SELECT)
        container = page.DropContainer(self._master("SDCONT_U.VSSX", "Plain"), selection)
        self._name(container, name)
        container.Text = label

    @_guard
    def move(self, name: str, x: float, y: float) -> None:
        shape = self._find(name)
        shape.CellsU("PinX").ResultIU = x
        shape.CellsU("PinY").ResultIU = y

    @_guard
    def delete(self, name: str) -> None:
        shape = self._find(name)
        doomed = [shape]
        for other in self._page().Shapes:
            if other.OneD and any(c.ToSheet.NameU == name for c in other.Connects):
                doomed.append(other)
        for s in doomed:
            s.Delete()

    @_guard
    def shapes(self) -> list[ShapeInfo]:
        out = []
        for s in self._page().Shapes:
            out.append(
                ShapeInfo(
                    name=s.NameU,
                    text=s.Text,
                    master=s.Master.NameU if s.Master is not None else None,
                    x=s.CellsU("PinX").ResultIU,
                    y=s.CellsU("PinY").ResultIU,
                    width=s.CellsU("Width").ResultIU,
                    height=s.CellsU("Height").ResultIU,
                    is_connector=bool(s.OneD),
                    is_container=self._is_container(s),
                )
            )
        return out

    # page
    @_guard
    def layout(self, preset: str) -> None:
        page = self._page()
        if preset != "none":
            if preset not in LAYOUTS:
                raise ValueError(f"unknown layout preset {preset!r}")
            place, route = LAYOUTS[preset]
            sheet = page.PageSheet
            for cell, value in (
                ("PlaceStyle", place),
                ("RouteStyle", route),
                ("AvenueSizeX", SPACING),
                ("AvenueSizeY", SPACING),
                ("BlockSizeX", SPACING / 2),
                ("BlockSizeY", SPACING / 2),
            ):
                sheet.CellsU(cell).ResultIU = value
            page.Layout()
        page.ResizeToFitContents()
        sheet = page.PageSheet  # add a margin around the drawing
        for cell in ("PageWidth", "PageHeight"):
            sheet.CellsU(cell).ResultIU += 1.0
        page.CreateSelection(1, 0).Move(0.5, 0.5)  # visSelTypeAll

    # helpers
    def _need_doc(self) -> Any:
        if self._doc is None:
            raise RuntimeError("no document open: call new_document or open_document first")
        return self._doc

    def _page(self) -> Any:
        return self._need_doc().Pages(1)

    def _close_doc(self) -> None:
        if self._doc is not None:
            self._doc.Saved = True  # discard changes, no prompt
            self._doc.Close()
            self._doc = None

    def _stencil(self, name: str) -> Any | None:
        key = name.upper()
        if key not in self._stencils:
            try:
                self._stencils[key] = self._app.Documents.OpenEx(name, OPEN_RO_HIDDEN)
            except pywintypes.com_error:
                return None
        return self._stencils[key]

    def _master(self, stencil: str, master: str) -> Any | None:
        doc = self._stencil(stencil)
        if doc is None:
            return None
        try:
            return doc.Masters.ItemU(master)
        except pywintypes.com_error:
            return None

    def _find(self, name: str) -> Any:
        try:
            return self._page().Shapes.ItemU(name)
        except pywintypes.com_error:
            raise KeyError(f"no shape named {name!r}") from None

    def _exists(self, name: str) -> bool:
        try:
            self._page().Shapes.ItemU(name)
            return True
        except pywintypes.com_error:
            return False

    @staticmethod
    def _name(shape: Any, name: str) -> None:
        shape.Name = name
        shape.NameU = name

    @staticmethod
    def _is_container(shape: Any) -> bool:
        cell = "User.msvStructureType"
        return bool(shape.CellExistsU(cell, 0)) and "Container" in shape.CellsU(cell).FormulaU
