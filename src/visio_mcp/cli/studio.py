"""The interactive studio: point at code, pick a diagram, watch it drawn live, refine by chatting."""

from __future__ import annotations

import json
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.live import Live
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

from visio_mcp import lint, style
from visio_mcp.output import drawer as engine
from visio_mcp.cli import ui
from visio_mcp.cli.ui import console
from visio_mcp.output.drawer import DrawOutput, Drawer
from visio_mcp.spec import DiagramSpec

TYPE_INFO = {  # fallback when rules.type_summary() is unavailable
    "architecture": "Components, services and data stores, and how they talk",
    "cloud": "Cloud services in their account/region/network hierarchy",
    "c4-context": "The system, its users and the systems around it",
    "c4-container": "Apps, services and stores inside one system",
    "deployment": "Where things run: hosts, containers, clusters",
    "dataflow": "How data moves from sources to sinks",
    "pipeline": "CI/CD or ETL stages in order",
    "erd": "Database tables and relationships",
    "flowchart": "A process with steps and decisions",
    "swimlane": "A process split by who does each step",
    "network": "Routers, firewalls, subnets and links",
    "state": "States and transitions of one thing",
    "org": "Org chart / hierarchy",
    "mindmap": "A central idea and its branches",
}
TOOL_ICONS = {"list_dir": "📂", "read_file": "📄", "search": "🔎", "find_files": "🗂 ",
              "get_rules": "📐", "list_kinds": "🧩", "submit_diagram": "✏️ "}


def type_info() -> dict[str, str]:
    try:
        from visio_mcp import rules

        summary = rules.type_summary()
        return {k: summary.get(k, TYPE_INFO.get(k, "")) for k in [*TYPE_INFO, *summary] if k in summary or k in TYPE_INFO}
    except Exception:
        return dict(TYPE_INFO)


@dataclass
class Session:
    repos: list[Any] = field(default_factory=list)  # scanner.RepoInfo
    diagram_type: str = "architecture"
    focus: str = ""
    theme: str = "auto"
    spec: DiagramSpec | None = None
    history: list[DiagramSpec] = field(default_factory=list)
    output: DrawOutput | None = None
    agent: Any = None
    out_dir: Path | None = None


# --- shared pipeline pieces (also used by `visio-ai draw`) -----------------------------------


def scan_paths(raw: str) -> list[Any]:
    from visio_mcp import repo as scanner

    with ui.spinner("Scanning for repositories…"):
        t0 = time.perf_counter()
        repos = scanner.discover(raw.strip().strip('"').strip("'"))
    if not repos:
        raise FileNotFoundError(f"no code found under {raw}")
    ui.ok(f"Found {len(repos)} repositor{'y' if len(repos) == 1 else 'ies'} in {time.perf_counter() - t0:.1f}s")
    return repos


def repo_table(repos: list[Any]) -> Any:
    t = ui.table("Repository", "Stack", "Infra", "Suggested")
    for r in repos:
        langs = ", ".join(list(r.languages)[:2])
        stack = " · ".join(x for x in [langs, ", ".join(r.frameworks[:2])] if x)
        infra = ", ".join(([c.upper() if c != "azure" else "Azure" for c in r.cloud]) +
                          (["Docker"] if r.containers else []) + (["CI"] if r.ci else [])) or "—"
        t.add_row(Text(r.name, style="bold"), Text(stack or "—", style="muted"), infra,
                  Text(r.suggested_types[0] if r.suggested_types else "architecture", style="accent2"))
    return t


def suggested_type(repos: list[Any]) -> str:
    votes: dict[str, float] = {}
    for r in repos:
        for i, t in enumerate(r.suggested_types[:3]):
            votes[t] = votes.get(t, 0) + 3 - i
    if len(repos) > 1:
        votes["architecture"] = votes.get("architecture", 0) + 2
    return max(votes, key=votes.get) if votes else "architecture"  # type: ignore[arg-type]


