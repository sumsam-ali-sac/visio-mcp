"""VisioBackend implemented with Visio desktop over COM.

Three ways to run:
- headless (visible=False): a hidden Visio.InvisibleApp of our own (CI, servers).
- visible (default): our own Visio window; each render opens a new drawing in front of the user.
- attach=True: draw into the Visio the user already has open (falls back to starting one).
  We never quit an app we did not start, and never close documents we did not create.

live_delay > 0 pauses after every shape so the user watches the diagram build.
"""

from __future__ import annotations

import functools
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import pythoncom
import pywintypes
import win32com.client

from visio_mcp.output.visio.backend import Align, ArrowMode, LinePattern, ShapeInfo, TextRun
from visio_mcp.style import EdgeStyle, GroupStyle, ShapeStyle, TextStyle

# Visio constants, verified on Visio 16 (names from the Visio type library).
OPEN_RO_HIDDEN = 2 + 64  # visOpenRO + visOpenHidden
ALERT_NO = 7  # AlertResponse: answer "No" to any prompt
SEL_SELECT = 2  # visSelect
SEL_TYPE_ALL = 1  # visSelTypeAll
FIXED_FORMAT_PDF = 1  # visFixedFormatPDF
PRINT_FROM_TO = 2  # visPrintFromTo
ARROW_FILLED = 13  # standard filled arrowhead
LINE_PATTERNS = {"solid": 1, "dashed": 2, "dotted": 3}  # visLPatSolid / ...

# Constants from the type library, not yet exercised on a real machine by this file's tests.
SECTION_CHARACTER = 3  # visSectionCharacter
SECTION_PARAGRAPH = 4  # visSectionParagraph
CHAR_SIZE = 7  # visCharacterSize (visCharacterFont=0, Color=1, Style=2)
PARA_HORZ_ALIGN = 6  # visHorzAlign
BIAS_LET_VISIO_CHOOSE = 0  # visBiasLetVisioChoose (Characters.CharPropsRow)
STYLE_BOLD, STYLE_ITALIC = 1, 2  # visBold, visItalic (Char.Style bits)
HORZ_ALIGN = {"left": 0, "center": 1, "right": 2}  # visHorzLeft / visHorzCenter / visHorzRight
VERT_TOP, VERT_MIDDLE = 0, 1  # visVertTop, visVertMiddle
ROUTE_RIGHT_ANGLE = 1  # visLORouteRightAngle (ShapeRouteStyle)
ROUTE_EXT_STRAIGHT = 1  # visLORouteExtStraight (ConLineRouteExt; 2 = curved)
JUMP_ARC = 1  # visLOJumpStyleArc (ConLineJumpStyle)
ARROW_SIZE_MEDIUM = 2  # visArrowSizeMedium
CONTAINER_NO_RESIZE = 0  # visContainerAutoResizeNone (1 = expand, 2 = expand and contract)
OBJ_TYPE_NONE = 4  # ObjType: neither placeable nor routable (layout and routing ignore it)
DRAWING_SIZE_CUSTOM = 3  # DrawingSizeType: custom page size
DRAWING_NO_AUTO_RESIZE = 2  # DrawingResizeType: do not grow the page as shapes move
WIN_DRAWING = 1  # visDrawing (Window.Type)
FIT_PAGE = 1  # visFitPage (Window.ViewFit)
DOC_DRAWING = 1  # visTypeDrawing (Document.Type)

BACKGROUND = "__background"
TEXT_MARGIN = "2 pt"
LABEL_BELOW_HEIGHT = 0.45  # inches, text block under an icon

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


def _running_app() -> Any | None:
    """The Visio the user already has open, or None."""
    try:
        return win32com.client.GetActiveObject("Visio.Application")
    except pywintypes.com_error:
        return None


# --- formula helpers -------------------------------------------------------------------------


def _rgb(color: str) -> str:
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", color)
    if not m:
        raise ValueError(f"color must be '#RRGGBB', got {color!r}")
    r, g, b = (int(m.group(1)[i : i + 2], 16) for i in (0, 2, 4))
    return f"RGB({r},{g},{b})"


