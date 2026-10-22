"""Read-only, sandboxed file access for the AI agent, with secret redaction."""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from ._common import GitIgnore, is_ignored_dir
from .digest import TreeNode, build_tree, render_tree

MASK = "***REDACTED***"

# --------------------------------------------------------------------------- redaction

_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)
_TOKEN_FORMATS = re.compile(
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
    r"|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b"
    r"|\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b|\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"
    r"|\bxox[abprs]-[A-Za-z0-9\-]{10,}\b|\bAIza[0-9A-Za-z_\-]{35}\b"
    r"|\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b"
    r"|\bglpat-[A-Za-z0-9_\-]{20,}\b|\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"
)
_URL_CREDS = re.compile(r"(://[^/\s:@\"']+):([^@\s\"'/]+)@")
_CONN_KV = re.compile(
    r"(?i)\b(password|pwd|accountkey|sharedaccesskey|sharedaccesssignature|secret|client_?secret|apikey|api_key)\s*=\s*"
    r"([^;\"'\s][^;\"'\n]*)"
)
_SECRET_NAME = (
    r"password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|client[_-]?secret|"
    r"credential|connection[_-]?string|conn[_-]?str|connectionstring|dsn|authorization|sas[_-]?token|signing[_-]?key|"
    r"encryption[_-]?key|master[_-]?key|account[_-]?key"
)
_ASSIGN = re.compile(
    r"(?P<k>[\w.\-]*(?:" + _SECRET_NAME + r")[\w.\-]*)(?P<sep>[\"']?\s*[:=]\s*)"
    r"(?P<v>\"[^\"\n]*\"|'[^'\n]*'|[^\s,;#\"'\n][^\s,;#\n]*)",
    re.I,
)
_REFERENCE_HINTS = (
    "${", "$(", "{{", "<", "%", "os.environ", "process.env", "getenv", "var.", "secrets.", "self.", "settings.",
    "config.", "env(", "environ", "keyvault", "@microsoft.keyvault", "!ref", "!sub", "!getatt", "ref:", "parameters(",
    "secretkeyref", "fn::", "args.", "params.", "props.", "input(", "getpass", "kwargs",
)
_SAFE_WORDS = {"true", "false", "none", "null", "nil", "str", "string", "int", "bool", "required", "optional",
               "secret", "token", "password", "undefined", "changeme", "xxx", "x", "yes", "no", "env", "field",
               "secretstr", "text", "any", "dict", "list", "bytes", "false,", "true,"}


def _assign_repl(m: re.Match[str]) -> str:
    raw = m.group("v")
    val = raw.strip("\"'")
    low = val.lower()
    if (
        len(val) < 4
        or low in _SAFE_WORDS
        or val.isdigit()
        or any(h in low for h in _REFERENCE_HINTS)
        or val.endswith(("(", "[", "{"))
        or re.fullmatch(r"[A-Za-z_][\w.]*\(.*", val)  # function call, e.g. Field(...)
        or re.fullmatch(r"[A-Z_][A-Z0-9_]*", val)  # SOME_CONSTANT_NAME (a reference, not a value)
        or val.startswith(("http://", "https://")) and "@" not in val
    ):
        return m.group(0)
    quote = raw[0] if raw[0] in "\"'" else ""
    return f"{m.group('k')}{m.group('sep')}{quote}{MASK}{quote}"


def redact(text: str, mask_all_values: bool = False) -> str:
    """Mask private keys, well-known token formats, URL credentials and secret-looking assignments."""
    if mask_all_values:  # .env style files: keep names, hide every value
        out = []
        for line in text.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                out.append(f"{k}={MASK}" if v.strip() else line)
            else:
                out.append(line)
        return "\n".join(out)
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _TOKEN_FORMATS.sub(MASK, text)
    text = _URL_CREDS.sub(lambda m: f"{m.group(1)}:{MASK}@", text)
    text = _CONN_KV.sub(lambda m: f"{m.group(1)}={MASK}" if m.group(2).lower() not in _SAFE_WORDS else m.group(0), text)
    text = _ASSIGN.sub(_assign_repl, text)
    return text


# --------------------------------------------------------------------------- sandbox

_MAX_READ_BYTES = 1_000_000
_MAX_SEARCH_BYTES = 512_000
_MAX_SEARCH_FILES = 6000
_BLOCKED_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".kdbx", ".ppk")
_BLOCKED_NAMES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc", ".htpasswd", "credentials")
_BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".pdf", ".zip", ".gz", ".tar", ".tgz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".war", ".pyc", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".mov", ".avi", ".wasm", ".bin", ".dat", ".db", ".sqlite", ".vsdx", ".docx", ".xlsx", ".pptx",
    ".svgz", ".lock",
}


class RepoFSError(ValueError):
    """Raised for refused paths and unreadable files; the message is safe to show to the AI."""


