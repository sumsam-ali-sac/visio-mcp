"""Turn user-typed folder paths (quoted, ~, env vars) into a resolved directory."""

from __future__ import annotations

import os
from pathlib import Path


def normalize_path(path: str | Path) -> Path:
    """Strip quotes/whitespace, expand ~ and env vars. Accepts pasted Windows paths."""
    raw = str(path).strip()
    while len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1].strip()
    raw = raw.strip("\"'")
    raw = os.path.expandvars(raw)
    p = Path(raw).expanduser()
    return p


def resolve_dir(path: str | Path) -> Path:
    p = normalize_path(path)
    if not str(p).strip() or str(p) == ".":
        p = Path.cwd()
    if not p.exists():
        raise FileNotFoundError(
            f"Folder not found: {p}. Check the path and make sure the repository is cloned on this machine."
        )
    if not p.is_dir():
        raise NotADirectoryError(f"Not a folder: {p}. Point me at a repository folder, not a file.")
    return p.resolve()
