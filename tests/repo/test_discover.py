"""Finding repositories under a folder."""

from __future__ import annotations

from pathlib import Path

from visio_mcp.repo import discover


def test_discover_single_repo(fastapi_repo: Path):
    repos = discover(fastapi_repo)
    assert [r.name for r in repos] == ["orders-api"]


def test_discover_repo_without_git_but_manifest(tmp_path: Path, write):
    root = tmp_path / "plain"
    write(root, "pyproject.toml", '[project]\nname="x"\ndependencies=["flask"]\n')
    repos = discover(root)
    assert len(repos) == 1 and "Flask" in repos[0].frameworks


def test_discover_folder_of_repos(workspace: Path):
    repos = discover(workspace)
    assert [r.name for r in repos] == ["infra-aws", "orders-api", "storefront"]
    assert discover(workspace, max_depth=1)[0].name == "infra-aws"


def test_discover_depth_limit_and_ignored_dirs(tmp_path: Path, write):
    ws = tmp_path / "ws"
    write(ws, "a/b/c/d/package.json", "{}")  # depth 4
    write(ws, "node_modules/pkg/package.json", "{}")
    write(ws, "x/package.json", "{}")
    names = [r.path.relative_to(ws).as_posix() for r in discover(ws, max_depth=3)]
    assert names == ["x"]
    assert "a/b/c/d" in [r.path.relative_to(ws).as_posix() for r in discover(ws, max_depth=5)]
