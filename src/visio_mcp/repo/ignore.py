"""What to skip while looking at a repo: built-in ignore lists and a small .gitignore matcher."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from .text import read_text


IGNORE_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "bin",
        "obj", "target", ".next", ".nuxt", "coverage", ".idea", ".vs", ".vscode", "vendor", ".tox",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", ".gradle", ".terraform", ".serverless", "cdk.out",
        ".angular", ".cache", ".parcel-cache", ".turbo", "site-packages", "bower_components",
        ".dart_tool", "Pods", "DerivedData", ".aws-sam", ".eggs", "htmlcov", ".nyc_output", ".svelte-kit",
        ".output", ".expo", ".direnv", ".terragrunt-cache",
    }
)

NOISE_FILES = frozenset(
    {".DS_Store", "Thumbs.db", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
     "uv.lock", "Cargo.lock", "composer.lock", "Gemfile.lock", "go.sum", "npm-shrinkwrap.json"}
)

NOISE_SUFFIXES = (".pyc", ".pyo", ".min.js", ".min.css", ".map", ".class", ".o", ".so", ".dll", ".exe")


def is_ignored_dir(name: str) -> bool:
    return name in IGNORE_DIRS or name.endswith(".egg-info")


class GitIgnore:
    """Very small .gitignore matcher: simple names, globs, trailing-slash dirs, anchored paths."""

    def __init__(self, root: Path | None = None):
        self.rules: list[tuple[str, bool, bool]] = []
        if root is None:
            return
        text = read_text(root / ".gitignore", 65536)
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", "!")):
                continue
            dir_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = line.startswith("/") or "/" in line
            line = line.lstrip("/")
            if line.startswith("**/"):
                line = line[3:]
                anchored = "/" in line
            if not line or line in ("*", "**"):
                continue
            self.rules.append((line, dir_only, anchored))

    def ignored(self, rel: str, name: str, is_dir: bool) -> bool:
        for pat, dir_only, anchored in self.rules:
            if dir_only and not is_dir:
                continue
            if anchored:
                if fnmatch.fnmatchcase(rel, pat):
                    return True
            elif fnmatch.fnmatchcase(name, pat):
                return True
        return False
