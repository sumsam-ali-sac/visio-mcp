"""Find repositories at or below a folder and profile each one."""

from __future__ import annotations

import os
from pathlib import Path

from .detect import scan
from .ignore import is_ignored_dir
from .model import RepoInfo
from .paths import resolve_dir


ROOT_MARKERS = {
    "package.json", "pyproject.toml", "requirements.txt", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "cargo.toml", "gemfile", "composer.json", "pipfile", "setup.py", "dockerfile", "docker-compose.yml",
    "docker-compose.yaml", "compose.yml", "compose.yaml", "main.tf", "main.bicep", "serverless.yml", "cdk.json",
    "host.json",
}


def is_repo(p: Path) -> bool:
    if (p / ".git").exists():
        return True
    try:
        with os.scandir(p) as it:
            for e in it:
                low = e.name.lower()
                if e.is_file(follow_symlinks=False) and (
                    low in ROOT_MARKERS or low.endswith((".csproj", ".sln", ".fsproj", ".tf", ".bicep"))
                ):
                    return True
    except OSError:
        return False
    return False


def discover(path: str | Path, max_depth: int = 3) -> list[RepoInfo]:
    """Find and profile repositories at or below path.

    A folder that is itself a repo (has .git or a manifest) yields one RepoInfo; otherwise repos are searched
    for below it (up to max_depth levels) and returned sorted by name.
    """
    root = resolve_dir(path)
    if is_repo(root):
        return [scan(root)]
    found: list[Path] = []
    level = [root]
    for _ in range(max(1, max_depth)):
        nxt: list[Path] = []
        for d in level:
            try:
                with os.scandir(d) as it:
                    subs = sorted(
                        (e for e in it if e.is_dir(follow_symlinks=False)
                         and not is_ignored_dir(e.name) and not e.name.startswith(".")),
                        key=lambda e: e.name,
                    )
            except OSError:
                continue
            for e in subs:
                p = Path(e.path)
                if is_repo(p):
                    found.append(p)
                else:
                    nxt.append(p)
        level = nxt
        if not level or len(found) >= 200:
            break
    if not found:
        return [scan(root)]
    repos = [scan(p) for p in found[:200]]
    repos.sort(key=lambda r: (r.name.lower(), str(r.path)))
    return repos
