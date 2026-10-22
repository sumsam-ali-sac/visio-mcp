"""The studio's four steps: where is the code, what to draw, how to explore, draw and refine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text

from visio_mcp import icons
from visio_mcp.ai import config as aiconfig
from visio_mcp.cli import coding_apps, prompts, ui
from visio_mcp.cli.commands.handoff import launch
from visio_mcp.cli.studio.drawing import draw, result_panel, spec_tree
from visio_mcp.cli.studio.explore import explore, repo_table, scan_paths
from visio_mcp.cli.studio.refine import pick_theme, refine_loop
from visio_mcp.cli.studio.session import Session, provider_label, suggested_type, type_info
from visio_mcp.cli.studio.setup_wizard import setup_wizard
from visio_mcp.output.drawer import Drawer, default_out_dir, open_file
from visio_mcp.spec import DiagramSpec

_icons_offered: set[str] = set()


def studio(args: Any) -> int:
    """Run the interactive studio; returns an exit code."""
    ui.banner()
    cfg = aiconfig.load_config()
    drawer = _make_drawer(args, cfg)
    _status_line(drawer, cfg)

    s = Session(theme=getattr(args, "theme", None) or cfg.theme or "auto")
    if getattr(args, "out", None):
        s.out_dir = Path(args.out).expanduser()
    elif cfg.out_dir:
        s.out_dir = Path(cfg.out_dir).expanduser()

    try:
        _choose_repos(args, cfg, s)
        while True:
            ui.step(2, 4, "What should we draw?")
            s.diagram_type = getattr(args, "type", None) or _ask_type(s)
            s.focus = prompts.text("Anything to focus on?", instruction="(optional — enter to skip)",
                                   default=getattr(args, "focus", "") or "").strip()

            ui.step(3, 4, "Explore the code")
            how = _ask_engine(cfg)
            if how == "handoff":
                return _handoff(s)
            if how == "setup":
                cfg = setup_wizard(cfg)
                how = "ai" if cfg.provider else "offline"
            s.spec = explore(how, cfg, s)
            if s.spec is None:
                continue
            ui.console.print(ui.panel(spec_tree(s.spec), title="Draft"))
            _offer_icons(s.spec)

            ui.step(4, 4, "Draw")
            if s.theme == "auto" and not getattr(args, "theme", None):
                s.theme = pick_theme(s.spec)
            out = draw(drawer, s)
            ui.console.print(result_panel(out))
            if drawer.target == "native" and out.previews.get("html") and not getattr(args, "no_open", False):
                open_file(out.previews["html"])
            if refine_loop(drawer, s) != "new":
                break
    except (prompts.Cancelled, KeyboardInterrupt):
        ui.console.print()
        ui.hint("Bye — your diagrams are in " + str(s.out_dir or default_out_dir()))
        return 130
    finally:
        if not drawer.live:
            drawer.close()
    ui.hint("Saved in " + str(s.out_dir or default_out_dir()))
    return 0


def _choose_repos(args: Any, cfg: Any, s: Session) -> None:
    ui.step(1, 4, "Where is the code?")
    raw = getattr(args, "path", None) or _ask_path(cfg)
    while True:
        try:
            s.repos = scan_paths(raw)
            break
        except (FileNotFoundError, NotADirectoryError) as e:
            ui.fail(str(e).strip("'\""), "Paste a folder path, e.g. C:\\code\\my-app or ~/code")
            raw = _ask_path(cfg)
    _remember_path(cfg, raw)
    ui.console.print(repo_table(s.repos))
    if len(s.repos) > 1:
        picked = prompts.checkbox("Which repositories belong in the diagram?",
                                  [prompts.choice(r.name, r, r.summary, None) for r in s.repos])
        s.repos = picked or s.repos


def _make_drawer(args: Any, cfg: Any) -> Drawer:
    target = "native" if getattr(args, "native", False) else "auto"
    live = not getattr(args, "no_live", False) and getattr(cfg, "live", True)
    attach = getattr(args, "attach", False) or getattr(cfg, "attach", False)
    return Drawer(target=target, live=live, attach=attach)


def _status_line(drawer: Drawer, cfg: Any) -> None:
    visio = (Text("● Visio desktop — drawing live", style="good") if drawer.target == "visio"
             else Text("● Native .vsdx (Visio not found) — previews in your browser", style="warn"))
    ai = (Text(f"● {provider_label(cfg.provider)}", style="good") if cfg.provider
          else Text("● No AI provider yet — set one up in step 3, or draw from a static scan", style="warn"))
    ui.console.print(ui.kv_table([("Output", visio), ("AI", ai)]))


def _ask_path(cfg: Any) -> str:
    recent = [p for p in getattr(cfg, "recent_paths", []) if Path(p).exists()][:5]
    if recent:
        pick = prompts.select("Choose a folder (a repo, or a folder of repos)",
                              [prompts.choice(p, p) for p in recent] + [prompts.choice("Another folder…", "")])
        if pick:
            return pick
    return prompts.path("Folder path", default=str(Path.cwd()) + ("\\" if "\\" in str(Path.cwd()) else "/"))


def _remember_path(cfg: Any, raw: str) -> None:
    p = str(Path(raw.strip().strip('"')).expanduser().resolve())
    cfg.recent_paths = [p] + [x for x in cfg.recent_paths if x != p][:7]
    try:
        aiconfig.save_config(cfg)
    except OSError:
        pass


def _ask_type(s: Session) -> str:
    best = suggested_type(s.repos)
    info = type_info()
    choices = [prompts.choice(("★ " if t == best else "  ") + t, t, info.get(t, ""))
               for t in [best, *(t for t in info if t != best)]]
    return prompts.select("Diagram type", choices, default=choices[0].value)


def _ask_engine(cfg: Any) -> str:
    choices = []
    if cfg.provider:
        choices.append(prompts.choice(f"AI agent  ·  {provider_label(cfg.provider)}", "ai",
                                      "explores the code, then drafts"))
    choices.append(prompts.choice("Set up an AI provider", "setup", "Claude, Gemini, Azure OpenAI, OpenAI or Ollama"))
    tools = coding_apps.installed_tools()
    if tools:
        choices.append(prompts.choice("Hand off to my AI coding app", "handoff", ", ".join(t.name for t in tools)))
    choices.append(prompts.choice("Quick draft without AI", "offline", "static scan of manifests, compose, IaC, CI"))
    return prompts.select("How should we explore the code?", choices)


def _handoff(s: Session) -> int:
    tools = coding_apps.installed_tools()
    tool = tools[0] if len(tools) == 1 else prompts.select("Which app?", [prompts.choice(t.name, t) for t in tools])
    return launch(tool, [r.path for r in s.repos], s.diagram_type, s.focus)


def _offer_icons(spec: DiagramSpec) -> None:
    """Cloud diagram without the provider's icon pack: offer once to install the official icons."""
    missing = [p for p in icons.missing_for([n.kind for n in spec.nodes]) if p not in _icons_offered]
    if not missing:
        return
    _icons_offered.update(missing)
    names = " and ".join(icons.PROVIDER_NAMES[p] for p in missing)
    if not prompts.confirm(f"Install the official {names} icons now? (recommended)", default=True):
        ui.hint("Later: visio-ai icons install")
        return
    for p in missing:
        try:
            with ui.spinner(f"Fetching the official {icons.PROVIDER_NAMES[p]} icons…") as status:
                n = icons.install(p, progress=lambda m: status.update(m))[p]
            ui.ok(f"{icons.PROVIDER_NAMES[p]}: {n} icons installed")
        except (RuntimeError, OSError, ValueError) as e:
            ui.warn(f"{icons.PROVIDER_NAMES[p]} icons not installed: {e}")
            if getattr(e, "hint", ""):
                ui.hint(e.hint)  # type: ignore[attr-defined]
