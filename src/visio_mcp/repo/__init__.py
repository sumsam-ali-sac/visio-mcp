"""Repository scanner: discover repos, profile them, give an AI safe file access, draw a no-AI fallback."""

from __future__ import annotations

from ._common import IGNORE_DIRS
from .detect import discover, scan
from .fs import RepoFS, redact
from .draft import heuristic_spec
from .model import RepoInfo
from .digest import cross_links, digest, tree, workspace_digest

__all__ = [
    "IGNORE_DIRS",
    "RepoFS",
    "RepoInfo",
    "cross_links",
    "digest",
    "discover",
    "heuristic_spec",
    "redact",
    "scan",
    "tree",
    "workspace_digest",
]