def provider_label(cfg: Any) -> str:
    names = {"anthropic": "Claude", "openai": "OpenAI", "azure": "Azure OpenAI", "gemini": "Gemini",
             "ollama": "Ollama"}
    return f"{names.get(cfg.provider, cfg.provider)} · {cfg.model}"


def run_agent(llm: Any, cfg: Any, s: Session) -> DiagramSpec:
    """Let the AI explore the code with a live activity feed; returns the drafted spec."""
    from visio_mcp.ai.agent import DiagramAgent

    feed: deque[Text] = deque(maxlen=9)
    state = {"status": "Reading the workspace", "steps": 0, "t0": time.perf_counter()}

    def render() -> Any:
        elapsed = time.perf_counter() - state["t0"]
        head = Text.assemble((f" {provider_label(cfg)} ", "bold black on #7C9CFF"), "  ",
                             (f"{state['steps']} steps · {elapsed:,.0f}s", "muted"))
        spin = Spinner("dots12", text=Text(state["status"], style="bold"), style=ui.ACCENT)
        return ui.panel(Group(head, Text(""), *feed, Text(""), spin), title="Exploring the code",
                        subtitle="Ctrl+C to stop")

    def on_event(ev: Any) -> None:
        kind, msg = ev.kind, ev.message
        if kind == "tool":
            state["steps"] += 1
            name = msg.split(" ", 1)[0]
            feed.append(Text.assemble(f"  {TOOL_ICONS.get(name, '•')} ", (msg, "default")))
            state["status"] = {"read_file": "Reading code", "search": "Searching", "list_dir": "Browsing",
                               "find_files": "Finding files", "submit_diagram": "Drafting the diagram"}.get(
                name, "Working")
        elif kind in ("thinking", "text") and msg.strip():
            line = " ".join(msg.split())
            feed.append(Text(f"  💭 {line[:110] + ('…' if len(line) > 110 else '')}", style="italic muted"))
        elif kind == "lint":
            feed.append(Text(f"  📐 {msg}", style="warn"))
            state["status"] = "Polishing against the diagram rules"
        elif kind == "status":
            state["status"] = msg
        elif kind == "error":
            feed.append(Text(f"  ✖ {msg}", style="bad"))
        live.update(render())

    agent = DiagramAgent(llm, s.repos, s.diagram_type, s.focus,
                         provider_hint=_provider_hint(s.repos), on_event=on_event)
    s.agent = agent
    with Live(render(), console=console, refresh_per_second=12, transient=True) as live:
        try:
            spec = agent.run()
        except KeyboardInterrupt:
            agent.cancel()
            raise
    ui.ok(f"Explored the code in {state['steps']} steps ({time.perf_counter() - state['t0']:.0f}s)")
    return spec


def _provider_hint(repos: list[Any]) -> str | None:
    clouds = [c for r in repos for c in r.cloud]
    return max(set(clouds), key=clouds.count) if clouds else None


def spec_tree(spec: DiagramSpec) -> Tree:
    """A compact outline of the drafted diagram: groups with their members."""
    norm, _ = lint.normalize(spec)
    tree = Tree(Text.assemble((norm.title, "bold"), ("  " + norm.subtitle if norm.subtitle else "", "muted")),
                guide_style=ui.MUTED)
    children: dict[str | None, list[Any]] = {}
    for g in norm.groups:
        children.setdefault(g.parent, []).append(g)
    members: dict[str | None, list[Any]] = {}
    for n in norm.nodes:
        members.setdefault(n.group, []).append(n)

    def add(branch: Tree, gid: str | None) -> None:
        for g in children.get(gid, []):
            add(branch.add(Text.assemble(("▣ ", "accent"), (g.label, "bold"), (f"  {g.kind}", "muted"))), g.id)
        for n in members.get(gid, []):
            tech = f"  {n.technology}" if n.technology else ""
            branch.add(Text.assemble(("● " if n.emphasis else "○ ", "accent2"), n.label, (tech, "muted"),
                                     (f"  [{n.kind}]", "dim")))

    add(tree, None)
    return tree


