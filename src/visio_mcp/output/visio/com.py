"""VisioCom: the VisioBackend implemented with Visio desktop over COM.

Three ways to run:
- headless (visible=False): a hidden Visio.InvisibleApp of our own (CI, servers).
- visible (default): our own Visio window; each render opens a new drawing in front of the user.
- attach=True: draw into the Visio the user already has open (falls back to starting one).
  We never quit an app we did not start, and never close documents we did not create.

live_delay > 0 pauses after every shape so the user watches the diagram build.
VisioCom keeps the session state (app, document, stencils, styled shapes) and does name
lookups; the sibling modules do the COM work on the objects it hands them.
"""

from __future__ import annotations

from typing import Any

import pywintypes

from visio_mcp.output.visio import app, connectors, containers, document, names, page, shapes, stencils, text
from visio_mcp.output.visio.backend import Align, ArrowMode, LinePattern, ShapeInfo, TextRun
from visio_mcp.output.visio.cells import rgb
from visio_mcp.output.visio.errors import guard
from visio_mcp.output.visio.page import BACKGROUND
from visio_mcp.style import EdgeStyle, GroupStyle, ShapeStyle

__all__ = ["BACKGROUND", "VisioCom"]


class VisioCom:
    """Implements visio_mcp.output.visio.backend.VisioBackend. Create and use only on the COM thread."""

    @guard
    def __init__(self, visible: bool = True, live_delay: float = 0.0, attach: bool = False) -> None:
        self._visible = visible or attach
        self._live_delay = live_delay if self._visible else 0.0
        running = app.running() if attach else None
        self._owns_app = running is None
        self._app = running if running is not None else app.start(self._visible)
        self._alert_before = self._app.AlertResponse
        self._events_before = self._app.EventsEnabled
        self._app.AlertResponse = app.ALERT_NO
        if self._visible:
            self._app.Visible = True
            self._app.ScreenUpdating = 1
            if self._owns_app:
                app.show_window(self._app, maximize=True)
        else:
            # Some masters (org chart) run add-ons on drop, which hang a headless Visio.
            self._app.EventsEnabled = False
        self._doc: Any = None
        self._doc_ours = False
        self._stencils = stencils.Stencils(self._app)
        self._rich: set[str] = set()  # shapes with styled runs: restyling keeps their character rows
        self._fonts = text.Fonts(self._need_doc)
        app.set_export_resolution(self._app)

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
                if self._owns_app and not document.unsaved_drawings(self._app):
                    self._app.Quit()
                else:
                    self._stencils.close()
                    self._app.AlertResponse = self._alert_before
                    self._app.EventsEnabled = self._events_before
        except pywintypes.com_error:
            pass
        self._doc, self._stencils = None, stencils.Stencils(self._app)

    # documents
    @guard
    def new_document(self, title: str) -> None:
        self._release_doc()
        self._doc = self._app.Documents.Add("")
        self._doc_ours = True
        self._doc.Title = title
        self._reset_doc_state()
        if self._visible:
            app.activate_window(self._app, self._doc)
            app.show_window(self._app)

    @guard
    def open_document(self, path: str) -> None:
        self._release_doc()
        self._doc, self._doc_ours = document.open_or_reuse(self._app, path)
        self._reset_doc_state()
        if self._visible:
            app.activate_window(self._app, self._doc)

    @guard
    def save(self, path: str) -> str:
        return document.save(self._need_doc(), path)

    @guard
    def export(self, path: str) -> str:
        return document.export(self._need_doc(), path)

    # stencils
    @guard
    def list_stencils(self) -> list[str]:
        return stencils.installed(self._app)

    @guard
    def list_masters(self, stencil: str) -> list[str]:
        return self._stencils.masters(stencil)

    def has_master(self, stencil: str, master: str) -> bool:
        try:
            return self._stencils.master(stencil, master) is not None
        except Exception:
            return False

    # shapes
    @guard
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
        m = self._stencils.master(stencil, master)
        if m is None:
            raise KeyError(f"no master {master!r} in {stencil!r}")
        self._check_new(name)
        shapes.drop(self._page(), name, m, x, y, width, height)
        self._tick()

    @guard
    def drop_image(self, name: str, path: str, x: float, y: float, width: float, height: float) -> None:
        file = shapes.image_file(path)
        self._check_new(name)
        shapes.import_image(self._page(), name, file, x, y, width, height)
        self._tick()

    @guard
    def set_text(self, name: str, text: str) -> None:
        self._find(name).Text = text
        self._rich.discard(name)

    @guard
    def set_rich_text(self, name: str, runs: list[TextRun]) -> None:
        text.write_runs(self._find(name), runs, self._fonts)
        self._rich.add(name)

    @guard
    def set_fill(self, name: str, color: str) -> None:
        formula = rgb(color)
        shapes.fill(self._find(name), formula)

    @guard
    def style_shape(
        self, name: str, style: ShapeStyle, keep_fill: bool = False, label_below: bool = False
    ) -> None:
        shapes.style(self._find(name), style, self._fonts, keep_fill, label_below, restyle_text=name not in self._rich)

    @guard
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
        master = self._stencils.master(connectors.STENCIL, connectors.MASTER)
        connectors.connect(self._page(), name, src, dst, master, label, pattern, arrow)
        self._tick()

    @guard
    def style_connector(self, name: str, style: EdgeStyle, color: str | None = None) -> None:
        connectors.style(self._find(name), style, color, self._fonts, restyle_text=name not in self._rich)

    @guard
    def add_container(
        self,
        name: str,
        label: str,
        members: list[str],
        style: GroupStyle | None = None,
        bounds: tuple[float, float, float, float] | None = None,
    ) -> None:
        self._check_new(name)
        pg = self._page()
        master = self._stencils.master(containers.STENCIL, containers.MASTER)
        container = containers.drop(pg, name, master, label, members, bounds)
        self._rich.discard(name)
        if style is not None:
            containers.style(container, style, self._fonts)
        if bounds is not None:
            containers.pin(pg, container, bounds, members)
        page.to_back(pg, container)  # parents come after children, so nesting stays in order
        self._tick()

    @guard
    def add_box(self, name: str, x: float, y: float, width: float, height: float, style: ShapeStyle) -> None:
        self._check_new(name)
        shapes.box(self._page(), name, x, y, width, height, style, self._fonts)
        self._tick()

    @guard
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
        shapes.text_block(self._page(), name, x, y, width, height, runs, align, self._fonts)
        self._rich.add(name)
        self._tick()

    @guard
    def add_line(
        self, name: str, x1: float, y1: float, x2: float, y2: float, style: EdgeStyle,
        pattern: LinePattern = "solid", arrow: ArrowMode = "end",
    ) -> None:
        self._check_new(name)
        connectors.line(self._page(), name, x1, y1, x2, y2, style, pattern, arrow)
        self._tick()

    @guard
    def move(self, name: str, x: float, y: float) -> None:
        shapes.move(self._find(name), x, y)

    @guard
    def delete(self, name: str) -> None:
        shapes.delete(self._page(), self._find(name), name)
        self._rich.discard(name)

    @guard
    def shapes(self) -> list[ShapeInfo]:
        return shapes.infos(self._page())

    # page
    @guard
    def set_page(self, width: float, height: float, background: str | None = None) -> None:
        page.set_size(self._page(), width, height, background)
        if self._visible:
            app.fit_window(self._app)

    @guard
    def present(self) -> None:
        if self._visible:
            app.present(self._app, self._doc)

    # state and lookup
    def _tick(self) -> None:
        app.pump(self._live_delay)

    def _need_doc(self) -> Any:
        if self._doc is None:
            raise RuntimeError("no document open: call new_document or open_document first")
        return self._doc

    def _page(self) -> Any:
        return document.first_page(self._need_doc())

    def _find(self, name: str) -> Any:
        return names.find(self._page(), name)

    def _check_new(self, name: str) -> None:
        names.check_new(self._page(), name)

    def _reset_doc_state(self) -> None:
        self._rich, self._fonts = set(), text.Fonts(self._need_doc)

    def _release_doc(self) -> None:
        doc, self._doc = self._doc, None
        document.release(doc, self._doc_ours, self._visible)
