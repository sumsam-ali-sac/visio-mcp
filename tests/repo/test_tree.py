"""Compact directory tree."""

from __future__ import annotations

from pathlib import Path

from visio_mcp.repo import tree


def test_tree_skips_noise_and_orders_dirs_first(fastapi_repo: Path):
    out = tree(fastapi_repo)
    lines = out.splitlines()
    assert lines[0] == "orders-api/"
    assert "node_modules" not in out and ".git/" not in out and "generated" not in out
    assert "  app/" in lines and "    main.py" in lines
    assert lines.index("  app/") < lines.index("  Dockerfile")  # dirs before files
    assert ".github/" in out


def test_tree_collapses_huge_dirs_and_truncates(tmp_path: Path, write):
    root = tmp_path / "t"
    for i in range(150):
        write(root, f"data/f{i:03}.txt")
    for i in range(30):
        write(root, f"d{i:02}/sub/file.py")
    out = tree(root, max_entries=40)
    assert "… 142 more files" in tree(root, max_entries=400) or "more files" in tree(root, max_entries=400)
    assert len(out.splitlines()) <= 42
    deep = tmp_path / "deep"
    write(deep, "a/b/c/d/e/f.txt")
    out = tree(deep, max_depth=2)
    assert "f.txt" not in out and "b/ …" in out
