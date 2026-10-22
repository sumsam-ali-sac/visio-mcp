"""Reads an installed pack's index.json, cached by file mtime."""

from __future__ import annotations

import json
from pathlib import Path

from visio_mcp.icons.names import squash
from visio_mcp.icons.paths import INDEX, provider_dir

_cache: dict[Path, tuple[float, dict]] = {}


def load_index(provider: str) -> dict | None:
    p = provider_dir(provider) / INDEX
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    hit = _cache.get(p)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data.get("icons"), dict):
            return None
    except (OSError, ValueError, AttributeError):
        return None
    data["_squashed"] = {}
    for k in data["icons"]:
        data["_squashed"].setdefault(squash(k), k)
    _cache[p] = (mtime, data)
    return data


def forget(provider: str) -> None:
    """Drop the cached index after a pack was written or removed."""
    _cache.pop(provider_dir(provider) / INDEX, None)