def _pt(v: float) -> str:
    return f"{v:g} pt"


def _inch(v: float) -> str:
    return f"{v:g} in"


def _u16len(text: str) -> int:
    """Length as Visio counts characters (UTF-16 code units)."""
    return len(text.encode("utf-16-le")) // 2


def _set(shape: Any, cell: str, formula: str) -> bool:
    """Set a ShapeSheet cell by universal name; a missing or refusing cell is skipped, never fatal."""
    try:
        if not shape.CellExistsU(cell, 0):
            return False
        c = shape.CellsU(cell)
        try:
            c.FormulaForceU = formula  # also replaces GUARD()ed master formulas
        except pywintypes.com_error:
            c.FormulaU = formula
        return True
    except pywintypes.com_error:
        return False


def _set_src(shape: Any, section: int, row: int, column: int, formula: str) -> bool:
    try:
        c = shape.CellsSRC(section, row, column)
        try:
            c.FormulaForceU = formula
        except pywintypes.com_error:
            c.FormulaU = formula
        return True
    except pywintypes.com_error:
        return False


def _rows(shape: Any, section: int) -> int:
    try:
        return max(1, int(shape.RowCount(section)))
    except pywintypes.com_error:
        return 1


def _put_char_prop(chars: Any, index: int, value: int) -> None:
    """Characters.CharProps(index) = value. pywin32 exposes indexed put properties as Set<Name>."""
    try:
        chars.SetCharProps(index, value)
    except AttributeError:
        ole = chars._oleobj_
        ole.Invoke(ole.GetIDsOfNames("CharProps"), 0, pythoncom.DISPATCH_PROPERTYPUT, 0, index, value)