def draw(drawer: Drawer, s: Session, formats: list[str] | None = None) -> DrawOutput:
    assert s.spec is not None
    spec = s.spec if s.theme == "auto" else s.spec.model_copy(update={"theme": s.theme})
    out_dir = s.out_dir or engine.default_out_dir()
    vsdx = out_dir / f"{engine.slug(spec.title)}.vsdx"
    where = "live in Visio" if drawer.target == "visio" else "as a native .vsdx"
    fmts = formats or (["png"] if drawer.target == "visio" else ["png", "svg", "html"])
    with ui.spinner(f"Drawing {where}…") as status:
        out = drawer.render(spec, vsdx, fmts, progress=lambda m: status.update(Text(f"{m}…", style="muted")))
    s.output = out
    return out


def result_panel(s: Session, out: DrawOutput) -> Any:
    r = out.result
    plan = out.plan
    rows: list[tuple[str, Any]] = []
    if plan:
        rows.append(("Diagram", Text.assemble((plan.spec.title, "bold"), (f"  {plan.spec.type} · {plan.spec.layout}"
                                                                         f" · {plan.theme.name} theme", "muted"))))
    rows.append(("Shapes", f"{len(plan.nodes) if plan else r.shapes} nodes · {len(plan.groups) if plan else 0} groups"
                           f" · {r.connectors} connectors"))
    for f in r.files:
        p = Path(f)
        rows.append((p.suffix.lstrip(".").upper(), Text(str(p), style=f"link file://{p.as_posix()}")))
    body: list[Any] = [ui.kv_table(rows)]
    if r.overlaps:
        body += [Text(""), Text(f"▲ {len(r.overlaps)} overlapping shape pairs", style="warn")]
    notes = [w for w in r.warnings] + [x for x in r.suggestions]
    if notes:
        body.append(Text(""))
        for w in notes[:6]:
            body.append(Text(f"• {w}", style="warn" if w in r.warnings else "muted"))
        if len(notes) > 6:
            body.append(Text(f"  … {len(notes) - 6} more (/lint)", style="muted"))
    title = "Drawn live in Visio" if out.target == "visio" else "Diagram ready"
    return ui.panel(Group(*body), title=title, style=ui.GOOD)


# --- the interactive flow -------------------------------------------------------------------


HELP = [
    ("<describe a change>", "e.g. “group the databases”, “add the Stripe webhook”, “make it left to right”"),
    ("/open", "open the diagram (Visio, or the browser preview)"),
    ("/theme [name]", "switch theme: " + ", ".join(style.THEMES)),
    ("/layout [name]", "re-layout: flowchart-lr, flowchart-tb, swimlane-lr, tree-tb, radial, grid…"),
    ("/export png|svg|pdf|html", "export the current diagram"),
    ("/spec", "show the diagram spec (JSON)"),
    ("/save [file]", "save the spec to a JSON file"),
    ("/lint", "show rule findings"),
    ("/undo", "go back to the previous version"),
    ("/new", "draw another diagram of the same code"),
    ("/quit", "leave"),
]