def _is_dot_env(name: str) -> bool:
    low = name.lower()
    return low == ".env" or (low.startswith(".env.") and not low.endswith((".example", ".sample", ".template", ".dist")))


class RepoFS:
    """Read-only, sandboxed file access over one or more repo roots.

    Paths are plain relative ('src/app.py') with one root, or 'repoName/src/app.py' with several.
    Anything that would leave the roots (.., absolute paths, escaping symlinks) raises ValueError.
    """

    def __init__(self, roots: list[Path]):
        if not roots:
            raise ValueError("RepoFS needs at least one root")
        self._roots: dict[str, Path] = {}
        for r in roots:
            p = Path(r).expanduser().resolve()
            if not p.is_dir():
                raise NotADirectoryError(f"Not a folder: {p}")
            name = p.name or "root"
            base, i = name, 2
            while name in self._roots:
                name = f"{base}-{i}"
                i += 1
            self._roots[name] = p
        self._multi = len(self._roots) > 1
        self._ignores = {n: GitIgnore(p) for n, p in self._roots.items()}

    @property
    def roots(self) -> dict[str, Path]:
        return dict(self._roots)

    # -- path handling

    def _split(self, rel: str) -> tuple[str, str]:
        rel = (rel or ".").strip().replace("\\", "/")
        if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or rel.startswith("~"):
            raise ValueError(f"Absolute paths are not allowed: {rel!r}. Use a path relative to the repository.")
        parts = [p for p in rel.split("/") if p not in ("", ".")]
        if ".." in parts:
            raise ValueError(f"Path traversal is not allowed: {rel!r}")
        if not self._multi:
            return next(iter(self._roots)), "/".join(parts)
        if not parts:
            return "", ""
        if parts[0] not in self._roots:
            raise ValueError(
                f"Unknown repository {parts[0]!r}. Start paths with one of: {', '.join(self._roots)}"
            )
        return parts[0], "/".join(parts[1:])

    def _resolve(self, rel: str) -> tuple[str, Path, str]:
        root_name, sub = self._split(rel)
        if not root_name:
            raise ValueError("Give a path inside a repository, e.g. " + next(iter(self._roots)) + "/")
        root = self._roots[root_name]
        target = (root / sub) if sub else root
        real = Path(os.path.realpath(target))
        try:
            real.relative_to(root)
        except ValueError:
            raise ValueError(f"Path escapes the repository: {rel!r}") from None
        return root_name, real, sub

    def _display(self, root_name: str, sub: str) -> str:
        return f"{root_name}/{sub}" if self._multi and sub else (root_name if self._multi else (sub or "."))

    def _ignored(self, root_name: str, sub: str, is_dir: bool) -> bool:
        parts = sub.split("/") if sub else []
        if any(is_ignored_dir(p) for p in parts[: len(parts) - (0 if is_dir else 1)]):
            return True
        return bool(sub) and self._ignores[root_name].ignored(sub, parts[-1], is_dir)

    # -- listing

    def list_dir(self, rel: str = ".", depth: int = 1) -> str:
        root_name, sub = self._split(rel)
        if not root_name:
            return "\n".join(f"{n}/" for n in self._roots)
        _, real, sub = self._resolve(rel)
        if not real.is_dir():
            raise RepoFSError(f"Not a directory: {rel}") if real.exists() else FileNotFoundError(f"No such directory: {rel}")
        depth = max(1, min(int(depth), 5))
        top = build_tree(str(real), sub, 0, depth, self._ignores[root_name])
        title = self._display(root_name, sub)
        return render_tree(top, title, 300, depth)

    # -- reading

    def read_file(self, rel: str, start_line: int = 1, max_lines: int = 400) -> str:
        root_name, real, sub = self._resolve(rel)
        name = real.name
        if not real.exists():
            raise FileNotFoundError(f"No such file: {rel}")
        if real.is_dir():
            raise RepoFSError(f"{rel} is a directory; use list_dir")
        low = name.lower()
        if low.endswith(_BLOCKED_SUFFIXES) or low in _BLOCKED_NAMES or low.startswith(("id_rsa", "id_ed25519")):
            raise RepoFSError(f"Refusing to read credential file: {rel}")
        if ".git" in sub.split("/"):
            raise RepoFSError("Refusing to read inside .git")
        size = real.stat().st_size
        if size > _MAX_READ_BYTES:
            raise RepoFSError(f"File too large ({size // 1024} KB); use search or read a smaller file: {rel}")
        if os.path.splitext(low)[1] in _BINARY_EXT:
            raise RepoFSError(f"Binary file, not shown: {rel}")
        with open(real, "rb") as fh:
            data = fh.read(_MAX_READ_BYTES)
        if b"\x00" in data[:8192]:
            raise RepoFSError(f"Binary file, not shown: {rel}")
        text = redact(data.decode("utf-8", errors="replace"), mask_all_values=_is_dot_env(name))
        lines = text.splitlines()
        start = max(1, int(start_line))
        count = max(1, min(int(max_lines), 2000))
        chunk = lines[start - 1: start - 1 + count]
        width = len(str(start + len(chunk)))
        body = "\n".join(
            f"{start + i:>{width}}: {ln if len(ln) <= 400 else ln[:400] + ' …'}" for i, ln in enumerate(chunk)
        )
        end = start - 1 + len(chunk)
        header = f"{self._display(root_name, sub)} (lines {start}-{end} of {len(lines)})"
        if not chunk:
            return f"{header}\n(no lines in that range)"
        if end < len(lines):
            body += f"\n… {len(lines) - end} more lines (call again with start_line={end + 1})"
        return f"{header}\n{body}"

    # -- searching

    def _iter_files(self, glob: str | None = None):
        """Yield (display_path, real_path) for text-candidate files across roots, honoring ignores."""
        patterns = self._glob_patterns(glob)
        count = 0
        for root_name, root in self._roots.items():
            gi = self._ignores[root_name]
            stack = [(str(root), "")]
            while stack:
                dpath, rel = stack.pop()
                try:
                    with os.scandir(dpath) as it:
                        entries = sorted(it, key=lambda e: e.name)
                except OSError:
                    continue
                subdirs = []
                for e in entries:
                    erel = f"{rel}/{e.name}" if rel else e.name
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if not is_ignored_dir(e.name) and not gi.ignored(erel, e.name, True):
                                subdirs.append((e.path, erel))
                        elif e.is_file(follow_symlinks=False):
                            if gi.ignored(erel, e.name, False):
                                continue
                            disp = self._display(root_name, erel)
                            if patterns and not any(fnmatch.fnmatch(disp, p) or fnmatch.fnmatch(erel, p)
                                                    or fnmatch.fnmatch(e.name, p) for p in patterns):
                                continue
                            count += 1
                            if count > _MAX_SEARCH_FILES * 4:
                                return
                            yield disp, e.path, e.name
                    except OSError:
                        continue
                stack.extend(reversed(subdirs))

    @staticmethod
    def _glob_patterns(glob: str | None) -> list[str]:
        if not glob:
            return []
        g = glob.strip().replace("\\", "/")
        pats = [g]
        if g.startswith("**/"):
            pats.append(g[3:])
        if "/" not in g:
            pats.append("*/" + g)
        return pats

    def search(self, pattern: str, glob: str | None = None, max_hits: int = 60) -> str:
        flags = re.IGNORECASE if pattern == pattern.lower() else 0
        try:
            rx = re.compile(pattern, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex {pattern!r}: {e}") from None
        max_hits = max(1, min(int(max_hits), 500))
        hits: list[str] = []
        scanned = 0
        truncated = False
        for disp, real, name in self._iter_files(glob):
            low = name.lower()
            if os.path.splitext(low)[1] in _BINARY_EXT or low.endswith(_BLOCKED_SUFFIXES) or low in _BLOCKED_NAMES:
                continue
            try:
                size = os.stat(real).st_size
                if size > _MAX_SEARCH_BYTES or size == 0:
                    continue
                with open(real, "rb") as fh:
                    data = fh.read(_MAX_SEARCH_BYTES)
            except OSError:
                continue
            if b"\x00" in data[:4096]:
                continue
            scanned += 1
            if scanned > _MAX_SEARCH_FILES:
                truncated = True
                break
            mask_all = _is_dot_env(name)
            text = data.decode("utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    shown = redact(line, mask_all_values=mask_all).strip()
                    hits.append(f"{disp}:{i}: {shown[:200]}{' …' if len(shown) > 200 else ''}")
                    if len(hits) >= max_hits:
                        truncated = True
                        break
            if len(hits) >= max_hits:
                break
        if not hits:
            return f"No matches for {pattern!r}" + (f" in files matching {glob!r}" if glob else "")
        if truncated:
            hits.append(f"… stopped at {len(hits)} hits; narrow the pattern or glob")
        return "\n".join(hits)

    def find_files(self, glob: str, max_hits: int = 200) -> str:
        if not glob or not glob.strip():
            raise ValueError("glob is required, e.g. '**/Dockerfile' or '*.tf'")
        max_hits = max(1, min(int(max_hits), 1000))
        out: list[str] = []
        for disp, _real, _name in self._iter_files(glob):
            out.append(disp)
            if len(out) > max_hits:
                break
        if not out:
            return f"No files match {glob!r}"
        if len(out) > max_hits:
            return "\n".join(out[:max_hits]) + f"\n… more than {max_hits} matches; narrow the glob"
        return "\n".join(out)
