"""Repositories as input: discover and profile them, digest them for an AI, give it safe file access, draw a no-AI fallback."""

from __future__ import annotations

from .detect import scan
from .digest import digest, workspace_digest
from .discover import discover
from .draft import heuristic_spec
from .fs import RepoFS, RepoFSError
from .links import cross_links
from .model import RepoInfo
from .redact import redact
from .tree import tree

__all__ = [
    "RepoFS",
    "RepoFSError",
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