def studio(args: Any) -> int:
    from visio_mcp.ai import config as aiconfig

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
        # 1. where's the code
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
        console.print(repo_table(s.repos))
        if len(s.repos) > 1:
            picked = ui.checkbox("Which repositories belong in the diagram?",
                                 [ui.choice(r.name, r, r.summary, None) for r in s.repos])
            for c in picked or []:
                pass
            s.repos = picked or s.repos

        # 2. what to draw
        while True:
            ui.step(2, 4, "What should we draw?")
            s.diagram_type = getattr(args, "type", None) or _ask_type(s.repos)
            s.focus = ui.text("Anything to focus on?", instruction="(optional — enter to skip)",
                              default=getattr(args, "focus", "") or "").strip()

            # 3. how to explore
            ui.step(3, 4, "Explore the code")
            how = _ask_engine(cfg)
            if how == "handoff":
                return _handoff(s)
            if how == "setup":
                cfg = setup_wizard(cfg)
                how = "ai" if cfg.provider else "offline"
            s.spec = _explore(how, cfg, s)
            if s.spec is None:
                continue
            console.print(ui.panel(spec_tree(s.spec), title="Draft"))
            _offer_icons(s.spec)

            # 4. draw
            ui.step(4, 4, "Draw")
            if s.theme == "auto" and not getattr(args, "theme", None):
                s.theme = _ask_theme(s.spec)
            out = draw(drawer, s)
            console.print(result_panel(s, out))
            if drawer.target == "native" and out.previews.get("html") and not getattr(args, "no_open", False):
                engine.open_file(out.previews["html"])
            if _refine_loop(drawer, cfg, s) != "new":
                break
    except (ui.Cancelled, KeyboardInterrupt):
        console.print()
        ui.hint("Bye — your diagrams are in " + str(s.out_dir or engine.default_out_dir()))
        return 130
    finally:
        if not drawer.live:
            drawer.close()
    ui.hint("Saved in " + str(s.out_dir or engine.default_out_dir()))
    return 0


_icons_offered: set[str] = set()


def _offer_icons(spec: DiagramSpec) -> None:
    """Cloud diagram without the provider's icon pack: offer once to install the official icons."""
    from visio_mcp import icons

    missing = [p for p in icons.missing_for([n.kind for n in spec.nodes]) if p not in _icons_offered]
    if not missing:
        return
    _icons_offered.update(missing)
    names = " and ".join(icons.PROVIDER_NAMES[p] for p in missing)
    if not ui.confirm(f"Install the official {names} icons now? (recommended)", default=True):
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
    console.print(ui.kv_table([("Output", visio), ("AI", ai)]))


def _ask_path(cfg: Any) -> str:
    recent = [p for p in getattr(cfg, "recent_paths", []) if Path(p).exists()][:5]
    if recent:
        pick = ui.select("Choose a folder (a repo, or a folder of repos)",
                         [ui.choice(p, p) for p in recent] + [ui.choice("Another folder…", "")])
        if pick:
            return pick
    return ui.path("Folder path", default=str(Path.cwd()) + ("\\" if "\\" in str(Path.cwd()) else "/"))


def _remember_path(cfg: Any, raw: str) -> None:
    from visio_mcp.ai import config as aiconfig

    p = str(Path(raw.strip().strip('"')).expanduser().resolve())
    cfg.recent_paths = [p] + [x for x in cfg.recent_paths if x != p][:7]
    try:
        aiconfig.save_config(cfg)
    except OSError:
        pass


def _ask_type(repos: list[Any]) -> str:
    best = suggested_type(repos)
    info = type_info()
    order = [best] + [t for t in info if t != best]
    choices = [ui.choice(("★ " if t == best else "  ") + t, t, info.get(t, "")) for t in order]
    return ui.select("Diagram type", choices, default=choices[0].value)


def _ask_engine(cfg: Any) -> str:
    from visio_mcp.cli import handoff

    choices = []
    if cfg.provider:
        choices.append(ui.choice(f"AI agent  ·  {provider_label(cfg.provider)}", "ai", "explores the code, then drafts"))
    choices.append(ui.choice("Set up an AI provider", "setup", "Claude, Gemini, Azure OpenAI, OpenAI or Ollama"))
    tools = handoff.installed_tools()
    if tools:
        names = ", ".join(t.name for t in tools)
        choices.append(ui.choice("Hand off to my AI coding app", "handoff", names))
    choices.append(ui.choice("Quick draft without AI", "offline", "static scan of manifests, compose, IaC, CI"))
    return ui.select("How should we explore the code?", choices)


