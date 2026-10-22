"""Sandboxed read-only file access."""

from __future__ import annotations

from pathlib import Path

import pytest

from visio_mcp.repo import RepoFS


def test_repofs_single_root_read_list_find(fastapi_repo: Path):
    fs = RepoFS([fastapi_repo])
    listing = fs.list_dir(".")
    assert "app/" in listing and "node_modules" not in listing
    assert "main.py" in fs.list_dir("app")
    text = fs.read_file("app/main.py")
    assert "1: from fastapi import FastAPI" in text
    part = fs.read_file("docker-compose.yml", start_line=3, max_lines=2)
    assert "more lines" in part and "lines 3-4" in part
    found = fs.find_files("**/*.py")
    assert "app/main.py" in found and "generated" not in found and "node_modules" not in found
    assert "Dockerfile" in fs.find_files("Dockerfile")


def test_repofs_rejects_traversal_and_symlink_escape(tmp_path: Path, fastapi_repo: Path, write):
    secret = write(tmp_path, "outside.txt", "top secret")
    fs = RepoFS([fastapi_repo])
    for bad in ("../outside.txt", "app/../../outside.txt", "/etc/passwd", str(secret), "C:\\Windows\\win.ini", "~/x"):
        with pytest.raises(ValueError):
            fs.read_file(bad)
    with pytest.raises(ValueError):
        fs.list_dir("..")
    (fastapi_repo / "link.txt").symlink_to(secret)
    (fastapi_repo / "linkdir").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        fs.read_file("link.txt")
    with pytest.raises(ValueError, match="escapes"):
        fs.list_dir("linkdir")
    assert "link.txt" not in fs.find_files("*.txt")  # symlinks are not followed in walks
    assert "top secret" not in fs.search("secret")


def test_repofs_multi_root_paths(workspace: Path):
    fs = RepoFS([workspace / "orders-api", workspace / "storefront"])
    assert fs.list_dir(".").splitlines() == ["orders-api/", "storefront/"]
    assert "from fastapi" in fs.read_file("orders-api/app/main.py")
    assert "next" in fs.read_file("storefront/package.json")
    with pytest.raises(ValueError, match="Unknown repository"):
        fs.read_file("nope/x")
    with pytest.raises(ValueError):
        fs.read_file("orders-api/../storefront/package.json")
    hits = fs.search("FastAPI", glob="*.py")
    assert hits.startswith("orders-api/app/main.py:1:")


def test_repofs_refuses_binary_huge_and_keys(tmp_path: Path, write):
    root = tmp_path / "r"
    write(root, "ok.txt", "hello")
    (root / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    (root / "image.png").write_bytes(b"\x89PNG")
    (root / "huge.log").write_text("x" * 1_200_000)
    write(root, "server.pem", "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----")
    fs = RepoFS([root])
    for name in ("blob.bin", "image.png", "huge.log", "server.pem"):
        with pytest.raises(ValueError):
            fs.read_file(name)
    with pytest.raises(FileNotFoundError):
        fs.read_file("missing.txt")
    with pytest.raises(ValueError, match="directory"):
        fs.read_file(".")


def test_repofs_redacts_on_read_and_search(tmp_path: Path, write):
    root = tmp_path / "r"
    write(root, "settings.py", 'SECRET_KEY = "djangoinsecurekey12345"\nDEBUG = True\n')
    write(root, ".env", "API_URL=http://svc\nSTRIPE_KEY=sk_live_abcdefghijklmnop1234\n")
    write(root, ".env.example", "API_URL=http://svc\n")
    fs = RepoFS([root])
    assert "djangoinsecurekey12345" not in fs.read_file("settings.py")
    assert "DEBUG = True" in fs.read_file("settings.py")
    env = fs.read_file(".env")
    assert "STRIPE_KEY=***REDACTED***" in env and "sk_live" not in env and "http://svc" not in env
    assert "http://svc" in fs.read_file(".env.example")
    hits = fs.search("KEY")
    assert "djangoinsecurekey12345" not in hits and "sk_live" not in hits
    assert "settings.py:1:" in hits


def test_repofs_search_options(fastapi_repo: Path):
    fs = RepoFS([fastapi_repo])
    out = fs.search(r"class\s+Order", glob="*.py")
    assert out == "app/models.py:1: class Order: ..."
    assert fs.search("fastapi").count("\n") >= 1  # lowercase pattern is case-insensitive
    assert fs.search("zzz-not-there").startswith("No matches")
    many = fs.search(".", max_hits=3)
    assert len([l for l in many.splitlines() if ":" in l]) >= 3 and "stopped at" in many
    with pytest.raises(ValueError, match="Invalid regex"):
        fs.search("(")
    assert "node_modules" not in fs.search("x")
