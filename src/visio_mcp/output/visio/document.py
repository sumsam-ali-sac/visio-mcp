"""Open, release, save and export Visio documents."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pywintypes

FIXED_FORMAT_PDF = 1  # visFixedFormatPDF
PRINT_FROM_TO = 2  # visPrintFromTo
DOC_DRAWING = 1  # visTypeDrawing (Document.Type)
EXPORT_FORMATS = (".png", ".svg", ".jpg", ".jpeg", ".pdf")


def first_page(doc: Any) -> Any:
    return doc.Pages(1)


def open_or_reuse(app: Any, path: str) -> tuple[Any, bool]:
    """(document, opened by us). A file already open in the user's Visio is reused, never closed."""
    target = Path(path).resolve()
    for d in app.Documents:
        try:
            if d.FullName and Path(d.FullName).resolve() == target:
                return d, False
        except (pywintypes.com_error, OSError):
            continue
    return app.Documents.Open(str(target)), True


def release(doc: Any | None, ours: bool, visible: bool) -> None:
    """Stop using a document.

    Headless: close it, discarding changes. Visible: leave it on screen so the user can
    compare renders, except our own document when nothing changed since our last save.
    Documents we did not create are never closed.
    """
    if doc is None or not ours:
        return
    try:
        if not visible:
            doc.Saved = True  # discard changes, no prompt
            doc.Close()
        elif doc.Saved and doc.FullName and os.path.isfile(doc.FullName):
            doc.Close()
    except pywintypes.com_error:
        pass  # the user already closed it


def unsaved_drawings(app: Any) -> bool:
    """True when any open drawing has changes the user could lose."""
    return not all(d.Saved for d in app.Documents if d.Type == DOC_DRAWING)


def save(doc: Any, path: str) -> str:
    """Save as .vsdx (overwriting), return the absolute path."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if doc.FullName and Path(doc.FullName).resolve() == target:
        doc.Save()
        return str(target)
    target.unlink(missing_ok=True)  # SaveAs will not overwrite when alerts answer "No"
    doc.SaveAs(str(target))
    return str(target)


def export(doc: Any, path: str) -> str:
    """Export the first page; format from the extension. Return the absolute path."""
    target = Path(path).resolve()
    ext = target.suffix.lower()
    if ext not in EXPORT_FORMATS:
        raise ValueError(f"unsupported export format {ext!r} (use png, svg, jpg or pdf)")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    if ext == ".pdf":
        index = first_page(doc).Index
        doc.ExportAsFixedFormat(FIXED_FORMAT_PDF, str(target), 0, PRINT_FROM_TO, index, index)
    else:
        first_page(doc).Export(str(target))
    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError(f"Visio export produced no file at {target}")
    return str(target)