def _explore(how: str, cfg: Any, s: Session) -> DiagramSpec | None:
    if how == "offline":
        from visio_mcp import repo as scanner

        with ui.spinner("Drafting from the static scan…"):
            spec = scanner.heuristic_spec(s.repos, s.diagram_type)
        ui.ok(f"Drafted {len(spec.nodes)} nodes from manifests, compose files, IaC and CI")
        return spec
    from visio_mcp.ai import providers

    try:
        llm = providers.make_llm(cfg.provider)
        return run_agent(llm, cfg.provider, s)
    except KeyboardInterrupt:
        ui.warn("Stopped.")
        return None
    except Exception as e:  # LLMError carries a hint
        ui.fail(str(getattr(e, "message", e)), getattr(e, "hint", "") or "Try /setup or the quick draft.")
        if ui.confirm("Use a quick draft from the static scan instead?", default=True):
            return _explore("offline", cfg, s)
        return None


def _ask_theme(spec: DiagramSpec) -> str:
    norm, _ = lint.normalize(spec)
    auto = norm.theme
    choices = [ui.choice(f"★ {auto}", auto, style.THEMES[auto].description + "  (recommended)")]
    choices += [ui.choice(f"  {t.name}", t.name, t.description) for t in style.THEMES.values() if t.name != auto]
    return ui.select("Theme", choices)


def _handoff(s: Session) -> int:
    from visio_mcp.cli import handoff

    tools = handoff.installed_tools()
    tool = tools[0] if len(tools) == 1 else ui.select("Which app?", [ui.choice(t.name, t) for t in tools])
    changed, argv, cwd = handoff.handoff(tool, [r.path for r in s.repos], s.diagram_type, s.focus)
    ui.ok(changed)
    ui.info(f"Launching {tool.name} in {cwd} — it will explore the code and draw in Visio.")
    console.print()
    return subprocess.call(argv, cwd=cwd)


def _refine_loop(drawer: Drawer, cfg: Any, s: Session) -> str:
    console.print()
    ui.hint("Refine it: describe a change in plain words, or type /help.")
    while True:
        console.print()
        try:
            line = ui.text("✎", instruction="").strip()
        except ui.Cancelled:
            return "quit"
        if not line:
            continue
        if line.startswith("/"):
            cmd, _, arg = line[1:].partition(" ")
            res = _command(cmd.lower(), arg.strip(), drawer, s)
            if res in ("quit", "new"):
                return res
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
        _apply(drawer, s, spec)


def _apply(drawer: Drawer, s: Session, spec: DiagramSpec) -> None:
    if s.spec is not None:
        s.history.append(s.spec)
    s.spec = spec
    out = draw(drawer, s)
    console.print(result_panel(s, out))


def _command(cmd: str, arg: str, drawer: Drawer, s: Session) -> str | None:
    assert s.spec is not None
    if cmd in ("q", "quit", "exit"):
        return "quit"
    if cmd == "new":
        return "new"
    if cmd in ("h", "help", "?"):
        t = ui.table("Command", "What it does")
        for k, v in HELP:
            t.add_row(Text(k, style="key"), Text(v, style="muted"))
        console.print(t)
    elif cmd == "open":
        out = s.output
        if out and drawer.target == "visio":
            ui.ok("It's open in Visio.") if drawer.live else engine.open_file(out.vsdx)
        elif out:
            engine.open_file(out.previews.get("html") or out.vsdx)
    elif cmd == "theme":
        name = arg or _ask_theme(s.spec)
        try:
            style.get_theme(name)
        except ValueError as e:
            return ui.fail(str(e))
        s.theme = name
        _apply(drawer, s, s.spec.model_copy(update={"theme": name}))
    elif cmd == "layout":
        layouts = ["flowchart-lr", "flowchart-tb", "swimlane-lr", "swimlane-tb", "tree-tb", "tree-lr",
                   "radial", "circular", "grid"]
        name = arg or ui.select("Layout", layouts)
        if name not in layouts + ["auto"]:
            return ui.fail(f"unknown layout {name!r}", "one of: " + ", ".join(layouts))
        _apply(drawer, s, s.spec.model_copy(update={"layout": name}))
    elif cmd == "export":
        fmt = (arg or "pdf").lower().lstrip(".")
        try:
            ui.ok(str(drawer.export(fmt)))
        except Exception as e:
            ui.fail(str(e))
    elif cmd == "spec":
        console.print(Syntax(s.spec.model_dump_json(indent=2, exclude_defaults=True), "json",
                             theme="ansi_dark", word_wrap=True))
    elif cmd == "save":
        target = Path(arg).expanduser() if arg else (s.output.vsdx.with_suffix(".json") if s.output and s.output.vsdx
                                                      else Path(engine.slug(s.spec.title) + ".json"))
        target.write_text(s.spec.model_dump_json(indent=2, exclude_defaults=True), encoding="utf-8")
        ui.ok(f"Saved {target}  ·  redraw it any time with: visio-ai render \"{target}\"")
    elif cmd == "lint":
        norm, notes = lint.normalize(s.spec)
        findings = lint.lint(norm)
        for f in notes + findings or ["No findings — it follows the ground rules."]:
            ui.info(f)
    elif cmd == "undo":
        if not s.history:
            return ui.warn("Nothing to undo.")
        s.spec = s.history.pop()
        out = draw(drawer, s)
        console.print(result_panel(s, out))
    else:
        ui.warn(f"Unknown command /{cmd}. Type /help.")
    return None


