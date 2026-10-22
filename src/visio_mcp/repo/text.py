"""Safe text helpers: bounded file reads, shortening and credential-stripping for display."""

from __future__ import annotations

import re
from pathlib import Path

TEXT_LIMIT = 262_144


def read_text(path: Path | str, limit: int = TEXT_LIMIT) -> str:
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit)
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def short(s: str, n: int = 24) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def sanitize_value(v: str) -> str:
    v = re.sub(r"(://[^/:@\s]+):[^@\s]+@", r"\1:***@", v)
    return v if len(v) <= 80 else v[:77] + "..."
