"""`visio-ai icons`: install, remove or list the official Azure / AWS / Google Cloud icon packs."""

from __future__ import annotations

from typing import Any

from rich.text import Text

from visio_mcp import icons
from visio_mcp.cli import ui


def run(args: Any) -> int:
    provider = None if args.provider == "all" else args.provider
    if args.action == "install":
        with ui.spinner("Fetching official cloud icons…") as status:
            done = icons.install(provider, args.source, progress=lambda m: status.update(Text(m, style="muted")))
        for p, n in done.items():
            ui.ok(f"{icons.PROVIDER_NAMES[p]}: {n} icons installed")
        for p in (icons.PROVIDERS if provider is None else (provider,)):
            if p not in done:
                ui.warn(f"{icons.PROVIDER_NAMES[p]}: not installed (visio-ai icons install {p} --from PATH)")
    elif args.action == "remove":
        gone = icons.remove(provider)
        ui.ok("Removed " + (", ".join(icons.PROVIDER_NAMES[p] for p in gone) or "nothing (no packs installed)"))
        return 0
    _print_status()
    return 0


def _print_status() -> None:
    status = icons.status()
    t = ui.table("Provider", "Icons", "Source", "Folder")
    for p, st in status.items():
        t.add_row(Text(icons.PROVIDER_NAMES[p], style="key"),
                  Text(str(st["count"]) if st["count"] else "—", style="good" if st["count"] else "warn"),
                  Text(st["source"] or "not installed", style="muted"), Text(st["path"], style="muted"))
    ui.console.print(t)
    if not all(st["count"] for st in status.values()):
        ui.hint("Install the official icons: visio-ai icons install  (or: --from the vendor zip you downloaded)")