# --- provider setup ---------------------------------------------------------------------------


def setup_wizard(cfg: Any) -> Any:
    from visio_mcp.ai import config as aiconfig

    console.print(ui.panel(Text("Pick the model that explores your code. Keys stay on this machine "
                                f"({aiconfig.CONFIG_PATH}).", style="muted"), title="AI provider"))
    detected = {p.provider: p for p in aiconfig.detect_providers()}
    names = [("anthropic", "Claude (Anthropic)"), ("gemini", "Google Gemini"), ("azure", "Azure OpenAI"),
             ("openai", "OpenAI"), ("ollama", "Ollama (local)")]
    choices = [ui.choice(label, key, "detected in your environment" if key in detected else "")
               for key, label in names]
    provider = ui.select("Provider", choices)
    pc = detected.get(provider) or aiconfig.ProviderConfig(provider=provider, model=aiconfig.DEFAULT_MODELS.get(provider, ""))

    if provider == "azure":
        pc.endpoint = ui.text("Azure OpenAI endpoint", default=pc.endpoint or "https://<resource>.openai.azure.com")
        pc.deployment = ui.text("Deployment name", default=pc.deployment or "")
        pc.api_version = ui.text("API version", default=pc.api_version or "2024-10-21")
        pc.model = pc.deployment or pc.model
    if provider != "ollama" and not (pc.api_key or aiconfig.resolve_key(pc)):
        pc.api_key = ui.password("API key") or None
    if provider != "azure":
        models = aiconfig.suggested_models(provider) or [pc.model]
        pick = ui.select("Model", [ui.choice(m, m, "default" if m == pc.model else "") for m in models]
                         + [ui.choice("Other…", "")], default=pc.model if pc.model in models else None)
        pc.model = pick or ui.text("Model id", default=pc.model)

    if ui.confirm("Test the connection now?", default=True):
        from visio_mcp.ai import providers

        try:
            with ui.spinner("Saying hello…"):
                llm = providers.make_llm(pc)
                llm.start("Reply with the single word: ready", []).send_user("ping")
            ui.ok(f"Connected to {provider_label(pc)}")
        except Exception as e:
            ui.fail(str(getattr(e, "message", e)), getattr(e, "hint", ""))
            if not ui.confirm("Save it anyway?", default=False):
                return cfg
    cfg.provider = pc
    aiconfig.save_config(cfg)
    ui.ok(f"Saved to {aiconfig.CONFIG_PATH}")
    return cfg


def print_json(data: Any) -> None:
    console.print(Syntax(json.dumps(data, indent=2), "json", theme="ansi_dark"))
