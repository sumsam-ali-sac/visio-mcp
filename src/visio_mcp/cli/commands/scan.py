"""`visio-ai scan`: profile repositories (table, JSON or the AI digest)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from visio_mcp import repo
from visio_mcp.cli import ui
from visio_mcp.cli.studio.explore import repo_table


def run(args: Any) -> int:
    repos = repo.discover(args.path)
    if args.json:
        ui.print_json([{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(r).items()} for r in repos])
    elif args.digest:
        ui.console.print(repo.workspace_digest(repos) if len(repos) > 1 else repo.digest(repos[0]))
    else:
        ui.console.print(repo_table(repos))
        for r in repos:
            ui.info(f"[bold]{r.name}[/]  {r.summary}")
    return 0
