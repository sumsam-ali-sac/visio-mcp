"""Where icon packs live on disk."""

from __future__ import annotations

import os
import sys
from pathlib import Path

INDEX = "index.json"


def cache_dir() -> Path:
    """Where icon packs live: VISIO_MCP_ICONS, else the platform's user cache folder."""
    env = os.environ.get("VISIO_MCP_ICONS")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "visio-mcp" / "icons"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "visio-mcp" / "icons"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "visio-mcp" / "icons"


def provider_dir(provider: str) -> Path:
    return cache_dir() / provider
