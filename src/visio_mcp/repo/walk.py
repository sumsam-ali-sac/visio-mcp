"""Deterministic file walk of a repo folder honoring ignore rules."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .ignore import GitIgnore, is_ignored_dir

MAX_FILES = 100_000


@dataclass(slots=True)
class FileEntry:
    rel: str
    size: int

    @property
    def name(self) -> str:
        return self.rel.rsplit("/", 1)[-1]

    @property
    def depth(self) -> int:
        return self.rel.count("/")


def walk(root: Path, gi: GitIgnore | None = None, max_files: int = MAX_FILES) -> list[FileEntry]:
    """All files under root (posix-style relative paths), skipping ignored dirs early. Deterministic."""
    out: list[FileEntry] = []
    stack: list[tuple[str, str]] = [(str(root), "")]
    while stack and len(out) < max_files:
        dpath, rel = stack.pop()
        try:
            with os.scandir(dpath) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        subdirs: list[tuple[str, str]] = []
        for e in entries:
            name = e.name
            erel = f"{rel}/{name}" if rel else name
            try:
                if e.is_dir(follow_symlinks=False):
                    if is_ignored_dir(name) or (gi and gi.ignored(erel, name, True)):
                        continue
                    subdirs.append((e.path, erel))
                elif e.is_file(follow_symlinks=False):
                    if gi and gi.ignored(erel, name, False):
                        continue
                    out.append(FileEntry(erel, e.stat(follow_symlinks=False).st_size))
            except OSError:
                continue
        stack.extend(reversed(subdirs))
    return out
