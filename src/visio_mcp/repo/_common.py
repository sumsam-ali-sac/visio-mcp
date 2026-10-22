"""Shared helpers: ignore rules, directory walking, path handling and a tolerant YAML subset parser."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

MAX_FILES = 100_000
TEXT_LIMIT = 262_144


def is_ignored_dir(name: str) -> bool:
    return name in IGNORE_DIRS or name.endswith(".egg-info")


def read_text(path: Path | str, limit: int = TEXT_LIMIT) -> str:
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit)
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- paths


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


# --------------------------------------------------------------------------- gitignore


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


# --------------------------------------------------------------------------- walking


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


# --------------------------------------------------------------------------- tolerant YAML


def _strip_comment(s: str) -> str:
    q: str | None = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            if i == 0 or s[i - 1] in " :[{,-":
                q = ch
        elif ch == "#" and (i == 0 or s[i - 1] == " "):
            return s[:i].rstrip()
    return s


_BLOCK_RE = re.compile(r"(?:^|:\s+|^-\s+)[|>][+-]?\d*$")
_KEY_RE = re.compile(r"""^(?P<k>"[^"]*"|'[^']*'|[^:\s'"\[\{#-][^:]*?|-[^:\s][^:]*?)\s*:(?:\s+(?P<v>.*))?$""")


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    raw = text.expandtabs(2).splitlines()
    out: list[tuple[int, str]] = []
    i = 0
    while i < len(raw):
        line = raw[i]
        i += 1
        s = line.strip()
        if not s or s.startswith(("#", "%")) or s in ("---", "..."):
            continue
        ind = len(line) - len(line.lstrip(" "))
        content = _strip_comment(s)
        m = _BLOCK_RE.search(content)
        if m:
            block: list[str] = []
            while i < len(raw):
                nxt = raw[i]
                if not nxt.strip():
                    i += 1
                    continue
                if len(nxt) - len(nxt.lstrip(" ")) <= ind:
                    break
                block.append(nxt.strip())
                i += 1
            pre = re.match(r"(:\s+|-\s+)?", m.group(0)).group(0)  # type: ignore[union-attr]
            content = content[: m.start()] + pre + json.dumps(" ".join(block)[:600])
        out.append((ind, content))
    return out


def _split_flow(s: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    q: str | None = None
    cur: list[str] = []
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        parts.append(tail)
    return parts


def _scalar(v: str) -> Any:
    v = v.strip()
    if v in ("", "~", "null"):
        return None
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        if v[0] == '"':
            try:
                return json.loads(v)
            except ValueError:
                pass
        return v[1:-1]
    if v[0] == "[" and v[-1] == "]":
        inner = v[1:-1].strip()
        return [_scalar(x) for x in _split_flow(inner)] if inner else []
    if v[0] == "{" and v[-1] == "}":
        d: dict[str, Any] = {}
        for part in _split_flow(v[1:-1]):
            k, sep, val = part.partition(":")
            if sep:
                d[k.strip().strip("\"'")] = _scalar(val)
        return d
    return v


def _is_kv(s: str) -> bool:
    return _KEY_RE.match(s) is not None


def _parse(lines: list[tuple[int, str]], i: int) -> tuple[Any, int]:
    ind, content = lines[i]
    if content.startswith("- ") or content == "-":
        return _parse_list(lines, i, ind)
    return _parse_map(lines, i, ind)


def _parse_list(lines: list[tuple[int, str]], i: int, ind: int) -> tuple[list[Any], int]:
    res: list[Any] = []
    while i < len(lines) and lines[i][0] == ind and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
        content = lines[i][1]
        rest = content[1:].lstrip()
        if not rest:
            i += 1
            if i < len(lines) and lines[i][0] > ind:
                v, i = _parse(lines, i)
                res.append(v)
            else:
                res.append(None)
        elif _is_kv(rest):
            offset = len(content) - len(rest)
            lines[i] = (ind + offset, rest)
            v, i = _parse_map(lines, i, ind + offset)
            res.append(v)
        elif rest.startswith("- "):
            offset = len(content) - len(rest)
            lines[i] = (ind + offset, rest)
            v, i = _parse_list(lines, i, ind + offset)
            res.append(v)
        else:
            res.append(_scalar(rest))
            i += 1
    return res, i


def _parse_map(lines: list[tuple[int, str]], i: int, ind: int) -> tuple[dict[str, Any], int]:
    res: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] >= ind:
        lind, content = lines[i]
        if lind > ind or content.startswith("- "):
            if content.startswith("- ") and lind == ind:
                break
            i += 1
            continue
        m = _KEY_RE.match(content)
        i += 1
        if not m:
            continue
        key = m.group("k").strip().strip("\"'")
        rest = (m.group("v") or "").strip()
        if not rest:
            if i < len(lines) and (
                lines[i][0] > ind or (lines[i][0] == ind and lines[i][1].startswith("- "))
            ):
                v, i = _parse(lines, i)
            else:
                v = None
        else:
            v = _scalar(rest)
        res[key] = v
    return res, i


def parse_yaml(text: str) -> Any:
    """Parse the common subset of YAML (maps, lists, scalars, flow collections, block scalars).

    Tolerant: returns {} on anything it cannot make sense of.
    """
    try:
        lines = _yaml_lines(text)
        if not lines:
            return {}
        v, _ = _parse(lines, 0)
        return v
    except Exception:  # noqa: BLE001 - tolerant by design
        return {}


def yaml_docs(text: str) -> list[Any]:
    docs = re.split(r"^---[ \t]*$", text, flags=re.M)
    return [d for d in (parse_yaml(p) for p in docs if p.strip()) if d]


def as_list(v: Any) -> list[Any]:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def as_str_list(v: Any) -> list[str]:
    if isinstance(v, dict):
        return [str(k) for k in v]
    return [str(x) for x in as_list(v) if x is not None and not isinstance(x, (dict, list))]


def short(s: str, n: int = 24) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"
