"""Find built-in stencils and their masters, opening stencils hidden on first use."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pywintypes

OPEN_RO_HIDDEN = 2 + 64  # visOpenRO + visOpenHidden


def installed(app: Any) -> list[str]:
    """Built-in stencil file names on this machine (app language, else en-US), e.g. 'BASFLO_U.VSSX'."""
    base = Path(app.Path) / "Visio Content"
    folder = base / str(app.Language)
    if not folder.is_dir():
        folder = base / "1033"
    if not folder.is_dir():
        return []
    return sorted(p.name.upper() for p in folder.glob("*.vssx") if p.stem.upper().endswith("_U"))


class Stencils:
    """Stencil documents by file name. Only stencils opened here are closed by close()."""

    def __init__(self, app: Any) -> None:
        self._app = app
        self._docs: dict[str, Any] = {}
        self._opened: list[Any] = []  # the user's own docked stencils stay open

    def get(self, name: str) -> Any | None:
        key = name.upper()
        if key in self._docs:
            try:
                self._docs[key].Name  # the user may have closed it
            except pywintypes.com_error:
                del self._docs[key]
        if key not in self._docs:
            for d in self._app.Documents:  # the user may already have it docked
                try:
                    if d.Name.upper() == key:
                        self._docs[key] = d
                        return d
                except pywintypes.com_error:
                    continue
            try:
                self._docs[key] = self._app.Documents.OpenEx(name, OPEN_RO_HIDDEN)
                self._opened.append(self._docs[key])
            except pywintypes.com_error:
                return None
        return self._docs[key]

    def master(self, stencil: str, master: str) -> Any | None:
        doc = self.get(stencil)
        if doc is None:
            return None
        try:
            return doc.Masters.ItemU(master)
        except pywintypes.com_error:
            return None

    def masters(self, stencil: str) -> list[str]:
        doc = self.get(stencil)
        return [m.NameU for m in doc.Masters] if doc is not None else []

    def close(self) -> None:
        for s in self._opened:
            try:
                s.Close()
            except pywintypes.com_error:
                pass
