"""The refine loop: describe a change in plain words or use a /slash command, and redraw."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from rich.syntax import Syntax
from rich.text import Text

from visio_mcp import lint, style
from visio_mcp.cli import prompts, ui
from visio_mcp.cli.studio.drawing import draw, result_panel
from visio_mcp.cli.studio.session import Session
from visio_mcp.output.drawer import Drawer, open_file, slug
from visio_mcp.spec import DiagramSpec

LAYOUTS = ["flowchart-lr", "flowchart-tb", "swimlane-lr", "swimlane-tb", "tree-tb", "tree-lr",
           "radial", "circular", "grid"]
HELP = [
    ("<describe a change>", "e.g. “group the databases”, “add the Stripe webhook”, “make it left to right”"),
    ("/open", "open the diagram (Visio, or the browser preview)"),
    ("/theme [name]", "switch theme: " + ", ".join(style.THEMES)),
    ("/layout [name]", "re-layout: " + ", ".join(LAYOUTS[:5]) + "…"),
    ("/export png|svg|pdf|html", "export the current diagram"),
    ("/spec", "show the diagram spec (JSON)"),
    ("/save [file]", "save the spec to a JSON file"),
    ("/lint", "show rule findings"),
    ("/undo", "go back to the previous version"),
    ("/new", "draw another diagram of the same code"),
    ("/quit", "leave"),
]


def pick_theme(spec: DiagramSpec) -> str:
    """Ask for a theme, recommending the one the diagram would get automatically."""
    auto = lint.normalize(spec)[0].theme
    choices = [prompts.choice(f"★ {auto}", auto, style.THEMES[auto].description + "  (recommended)")]
    choices += [prompts.choice(f"  {t.name}", t.name, t.description) for t in style.THEMES.values() if t.name != auto]
    return prompts.select("Theme", choices)


def apply(drawer: Drawer, s: Session, spec: DiagramSpec) -> None:
    """Make spec current (keeping the old one for /undo) and redraw."""
    if s.spec is not None:
        s.history.append(s.spec)
    s.spec = spec
    ui.console.print(result_panel(draw(drawer, s)))


def refine_loop(drawer: Drawer, s: Session) -> str:
    """Read edits until the user quits ("quit") or wants another diagram ("new")."""
    ui.console.print()
    ui.hint("Refine it: describe a change in plain words, or type /help.")
    while True:
        ui.console.print()
        try:
            line = prompts.text("✎", instruction="").strip()
        except prompts.Cancelled:
            return "quit"
        if not line:
            continue
        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            result = handle_command(cmd.lower(), arg.strip(), drawer, s)
            if result:
                return result
            continue
        if s.agent is None:
            ui.warn("Plain-language edits need an AI provider. Use /theme, /layout, or set one up with `visio-ai setup`.")
            continue
        try:
            with ui.spinner("Updating the diagram…"):
                spec = s.agent.refine(line)
        except KeyboardInterrupt:
            ui.warn("Stopped.")
            continue
        except Exception as e:
            ui.fail(str(getattr(e, "message", e)), getattr(e, "hint", ""))
            continue
        apply(drawer, s, spec)


# --- slash commands: each takes (arg, drawer, session) and may return "quit" or "new" ----------


def _help(arg: str, drawer: Drawer, s: Session) -> None:
    t = ui.table("Command", "What it does")
    for k, v in HELP:
        t.add_row(Text(k, style="key"), Text(v, style="muted"))
    ui.console.print(t)


def _open(arg: str, drawer: Drawer, s: Session) -> None:
    out = s.output
    if out and drawer.target == "visio":
        if drawer.live:
            ui.ok("It's open in Visio.")
        else:
            open_file(out.vsdx)
    elif out:
        open_file(out.previews.get("html") or out.vsdx)


def _theme(arg: str, drawer: Drawer, s: Session) -> None:
    assert s.spec is not None
    name = arg or pick_theme(s.spec)
    try:
        style.get_theme(name)
    except ValueError as e:
        ui.fail(str(e))
        return
    s.theme = name
    apply(drawer, s, s.spec.model_copy(update={"theme": name}))


def _layout(arg: str, drawer: Drawer, s: Session) -> None:
    assert s.spec is not None
    name = arg or prompts.select("Layout", LAYOUTS)
    if name not in [*LAYOUTS, "auto"]:
        ui.fail(f"unknown layout {name!r}", "one of: " + ", ".join(LAYOUTS))
        return
    apply(drawer, s, s.spec.model_copy(update={"layout": name}))


def _export(arg: str, drawer: Drawer, s: Session) -> None:
    try:
        ui.ok(str(drawer.export((arg or "pdf").lower().lstrip("."))))
    except Exception as e:
        ui.fail(str(e))


def _spec(arg: str, drawer: Drawer, s: Session) -> None:
    assert s.spec is not None
    ui.console.print(Syntax(s.spec.model_dump_json(indent=2, exclude_defaults=True), "json",
                            theme="ansi_dark", word_wrap=True))


def _save(arg: str, drawer: Drawer, s: Session) -> None:
    assert s.spec is not None
    if arg:
        target = Path(arg).expanduser()
    elif s.output and s.output.vsdx:
        target = s.output.vsdx.with_suffix(".json")
    else:
        target = Path(slug(s.spec.title) + ".json")
    target.write_text(s.spec.model_dump_json(indent=2, exclude_defaults=True), encoding="utf-8")
    ui.ok(f"Saved {target}  ·  redraw it any time with: visio-ai render \"{target}\"")


def _lint(arg: str, drawer: Drawer, s: Session) -> None:
    assert s.spec is not None
    norm, notes = lint.normalize(s.spec)
    for f in notes + lint.lint(norm) or ["No findings — it follows the ground rules."]:
        ui.info(f)


def _undo(arg: str, drawer: Drawer, s: Session) -> None:
    if not s.history:
        ui.warn("Nothing to undo.")
        return
    s.spec = s.history.pop()
    ui.console.print(result_panel(draw(drawer, s)))


COMMANDS: dict[str, Callable[[str, Drawer, Session], Any]] = {
    "help": _help, "h": _help, "?": _help, "open": _open, "theme": _theme, "layout": _layout,
    "export": _export, "spec": _spec, "save": _save, "lint": _lint, "undo": _undo,
}


def handle_command(cmd: str, arg: str, drawer: Drawer, s: Session) -> str | None:
    """Run one slash command; returns "quit" or "new" when the loop should end."""
    if cmd in ("q", "quit", "exit"):
        return "quit"
    if cmd == "new":
        return "new"
    handler = COMMANDS.get(cmd)
    if handler is None:
        ui.warn(f"Unknown command /{cmd}. Type /help.")
        return None
    handler(arg, drawer, s)
    return None
