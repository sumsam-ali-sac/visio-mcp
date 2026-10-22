"""Compact indented directory tree of a repo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .ignore import NOISE_FILES, NOISE_SUFFIXES, GitIgnore, is_ignored_dir
from .paths import resolve_dir


MAX_FILES_SHOWN = 12
FILES_COLLAPSE_OVER = 16
MAX_DIRS_SHOWN = 40


@dataclass
class TreeNode:
    name: str
    is_dir: bool
    children: list["TreeNode"] = field(default_factory=list)
    more_files: int = 0
    more_dirs: int = 0
    hidden: bool = False  # dir whose contents were not scanned (depth limit)


def _scan_entries(path: str, rel: str, gi: GitIgnore) -> tuple[list[str], list[str]]:
    dirs: list[str] = []
    files: list[str] = []
    try:
        with os.scandir(path) as it:
            for e in it:
                name = e.name
                erel = f"{rel}/{name}" if rel else name
                try:
                    if e.is_dir(follow_symlinks=False):
                        if is_ignored_dir(name) or gi.ignored(erel, name, True):
                            continue
                        dirs.append(name)
                    elif e.is_file(follow_symlinks=False) or e.is_symlink():
                        if name in NOISE_FILES or name.endswith(NOISE_SUFFIXES) or gi.ignored(erel, name, False):
                            continue
                        files.append(name)
                except OSError:
                    continue
    except OSError:
        pass
    key = lambda s: (s.lower(), s)  # noqa: E731
    return sorted(dirs, key=key), sorted(files, key=key)


def build_tree(path: str, rel: str, depth: int, max_depth: int, gi: GitIgnore) -> TreeNode:
    name = os.path.basename(path.rstrip(os.sep)) or path
    node = TreeNode(name, True)
    if depth >= max_depth:
        node.hidden = True
        return node
    dirs, files = _scan_entries(path, rel, gi)
    for d in dirs[:MAX_DIRS_SHOWN]:
        node.children.append(build_tree(os.path.join(path, d), f"{rel}/{d}" if rel else d, depth + 1, max_depth, gi))
    node.more_dirs = max(0, len(dirs) - MAX_DIRS_SHOWN)
    shown = files if len(files) <= FILES_COLLAPSE_OVER else files[: MAX_FILES_SHOWN - 4]
    for f in shown:
        node.children.append(TreeNode(f, False))
    node.more_files = len(files) - len(shown)
    return node


def _count(node: TreeNode, eff: int, depth: int = 0) -> int:
    n = (1 if node.more_dirs else 0) + (1 if node.more_files else 0)
    for c in node.children:
        n += 1
        if c.is_dir and depth + 1 < eff:
            n += _count(c, eff, depth + 1)
    return n


def _render(node: TreeNode, eff: int, depth: int, lines: list[str]) -> None:
    pad = "  " * (depth + 1)
    for c in node.children:
        if c.is_dir:
            expand = depth + 1 < eff
            has_more = c.hidden or bool(c.children) or c.more_files or c.more_dirs
            lines.append(f"{pad}{c.name}/" + ("" if expand or not has_more else " …"))
            if expand:
                _render(c, eff, depth + 1, lines)
        else:
            lines.append(f"{pad}{c.name}")
    if node.more_dirs:
        lines.append(f"{pad}… {node.more_dirs} more dirs")
    if node.more_files:
        lines.append(f"{pad}… {node.more_files} more files")


def render_tree(top: TreeNode, title: str, max_entries: int, max_depth: int) -> str:
    eff = max(1, max_depth)
    while eff > 1 and _count(top, eff) > max_entries:
        eff -= 1
    lines = [title.rstrip("/") + "/"]
    _render(top, eff, 0, lines)
    if len(lines) - 1 > max_entries:
        lines = lines[: max_entries + 1] + ["  … (truncated)"]
    return "\n".join(lines)


def tree(path: str | Path, max_entries: int = 300, max_depth: int = 4) -> str:
    """Compact indented tree: dirs first, noise skipped, .gitignore honored, huge dirs collapsed."""
    root = resolve_dir(path)
    top = build_tree(str(root), "", 0, max(1, max_depth), GitIgnore(root))
    return render_tree(top, root.name or str(root), max(1, max_entries), max(1, max_depth))
