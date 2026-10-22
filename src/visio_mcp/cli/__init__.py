"""visio-ai: the terminal app.

    visio-ai                      interactive studio (point at code, pick, watch it draw)
    visio-ai draw PATH            explore code and draw, no questions asked
    visio-ai render SPEC.json     draw a saved spec
    visio-ai scan PATH            profile repositories
    visio-ai setup                choose the AI provider
    visio-ai handoff PATH         let Claude Code / Gemini CLI / Codex / Copilot draw it
    visio-ai doctor               check Visio, providers and renderers
    visio-ai themes | kinds | rules TYPE | examples | mcp
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.text import Text

from visio_mcp import __version__ as VERSION

TYPES = ["architecture", "cloud", "c4-context", "c4-container", "deployment", "dataflow", "pipeline", "erd",
         "flowchart", "swimlane", "network", "state", "org", "mindmap"]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="visio-ai", add_help=False)
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="command")

    def output_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--theme", help="professional, azure, aws, gcp, c4, blueprint, dark, monochrome")
        sp.add_argument("--out", help="output folder (default: Documents/visio-mcp)")
        sp.add_argument("--native", action="store_true", help="write .vsdx without Visio")
        sp.add_argument("--no-live", action="store_true", help="draw in a hidden Visio instead of live")
        sp.add_argument("--attach", action="store_true", help="draw into the Visio window you already have open")
        sp.add_argument("--format", action="append", dest="formats", help="png, svg, pdf, html (repeatable)")
        sp.add_argument("--no-open", action="store_true", help="don't open the result")

    st = sub.add_parser("studio", add_help=False)
    st.add_argument("path", nargs="?")
    st.add_argument("--type", choices=TYPES)
    st.add_argument("--focus", default="")
    output_flags(st)

    d = sub.add_parser("draw")
    d.add_argument("path")
    d.add_argument("--type", choices=TYPES)
    d.add_argument("--focus", default="", help="what to emphasise, in plain words")
    d.add_argument("--provider", choices=["anthropic", "openai", "azure", "gemini", "ollama"])
    d.add_argument("--model")
    d.add_argument("--offline", action="store_true", help="no AI: draft from a static scan")
    d.add_argument("--save-spec", help="also save the spec JSON here")
    output_flags(d)

    r = sub.add_parser("render")
    r.add_argument("spec")
    output_flags(r)

    sc = sub.add_parser("scan")
    sc.add_argument("path")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--digest", action="store_true", help="print the AI digest")

    sub.add_parser("setup")
    h = sub.add_parser("handoff")
    h.add_argument("path")
    h.add_argument("--tool", choices=["claude", "gemini", "codex", "copilot"])
    h.add_argument("--type", choices=TYPES, default="architecture")
    h.add_argument("--focus", default="")
    sub.add_parser("doctor")
    sub.add_parser("themes")
    k = sub.add_parser("kinds")
    k.add_argument("--provider", choices=["azure", "aws", "gcp"])
    ru = sub.add_parser("rules")
    ru.add_argument("type", choices=TYPES)
    ru.add_argument("--provider", choices=["azure", "aws", "gcp"])
    ex = sub.add_parser("examples")
    output_flags(ex)
    sub.add_parser("mcp")
    return p


def main(argv: list[str] | None = None) -> int:
    from visio_mcp.cli import ui

    args = _parser().parse_args(argv)
    if args.version:
        ui.console.print(f"visio-ai {VERSION}")
        return 0
    if args.help:
        return _help()
    cmd = args.command or "studio"
    if cmd == "studio" and not ui.interactive():
        ui.fail("The studio needs an interactive terminal.", "Use `visio-ai draw PATH` in scripts and CI.")
        return 2
    try:
        return int(COMMANDS[cmd](args) or 0)
    except KeyboardInterrupt:
        ui.console.print()
        return 130
    except (FileNotFoundError, NotADirectoryError, ValueError, RuntimeError) as e:
        ui.fail(str(e).strip("'\""), getattr(e, "hint", ""))
        return 1


# --- commands ---------------------------------------------------------------------------------


def _studio(args: Any) -> int:
    from visio_mcp.cli import studio

    return studio.studio(args)


def _draw(args: Any) -> int:
    from visio_mcp.ai import config as aiconfig
    from visio_mcp.cli import studio, ui
    from visio_mcp.engine import Drawer

    ui.banner()
    cfg = aiconfig.load_config()
    s = studio.Session(theme=args.theme or cfg.theme or "auto", focus=args.focus,
                       out_dir=Path(args.out).expanduser() if args.out else None)
    s.repos = studio.scan_paths(args.path)
    ui.console.print(studio.repo_table(s.repos))
    s.diagram_type = args.type or studio.suggested_type(s.repos)
    ui.info(f"Diagram type: [accent2]{s.diagram_type}[/]")

    pc = cfg.provider
    if args.provider:
        found = {p.provider: p for p in aiconfig.detect_providers(probe_ollama=args.provider == "ollama")}
        pc = found.get(args.provider) or aiconfig.ProviderConfig(
            provider=args.provider, model=aiconfig.DEFAULT_MODELS.get(args.provider, ""))
    if pc and args.model:
        pc.model = args.model
    if args.offline or pc is None:
        if pc is None and not args.offline:
            ui.warn("No AI provider configured (run `visio-ai setup`); drafting from a static scan.")
        from visio_mcp import scanner

        s.spec = scanner.heuristic_spec(s.repos, s.diagram_type)
    else:
        from visio_mcp.ai import providers

        s.spec = studio.run_agent(providers.make_llm(pc), pc, s)
    ui.console.print(ui.panel(studio.spec_tree(s.spec), title="Draft"))
    if args.save_spec:
        Path(args.save_spec).write_text(s.spec.model_dump_json(indent=2, exclude_defaults=True), encoding="utf-8")
        ui.ok(f"Spec saved to {args.save_spec}")
    return _finish(args, s, Drawer(target="native" if args.native else "auto", live=not args.no_live,
                                   attach=args.attach))


def _render(args: Any) -> int:
    from visio_mcp.cli import studio, ui
    from visio_mcp.engine import Drawer
    from visio_mcp.spec import DiagramSpec

    path = Path(args.spec).expanduser()
    spec = DiagramSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))
    s = studio.Session(spec=spec, theme=args.theme or "auto",
                       out_dir=Path(args.out).expanduser() if args.out else path.parent)
    ui.banner()
    return _finish(args, s, Drawer(target="native" if args.native else "auto", live=not args.no_live,
                                   attach=args.attach))


def _finish(args: Any, s: Any, drawer: Any) -> int:
    from visio_mcp import engine
    from visio_mcp.cli import studio, ui

    try:
        out = studio.draw(drawer, s, args.formats)
        ui.console.print(studio.result_panel(s, out))
        if not args.no_open and drawer.target == "native":
            target = out.previews.get("html") or out.vsdx
            if target:
                engine.open_file(target)
    finally:
        if not drawer.live:
            drawer.close()
    return 0


def _scan(args: Any) -> int:
    from visio_mcp import scanner
    from visio_mcp.cli import studio, ui

    repos = scanner.discover(args.path)
    if args.json:
        studio.print_json([{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(r).items()} for r in repos])
    elif args.digest:
        ui.console.print(scanner.workspace_digest(repos) if len(repos) > 1 else scanner.digest(repos[0]))
    else:
        ui.console.print(studio.repo_table(repos))
        for r in repos:
            ui.info(f"[bold]{r.name}[/]  {r.summary}")
    return 0


def _setup(args: Any) -> int:
    from visio_mcp.ai import config as aiconfig
    from visio_mcp.cli import studio, ui

    ui.banner("Set up the AI that explores your code.")
    studio.setup_wizard(aiconfig.load_config())
    return 0


def _handoff(args: Any) -> int:
    import subprocess

    from visio_mcp import scanner
    from visio_mcp.cli import handoff, ui

    tools = handoff.installed_tools()
    if args.tool:
        tool = handoff.TOOLS[args.tool]
    elif tools:
        tool = tools[0] if len(tools) == 1 or not ui.interactive() else ui.select(
            "Which app?", [ui.choice(t.name, t) for t in tools])
    else:
        ui.fail("No AI coding app found on PATH.", "Install Claude Code, Gemini CLI, Codex or Copilot CLI.")
        return 1
    repos = scanner.discover(args.path)
    changed, argv, cwd = handoff.handoff(tool, [r.path for r in repos], args.type, args.focus)
    ui.ok(changed)
    ui.info(f"Launching {tool.name} in {cwd}")
    return subprocess.call(argv, cwd=cwd)


def _doctor(args: Any) -> int:
    import platform
    import shutil

    from visio_mcp import engine
    from visio_mcp.ai import config as aiconfig
    from visio_mcp.cli import handoff, ui

    ui.banner("Checking your setup.")
    rows: list[tuple[str, Any]] = []

    def mark(good: bool, text: str, fix: str = "") -> Text:
        return Text.assemble(("✔ " if good else "▲ ", "good" if good else "warn"), text,
                             (f"  — {fix}" if fix and not good else "", "muted"))

    rows.append(("System", f"{platform.system()} {platform.release()} · Python {platform.python_version()}"))
    has_visio = engine.visio_available()
    rows.append(("Visio desktop", mark(has_visio, "installed — diagrams draw live" if has_visio else "not found",
                                       "native .vsdx output will be used (opens in Visio / Visio for the web)")))
    cfg = aiconfig.load_config()
    rows.append(("Config", str(aiconfig.CONFIG_PATH)))
    if cfg.provider:
        key = bool(aiconfig.resolve_key(cfg.provider)) or cfg.provider.provider == "ollama"
        rows.append(("AI provider", mark(key, f"{cfg.provider.provider} · {cfg.provider.model}",
                                         "API key missing: run visio-ai setup")))
    else:
        found = aiconfig.detect_providers(probe_ollama=True)
        rows.append(("AI provider", mark(bool(found), "not set" + (
            f" (detected: {', '.join(p.provider for p in found)})" if found else ""), "run visio-ai setup")))
    tools = handoff.installed_tools()
    rows.append(("AI coding apps", mark(bool(tools), ", ".join(t.name for t in tools) or "none",
                                        "optional: Claude Code, Gemini CLI, Codex, Copilot CLI")))
    try:
        import playwright  # noqa: F401

        png = True
    except ImportError:
        png = False
    rows.append(("PNG previews", mark(png or has_visio, "available" if (png or has_visio) else "not available",
                                      "optional: pip install playwright && playwright install chromium")))
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    rows.append(("PDF without Visio", mark(bool(soffice) or has_visio, "LibreOffice" if soffice else "not available",
                                           "optional: install LibreOffice")))
    rows.append(("Output folder", str(engine.default_out_dir())))
    ui.console.print(ui.panel(ui.kv_table(rows), title="visio-ai doctor"))
    return 0


def _themes(args: Any) -> int:
    from visio_mcp import style
    from visio_mcp.cli import ui

    t = ui.table("Theme", "Font", "Palette", "Use it for")
    for th in style.THEMES.values():
        sw = Text()
        for cat in ("compute", "data", "integration", "network", "security"):
            sw.append("■ ", style=th.node_style(cat).line or "white")
        t.add_row(Text(th.name, style="key"), th.title.font, sw, Text(th.description, style="muted"))
    ui.console.print(t)
    return 0


def _kinds(args: Any) -> int:
    from rich.markdown import Markdown

    from visio_mcp import catalog
    from visio_mcp.cli import ui

    ui.console.print(Markdown(catalog.describe_kinds(args.provider)))
    return 0


def _rules(args: Any) -> int:
    from rich.markdown import Markdown

    from visio_mcp import rules
    from visio_mcp.cli import ui

    ui.console.print(Markdown(rules.get_rules(args.type, args.provider)))
    return 0


def _examples(args: Any) -> int:
    from visio_mcp.cli import studio, ui
    from visio_mcp.engine import Drawer
    from visio_mcp.spec import DiagramSpec

    root = Path(__file__).resolve().parents[3] / "examples"
    files = sorted(root.glob("*.json")) if root.is_dir() else []
    if not files:
        ui.fail("No examples folder found next to the package.")
        return 1
    drawer = Drawer(target="native" if args.native else "auto", live=not args.no_live, attach=args.attach)
    out_dir = Path(args.out).expanduser() if args.out else None
    for f in files:
        spec = DiagramSpec.model_validate(json.loads(f.read_text(encoding="utf-8")))
        s = studio.Session(spec=spec, theme=args.theme or "auto", out_dir=out_dir)
        out = studio.draw(drawer, s, args.formats)
        ui.ok(f"{f.stem}: {out.vsdx}")
    if not drawer.live:
        drawer.close()
    return 0


def _mcp(args: Any) -> int:
    from visio_mcp import server

    server.main()
    return 0


COMMANDS = {
    "studio": _studio, "draw": _draw, "render": _render, "scan": _scan, "setup": _setup, "handoff": _handoff,
    "doctor": _doctor, "themes": _themes, "kinds": _kinds, "rules": _rules, "examples": _examples, "mcp": _mcp,
}


def _help() -> int:
    from visio_mcp.cli import ui

    ui.banner()
    t = ui.table("Command", "What it does")
    for cmd, desc in [
        ("visio-ai", "Interactive studio: point at code, pick a diagram, watch Visio draw it, refine by chatting"),
        ("visio-ai draw PATH", "Explore a repo (or a folder of repos) and draw — no questions asked"),
        ("visio-ai render SPEC.json", "Draw a saved diagram spec"),
        ("visio-ai scan PATH", "Profile repositories: stack, cloud, IaC, CI, suggested diagrams"),
        ("visio-ai setup", "Choose the AI: Claude, Gemini, Azure OpenAI, OpenAI or Ollama"),
        ("visio-ai handoff PATH", "Let Claude Code, Gemini CLI, Codex or Copilot CLI draw it via MCP"),
        ("visio-ai doctor", "Check Visio, the AI provider and preview renderers"),
        ("visio-ai themes | kinds | rules TYPE", "Browse themes, shape kinds and diagramming rules"),
        ("visio-ai examples", "Draw the bundled example diagrams"),
        ("visio-ai mcp", "Run the MCP server (for any MCP client)"),
    ]:
        t.add_row(Text(cmd, style="key"), Text(desc, style="muted"))
    ui.console.print(t)
    ui.hint("Common flags: --type architecture  --theme azure  --focus \"payments flow\"  --attach  --native  --out DIR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
