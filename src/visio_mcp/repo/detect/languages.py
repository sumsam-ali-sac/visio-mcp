"""Language detection from file extensions: tables, test-path heuristic and the language profile."""

from __future__ import annotations

from collections import Counter


LANG = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".cs": "C#", ".java": "Java",
    ".kt": "Kotlin", ".kts": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".scala": "Scala",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell", ".sql": "SQL", ".html": "HTML", ".css": "CSS",
    ".scss": "CSS", ".vue": "Vue", ".svelte": "Svelte", ".tf": "HCL", ".bicep": "Bicep", ".dart": "Dart",
    ".ex": "Elixir", ".exs": "Elixir", ".fs": "F#", ".vb": "VB.NET", ".lua": "Lua", ".r": "R",
}

NON_PRIMARY = {"HTML", "CSS", "SQL", "Shell", "PowerShell", "HCL", "Bicep"}

SAMPLE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cs", ".java", ".kt", ".go", ".rs", ".rb", ".php"}

TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "mocks", "__mocks__", "fixtures", "examples",
               "docs", "testdata", "samples"}


def is_test_path(rel: str) -> bool:
    parts = rel.lower().split("/")
    if any(p in TEST_PARTS for p in parts[:-1]):
        return True
    n = parts[-1]
    return ".test." in n or ".spec." in n or n.startswith("test_") or n.endswith(("_test.go", "_test.py", "tests.cs"))


def language_profile(langs: Counter[str], code_bytes: int) -> tuple[dict[str, int], int]:
    """Languages by file count (most first) and a rough lines-of-code estimate."""
    return dict(sorted(langs.items(), key=lambda kv: (-kv[1], kv[0]))), code_bytes // 36


def primary_language(languages: dict[str, int]) -> str:
    return next((l for l in languages if l not in NON_PRIMARY), "")
