"""Likely program entry points (main.py, server.ts, Program.cs, cmd/*/main.go, ...)."""

from __future__ import annotations

from ..lists import add_unique
from ..walk import FileEntry


ENTRY_NAMES = {
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "server.py", "__main__.py", "run.py",
    "index.js", "index.ts", "server.js", "server.ts", "app.js", "app.ts", "main.js", "main.ts",
    "program.cs", "startup.cs", "main.go", "main.rs", "main.java", "function_app.py", "lambda_function.py",
    "handler.py", "handler.js", "handler.ts", "main.kt",
}


def is_entry_candidate(low: str, rel: str, depth: int) -> bool:
    if low in ENTRY_NAMES and depth <= 3:
        return True
    return low.endswith("application.java") and depth <= 8 and "src/main/" in rel


def find_entrypoints(candidates: list[FileEntry], files: list[FileEntry]) -> list[str]:
    entries: list[str] = []
    for f in sorted(candidates, key=lambda f: (f.depth, f.rel)):
        add_unique(entries, f.rel)
    for f in files:
        if f.name == "main.go" and f.rel.startswith("cmd/"):
            add_unique(entries, f.rel)
        if len(entries) >= 15:
            break
    return sorted(entries, key=lambda r: (r.count("/"), r))[:15]
