"""Output file naming, the default output folder, opening files, and saving around locked files."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable


def slug(text: str) -> str:
    """A file-name-safe lowercase stem ('diagram' when nothing is left)."""
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "diagram"


def default_out_dir() -> Path:
    """$VISIO_MCP_OUT or ~/Documents/visio-mcp, created if missing."""
    d = Path(os.environ.get("VISIO_MCP_OUT") or Path.home() / "Documents" / "visio-mcp")
    d.mkdir(parents=True, exist_ok=True)
    return d


def open_file(path: str | Path) -> None:
    """Open a file with the OS default app (Visio for .vsdx, browser for .html)."""
    p = str(path)
    if sys.platform == "win32":
        os.startfile(p)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def free_name(p: Path) -> Path:
    """The first 'name-N.ext' (N >= 2) next to p that does not exist yet."""
    n = 2
    while (alt := p.with_name(f"{p.stem}-{n}{p.suffix}")).exists():
        n += 1
    return alt


def save_free(save: Callable[[Path], Path], path: Path) -> tuple[Path, str | None]:
    """save(path), or save under a free name when the file is open elsewhere (e.g. in Visio).

    Returns (saved file, warning for the user or None).
    """
    try:
        return save(path), None
    except PermissionError:
        alt = free_name(path)
        return save(alt), f"{path.name} is open in another program; saved as {alt.name}"
