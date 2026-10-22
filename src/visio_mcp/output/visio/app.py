"""Start or attach to the Visio application and manage its windows and live repaints."""

from __future__ import annotations

import time
from typing import Any

import pythoncom
import pywintypes
import win32com.client

from visio_mcp.output.visio.errors import message

ALERT_NO = 7  # AlertResponse: answer "No" to any prompt
WIN_DRAWING = 1  # visDrawing (Window.Type)
FIT_PAGE = 1  # visFitPage (Window.ViewFit)
RASTER_DPI = 150.0


def start(visible: bool) -> Any:
    """Start a Visio of our own, retrying while it is busy ('Call was rejected by callee')."""
    prog_id = "Visio.Application" if visible else "Visio.InvisibleApp"
    for attempt in range(6):
        try:
            return win32com.client.DispatchEx(prog_id)
        except pywintypes.com_error as e:
            if attempt == 5:
                raise RuntimeError(f"could not start Visio: {message(e)}") from None
            time.sleep(1.0)
    raise AssertionError("unreachable")


def running() -> Any | None:
    """The Visio the user already has open, or None."""
    try:
        return win32com.client.GetActiveObject("Visio.Application")
    except pywintypes.com_error:
        return None


def set_export_resolution(app: Any) -> None:
    """PNG/JPG exports at a fixed custom resolution instead of screen resolution."""
    try:
        app.Settings.SetRasterExportResolution(3, RASTER_DPI, RASTER_DPI, 0)  # 3: custom
    except (pywintypes.com_error, AttributeError):
        pass


def pump(delay: float) -> None:
    """Live mode: let Visio repaint and give the viewer a moment to see the new shape."""
    if delay <= 0:
        return
    try:
        pythoncom.PumpWaitingMessages()
    except Exception:
        pass
    time.sleep(delay)


def activate_window(app: Any, doc: Any | None) -> None:
    """Bring the document's drawing window to the front inside Visio."""
    if doc is None:
        return
    try:
        for w in app.Windows:
            try:
                if w.Type == WIN_DRAWING and w.Document.Name == doc.Name:
                    w.Activate()
                    return
            except pywintypes.com_error:
                continue
    except pywintypes.com_error:
        pass


def fit_window(app: Any) -> None:
    """Zoom the active window to the whole page."""
    try:
        app.ActiveWindow.ViewFit = FIT_PAGE
    except pywintypes.com_error:
        pass


def present(app: Any, doc: Any | None) -> None:
    """Our drawing in front, zoomed to the page, nothing selected."""
    activate_window(app, doc)
    try:
        win = app.ActiveWindow
        win.ViewFit = FIT_PAGE
        win.DeselectAll()
    except pywintypes.com_error:
        pass
    show_window(app)


def show_window(app: Any, maximize: bool = False) -> None:
    """Bring the Visio main window to the foreground (Windows may refuse; that is fine)."""
    try:
        import win32con
        import win32gui

        hwnd = int(app.WindowHandle32)
        if maximize:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        elif win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