class VisioCom:
    """Implements visio_mcp.output.visio.backend.VisioBackend. Create and use only on the COM thread."""

    @_guard
    def __init__(self, visible: bool = True, live_delay: float = 0.0, attach: bool = False) -> None:
        self._visible = visible or attach
        self._live_delay = live_delay if self._visible else 0.0
        app = _running_app() if attach else None
        self._owns_app = app is None
        self._app = app if app is not None else _start_app(self._visible)
        self._alert_before = self._app.AlertResponse
        self._events_before = self._app.EventsEnabled
        self._app.AlertResponse = ALERT_NO
        if self._visible:
            self._app.Visible = True
            self._app.ScreenUpdating = 1
            if self._owns_app:
                self._show_window(maximize=True)
        else:
            # Some masters (org chart) run add-ons on drop, which hang a headless Visio.
            self._app.EventsEnabled = False
        self._doc: Any = None
        self._doc_ours = False
        self._stencils: dict[str, Any] = {}
        self._opened_stencils: list[Any] = []  # stencils we opened (the user's own stay open)
        self._rich: set[str] = set()  # shapes with styled runs: style_shape keeps their character rows
        self._fonts: dict[str, str] = {}
        try:
            self._app.Settings.SetRasterExportResolution(3, 150.0, 150.0, 0)  # custom, 150 dpi
        except (pywintypes.com_error, AttributeError):
            pass

    # lifecycle
    def close(self) -> None:
        """Headless: quit Visio without saving. Visible: leave the user's drawings on screen.

        An attached Visio is never quit; one we started visibly is quit only when every open
        drawing is saved (nothing the user could lose), otherwise it stays up for them.
        """
        try:
            if not self._visible:
                self._release_doc()
                self._app.EventsEnabled = True
                self._app.Quit()
            else:
                self._doc = None
                drawings = [d for d in self._app.Documents if d.Type == DOC_DRAWING]
                if self._owns_app and all(d.Saved for d in drawings):
                    self._app.Quit()
                else:
                    for s in self._opened_stencils:
                        try:
                            s.Close()
                        except pywintypes.com_error:
                            pass
                    self._app.AlertResponse = self._alert_before
                    self._app.EventsEnabled = self._events_before
        except pywintypes.com_error:
            pass
        self._doc, self._stencils, self._opened_stencils = None, {}, []

    quit = close

    # documents
    @_guard
    def new_document(self, title: str) -> None:
        self._release_doc()
        self._doc = self._app.Documents.Add("")
        self._doc_ours = True
        self._doc.Title = title
        self._reset_doc_state()
        if self._visible:
            self._activate_window()
            self._show_window()

    @_guard
    def open_document(self, path: str) -> None:
        target = Path(path).resolve()
        self._release_doc()
        for d in self._app.Documents:  # already open in the user's Visio: reuse, never close it
            try:
                if d.FullName and Path(d.FullName).resolve() == target:
                    self._doc, self._doc_ours = d, False
                    break
            except (pywintypes.com_error, OSError):
                continue
        else:
            self._doc, self._doc_ours = self._app.Documents.Open(str(target)), True
        self._reset_doc_state()
        if self._visible:
            self._activate_window()

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
        ext = target.suffix.lower()
        if ext not in (".png", ".svg", ".jpg", ".jpeg", ".pdf"):
            raise ValueError(f"unsupported export format {ext!r} (use png, svg, jpg or pdf)")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        if ext in (".png", ".svg", ".jpg", ".jpeg"):
            self._page().Export(str(target))
        elif ext == ".pdf":
            index = self._page().Index
            self._need_doc().ExportAsFixedFormat(
                FIXED_FORMAT_PDF, str(target), 0, PRINT_FROM_TO, index, index
            )
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
        self._check_new(name)
        shape = self._page().Drop(m, x, y)
        self._name(shape, name)
        if width is not None:
            shape.CellsU("Width").ResultIU = width
        if height is not None:
            shape.CellsU("Height").ResultIU = height
        self._tick()

    @_guard
    def drop_image(self, name: str, path: str, x: float, y: float, width: float, height: float) -> None:
        """Page.Import an .svg/.png (Visio 2016+) and fit it, aspect kept, into width x height at (x, y).

        An SVG may arrive as a picture or as a group of converted shapes; either takes text, so
        the label is set on the imported shape itself. Nothing is left on the page on failure.
        """
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"icon file not found: {p}")
        self._check_new(name)
        shape = self._page().Import(str(p))
        try:
            self._name(shape, name)
            w0 = float(shape.CellsU("Width").ResultIU) or width
            h0 = float(shape.CellsU("Height").ResultIU) or height
            k = min(width / w0, height / h0) if w0 > 0 and h0 > 0 else 1.0
            _set(shape, "LockAspect", "0")
            _set(shape, "Width", _inch(round(w0 * k, 4)))
            _set(shape, "Height", _inch(round(h0 * k, 4)))
            _set(shape, "PinX", _inch(x))
            _set(shape, "PinY", _inch(y))
            _set(shape, "LockAspect", "1")
            _set(shape, "LockTextEdit", "0")
        except pywintypes.com_error:
            try:
                shape.Delete()
            except pywintypes.com_error:
                pass
            raise
        self._tick()

    @_guard
    def set_text(self, name: str, text: str) -> None:
        self._find(name).Text = text
        self._rich.discard(name)

    @_guard
    def set_rich_text(self, name: str, runs: list[TextRun]) -> None:
        self._write_runs(self._find(name), runs)
        self._rich.add(name)

    @_guard
    def set_fill(self, name: str, color: str) -> None:
        formula = _rgb(color)
        shape = self._find(name)
        shape.CellsU("FillForegnd").FormulaU = formula
        shape.CellsU("FillPattern").FormulaU = "1"

    @_guard
    def style_shape(
        self, name: str, style: ShapeStyle, keep_fill: bool = False, label_below: bool = False
    ) -> None:
        shape = self._find(name)
        if not keep_fill:
            self._apply_frame(shape, style)
        self._shadow(shape, style.shadow and not keep_fill)
        if name not in self._rich:
            self._text_style(shape, style.text)
        self._paragraphs(shape, "center")
        for cell in ("LeftMargin", "RightMargin", "TopMargin", "BottomMargin"):
            _set(shape, cell, TEXT_MARGIN)
        _set(shape, "TextBkgnd", "0")  # transparent text block
        if label_below:
            self._label_below(shape)
        else:
            _set(shape, "VerticalAlign", str(VERT_MIDDLE))

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
        self._check_new(name)
        conn = self._page().Drop(self._master("BASFLO_U.VSSX", "Dynamic connector"), 0, 0)
        conn.CellsU("BeginX").GlueTo(src.CellsU("PinX"))
        conn.CellsU("EndX").GlueTo(dst.CellsU("PinX"))
        self._name(conn, name)
        conn.Text = label
        conn.CellsU("LinePattern").FormulaU = str(LINE_PATTERNS[pattern])
        self._arrows(conn, arrow)
        self._tick()

    @_guard
    def style_connector(self, name: str, style: EdgeStyle, color: str | None = None) -> None:
        conn = self._find(name)
        _set(conn, "LineColor", _rgb(color or style.color))
        _set(conn, "LineWeight", _pt(style.weight))
        _set(conn, "LineColorTrans", "0%")
        _set(conn, "Rounding", _inch(style.corner))
        _set(conn, "ShapeRouteStyle", str(ROUTE_RIGHT_ANGLE))
        _set(conn, "ConLineRouteExt", str(ROUTE_EXT_STRAIGHT))
        _set(conn, "ConLineJumpStyle", str(JUMP_ARC))
        _set(conn, "BeginArrowSize", str(ARROW_SIZE_MEDIUM))
        _set(conn, "EndArrowSize", str(ARROW_SIZE_MEDIUM))
        self._shadow(conn, False)
        if name not in self._rich:
            self._text_style(conn, style.text)
        self._paragraphs(conn, "center")
        if style.label_bg:  # TextBkgnd 0 is transparent, so pure black becomes RGB(1,1,1)
            bg = _rgb(style.label_bg)
            _set(conn, "TextBkgnd", "RGB(1,1,1)" if bg == "RGB(0,0,0)" else bg)
            _set(conn, "TextBkgndTrans", "0%")
        else:
            _set(conn, "TextBkgnd", "0")

    @_guard
    def add_container(
        self,
        name: str,
        label: str,
        members: list[str],
        style: GroupStyle | None = None,
        bounds: tuple[float, float, float, float] | None = None,
    ) -> None:
        self._check_new(name)
        page = self._page()
        master = self._master("SDCONT_U.VSSX", "Plain")
        if members:
            selection = page.CreateSelection(0, 0)  # empty selection
            for m in members:
                selection.Select(self._find(m), SEL_SELECT)
            container = page.DropContainer(master, selection)
        else:
            x, y = (bounds[0], bounds[1]) if bounds else (1.0, 1.0)
            container = page.Drop(master, x, y)
        self._name(container, name)
        container.Text = label
        self._rich.discard(name)
        if style is not None:
            _set(container, "User.msvSDContainerMargin", _inch(style.padding))
            self._apply_frame(container, style.shape)
            self._shadow(container, False)
            self._text_style(container, style.header)
            self._paragraphs(container, "left")
            for sub in self._subshapes(container):  # heading parts, if the master has any
                if sub.Text:
                    self._text_style(sub, style.header)
                    self._paragraphs(sub, "left")
        if bounds is not None:
            self._no_auto_resize(container)
            self._set_bounds(container, bounds, members)
        self._to_back(container)  # parents come after children, so nesting stays in order
        self._tick()

    @_guard
    def add_box(self, name: str, x: float, y: float, width: float, height: float, style: ShapeStyle) -> None:
        self._check_new(name)
        box = self._page().DrawRectangle(x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        self._name(box, name)
        self._apply_frame(box, style)
        self._shadow(box, style.shadow)
        self._text_style(box, style.text)
        self._tick()

    @_guard
    def add_text(
        self,
        name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        runs: list[TextRun],
        align: Align = "left",
    ) -> None:
        self._check_new(name)
        box = self._page().DrawRectangle(x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        self._name(box, name)
        _set(box, "FillPattern", "0")
        _set(box, "LinePattern", "0")
        self._shadow(box, False)
        for cell in ("LeftMargin", "RightMargin", "TopMargin", "BottomMargin"):
            _set(box, cell, "0 pt")
        _set(box, "TextBkgnd", "0")
        _set(box, "VerticalAlign", str(VERT_MIDDLE))
        self._write_runs(box, runs)
        self._rich.add(name)
        self._paragraphs(box, align)
        self._tick()

    @_guard
    def add_line(
        self, name: str, x1: float, y1: float, x2: float, y2: float, style: EdgeStyle,
        pattern: LinePattern = "solid", arrow: ArrowMode = "end",
    ) -> None:
        self._check_new(name)
        line = self._page().DrawLine(x1, y1, x2, y2)
        self._name(line, name)
        _set(line, "LineColor", _rgb(style.color))
        _set(line, "LineWeight", _pt(style.weight))
        _set(line, "LinePattern", str(LINE_PATTERNS[pattern]))
        _set(line, "BeginArrowSize", str(ARROW_SIZE_MEDIUM))
        _set(line, "EndArrowSize", str(ARROW_SIZE_MEDIUM))
        self._shadow(line, False)
        self._arrows(line, arrow)
        self._tick()

    @_guard
    def send_to_back(self, name: str) -> None:
        self._to_back(self._find(name))

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
        self._rich.discard(name)

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
    def set_page(self, width: float, height: float, background: str | None = None) -> None:
        sheet = self._page().PageSheet
        _set(sheet, "DrawingSizeType", str(DRAWING_SIZE_CUSTOM))
        _set(sheet, "DrawingResizeType", str(DRAWING_NO_AUTO_RESIZE))
        sheet.CellsU("PageWidth").ResultIU = width
        sheet.CellsU("PageHeight").ResultIU = height
        bg = self._find_opt(BACKGROUND)
        if background is None:
            if bg is not None:
                bg.Delete()
        else:
            self._background(_rgb(background), bg)
        if self._visible:
            self._fit_window()

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
        self.fit_page(0.5)

    @_guard
    def fit_page(self, margin: float = 0.5) -> None:
        page = self._page()
        bg = self._find_opt(BACKGROUND)
        fill = None
        if bg is not None:  # take it out so the fit sees only the drawing, then rebuild it
            fill = bg.CellsU("FillForegnd").FormulaU
            bg.Delete()
        page.ResizeToFitContents()
        sheet = page.PageSheet
        for cell in ("PageWidth", "PageHeight"):
            sheet.CellsU(cell).ResultIU += 2 * margin
        page.CreateSelection(SEL_TYPE_ALL, 0).Move(margin, margin)
        if fill is not None:
            self._background(fill, None)
        if self._visible:
            self._fit_window()

    @_guard
    def present(self) -> None:
        if not self._visible:
            return
        self._activate_window()
        try:
            win = self._app.ActiveWindow
            win.ViewFit = FIT_PAGE
            win.DeselectAll()
        except pywintypes.com_error:
            pass
        self._show_window()

    # helpers: text
    def _write_runs(self, shape: Any, runs: list[TextRun]) -> None:
        """Set the text once, then give each run its own Character row and style that row."""
        shape.Text = "".join(r.text for r in runs)
        runs = [r for r in runs if r.text]
        if not runs:
            return
        if len(runs) > 1:
            try:
                pos = 0
                for i, run in enumerate(runs):
                    n = _u16len(run.text)
                    chars = shape.Characters
                    chars.Begin = pos
                    chars.End = pos + n
                    # A unique temporary size splits the range into its own row; real cells come next.
                    _put_char_prop(chars, CHAR_SIZE, 100 + i)
                    row = int(chars.CharPropsRow(BIAS_LET_VISIO_CHOOSE))
                    if row < 0:
                        raise ValueError("run spans several character rows")
                    self._char_row(shape, row, run.style)
                    pos += n
                return
            except (pywintypes.com_error, ValueError, AttributeError):
                pass  # fall back to one style for the whole text
        self._text_style(shape, runs[0].style)

    def _char_row(self, shape: Any, row: int, st: TextStyle) -> None:
        font = self._font(st.font)
        if font:
            _set_src(shape, SECTION_CHARACTER, row, 0, font)  # visCharacterFont
        _set_src(shape, SECTION_CHARACTER, row, 1, _rgb(st.color))  # visCharacterColor
        _set_src(shape, SECTION_CHARACTER, row, 2,  # visCharacterStyle
                 str((STYLE_BOLD if st.bold else 0) | (STYLE_ITALIC if st.italic else 0)))
        _set_src(shape, SECTION_CHARACTER, row, CHAR_SIZE, _pt(st.size))

    def _text_style(self, shape: Any, st: TextStyle) -> None:
        """One style for every character row of the shape."""
        for row in range(_rows(shape, SECTION_CHARACTER)):
            self._char_row(shape, row, st)

    def _paragraphs(self, shape: Any, align: str) -> None:
        for row in range(_rows(shape, SECTION_PARAGRAPH)):
            _set_src(shape, SECTION_PARAGRAPH, row, PARA_HORZ_ALIGN, str(HORZ_ALIGN[align]))

    def _font(self, name: str) -> str | None:
        """Char.Font formula: the font's ID in this document (FONT() formula as a fallback)."""
        if name not in self._fonts:
            try:
                self._fonts[name] = str(int(self._need_doc().Fonts(name).ID))
            except (pywintypes.com_error, TypeError, ValueError):
                self._fonts[name] = f'FONT("{name}")'
        return self._fonts[name]

    def _label_below(self, shape: Any) -> None:
        """Text block under the shape (icons), wide enough for two lines, tracking its size."""
        if not shape.CellExistsU("TxtPinX", 0):
            try:
                shape.AddRow(1, 12, 0)  # visSectionObject, visRowTextXForm, visTagDefault
            except pywintypes.com_error:
                return
        for cell, formula in (
            ("TxtWidth", "MAX(1.7 in,Width*2)"),
            ("TxtHeight", _inch(LABEL_BELOW_HEIGHT)),
            ("TxtPinX", "Width*0.5"),
            ("TxtPinY", "-TxtHeight*0.5-0.04 in"),
            ("TxtLocPinX", "TxtWidth*0.5"),
            ("TxtLocPinY", "TxtHeight*0.5"),
            ("TxtAngle", "0 deg"),
            ("VerticalAlign", str(VERT_TOP)),
        ):
            _set(shape, cell, formula)

    # helpers: formatting
    def _apply_frame(self, shape: Any, style: ShapeStyle) -> None:
        """Fill, line and rounding as explicit local formulas (they override master/theme values)."""
        if style.fill is None:
            _set(shape, "FillPattern", "0")
        else:
            for cell in ("FillForegnd", "FillBkgnd"):
                _set(shape, cell, _rgb(style.fill))
            _set(shape, "FillForegndTrans", "0%")
            _set(shape, "FillPattern", "1")
            _set(shape, "FillGradientEnabled", "FALSE")
        if style.line is None:
            _set(shape, "LinePattern", "0")
        else:
            _set(shape, "LineColor", _rgb(style.line))
            _set(shape, "LineColorTrans", "0%")
            _set(shape, "LinePattern", str(LINE_PATTERNS[style.line_pattern]))
            _set(shape, "LineWeight", _pt(style.line_weight))
            _set(shape, "LineGradientEnabled", "FALSE")
        _set(shape, "Rounding", _inch(style.rounding))

    @staticmethod
    def _shadow(shape: Any, on: bool) -> None:
        if not on:
            _set(shape, "ShdwPattern", "0")
            return
        for cell, formula in (
            ("ShdwPattern", "1"),
            ("ShdwForegnd", "RGB(15,23,42)"),
            ("ShdwForegndTrans", "85%"),
            ("ShapeShdwType", "1"),  # simple offset shadow
            ("ShapeShdwOffsetX", "0.03 in"),
            ("ShapeShdwOffsetY", "-0.03 in"),
        ):
            _set(shape, cell, formula)

    @staticmethod
    def _arrows(shape: Any, arrow: ArrowMode) -> None:
        shape.CellsU("BeginArrow").FormulaU = str(ARROW_FILLED if arrow == "both" else 0)
        shape.CellsU("EndArrow").FormulaU = str(0 if arrow == "none" else ARROW_FILLED)

    def _background(self, fill_formula: str, bg: Any | None) -> None:
        """A locked page-sized rectangle at the very back that layout and routing ignore."""
        sheet = self._page().PageSheet
        w, h = sheet.CellsU("PageWidth").ResultIU, sheet.CellsU("PageHeight").ResultIU
        if bg is None:
            bg = self._page().DrawRectangle(0, 0, w, h)
            self._name(bg, BACKGROUND)
        else:
            for cell, v in (("Width", w), ("Height", h), ("PinX", w / 2), ("PinY", h / 2)):
                bg.CellsU(cell).ResultIU = v
        for cell, formula in (
            ("FillForegnd", fill_formula),
            ("FillBkgnd", fill_formula),
            ("FillPattern", "1"),
            ("LinePattern", "0"),
            ("ShdwPattern", "0"),
            ("ObjType", str(OBJ_TYPE_NONE)),
            ("ShapePermeableX", "TRUE"),  # connectors route straight across it
            ("ShapePermeableY", "TRUE"),
            ("ShapePermeablePlace", "TRUE"),
            ("LockSelect", "1"),
            ("LockTextEdit", "1"),
        ):
            _set(bg, cell, formula)
        bg.SendToBack()

    def _to_back(self, shape: Any) -> None:
        shape.SendToBack()
        if shape.NameU != BACKGROUND:
            bg = self._find_opt(BACKGROUND)
            if bg is not None:
                bg.SendToBack()

    # helpers: containers
    @staticmethod
    def _no_auto_resize(container: Any) -> None:
        try:
            container.ContainerProperties.ResizeAsNeeded = CONTAINER_NO_RESIZE
        except (pywintypes.com_error, AttributeError):
            _set(container, "User.msvSDContainerResize", str(CONTAINER_NO_RESIZE))

    def _set_bounds(self, container: Any, bounds: tuple[float, float, float, float], members: list[str]) -> None:
        """Place the frame exactly; moving a container may drag its members, so put them back."""
        cx, cy, w, h = bounds
        inside = self._inside(members)
        before = {n: (s.CellsU("PinX").ResultIU, s.CellsU("PinY").ResultIU) for n, s in inside}
        container.CellsU("Width").ResultIU = w
        container.CellsU("Height").ResultIU = h
        container.CellsU("PinX").ResultIU = cx - w / 2 + container.CellsU("LocPinX").ResultIU
        container.CellsU("PinY").ResultIU = cy - h / 2 + container.CellsU("LocPinY").ResultIU
        # outer containers first: restoring one also brings back everything inside it
        order = sorted(inside, key=lambda p: (not self._is_container(p[1]),
                                              -p[1].CellsU("Width").ResultIU * p[1].CellsU("Height").ResultIU))
        for n, s in order:
            x, y = before[n]
            if abs(s.CellsU("PinX").ResultIU - x) > 1e-6 or abs(s.CellsU("PinY").ResultIU - y) > 1e-6:
                s.CellsU("PinX").ResultIU = x
                s.CellsU("PinY").ResultIU = y

    def _inside(self, members: list[str]) -> list[tuple[str, Any]]:
        """Members and, for member containers, everything they hold (by name)."""
        out: dict[str, Any] = {}
        todo = list(members)
        while todo:
            n = todo.pop()
            if n in out:
                continue
            s = self._find(n)
            if s.OneD:  # glued connectors follow their shapes by themselves
                continue
            out[n] = s
            if self._is_container(s):
                try:
                    ids = s.ContainerProperties.GetMemberShapes(0)  # 0: all members, as shape IDs
                    todo += [self._page().Shapes.ItemFromID(i).NameU for i in ids or ()]
                except (pywintypes.com_error, AttributeError, TypeError):
                    pass
        return list(out.items())

    @staticmethod
    def _subshapes(shape: Any) -> list[Any]:
        try:
            return list(shape.Shapes)
        except (pywintypes.com_error, TypeError):
            return []

    # helpers: windows and live drawing
    def _tick(self) -> None:
        """Live mode: let Visio repaint and give the viewer a moment to see the new shape."""
        if self._live_delay <= 0:
            return
        try:
            pythoncom.PumpWaitingMessages()
        except Exception:
            pass
        time.sleep(self._live_delay)

    def _activate_window(self) -> None:
        """Bring our document's drawing window to the front inside Visio."""
        doc = self._doc
        if doc is None:
            return
        try:
            for w in self._app.Windows:
                try:
                    if w.Type == WIN_DRAWING and w.Document.Name == doc.Name:
                        w.Activate()
                        return
                except pywintypes.com_error:
                    continue
        except pywintypes.com_error:
            pass

    def _fit_window(self) -> None:
        try:
            self._app.ActiveWindow.ViewFit = FIT_PAGE
        except pywintypes.com_error:
            pass

    def _show_window(self, maximize: bool = False) -> None:
        """Bring the Visio main window to the foreground (Windows may refuse; that is fine)."""
        try:
            import win32con
            import win32gui

            hwnd = int(self._app.WindowHandle32)
            if maximize:
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            elif win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    # helpers: documents and lookup
    def _need_doc(self) -> Any:
        if self._doc is None:
            raise RuntimeError("no document open: call new_document or open_document first")
        return self._doc

    def _page(self) -> Any:
        return self._need_doc().Pages(1)

    def _reset_doc_state(self) -> None:
        self._rich, self._fonts = set(), {}

    def _release_doc(self) -> None:
        """Stop using the current document.

        Headless: close it, discarding changes. Visible: leave it on screen so the user can
        compare renders, except our own document when nothing changed since our last save.
        Documents we did not create are never closed.
        """
        doc, self._doc = self._doc, None
        if doc is None or not self._doc_ours:
            return
        try:
            if not self._visible:
                doc.Saved = True  # discard changes, no prompt
                doc.Close()
            elif doc.Saved and doc.FullName and os.path.isfile(doc.FullName):
                doc.Close()
        except pywintypes.com_error:
            pass  # the user already closed it

    def _stencil(self, name: str) -> Any | None:
        key = name.upper()
        if key in self._stencils:
            try:
                self._stencils[key].Name  # the user may have closed it
            except pywintypes.com_error:
                del self._stencils[key]
        if key not in self._stencils:
            for d in self._app.Documents:  # the user may already have it docked
                try:
                    if d.Name.upper() == key:
                        self._stencils[key] = d
                        return d
                except pywintypes.com_error:
                    continue
            try:
                self._stencils[key] = self._app.Documents.OpenEx(name, OPEN_RO_HIDDEN)
                self._opened_stencils.append(self._stencils[key])
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

    def _find_opt(self, name: str) -> Any | None:
        try:
            return self._page().Shapes.ItemU(name)
        except pywintypes.com_error:
            return None

    def _exists(self, name: str) -> bool:
        return self._find_opt(name) is not None

    def _check_new(self, name: str) -> None:
        if self._exists(name):
            raise KeyError(f"duplicate shape name {name!r}")

    @staticmethod
    def _name(shape: Any, name: str) -> None:
        shape.Name = name
        shape.NameU = name

    @staticmethod
    def _is_container(shape: Any) -> bool:
        cell = "User.msvStructureType"
        return bool(shape.CellExistsU(cell, 0)) and "Container" in shape.CellsU(cell).FormulaU
