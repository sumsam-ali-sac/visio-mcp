"""`visio-ai draw`, `render` and `examples`: turn code or saved specs into drawn diagrams."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from visio_mcp.ai import config
from visio_mcp.cli import ui
from visio_mcp.cli.studio.drawing import draw, result_panel, spec_tree
from visio_mcp.cli.studio.explore import offline_draft, repo_table, run_agent, scan_paths
from visio_mcp.cli.studio.session import Session, suggested_type
from visio_mcp.output.drawer import Drawer
from visio_mcp.output.files import open_file
from visio_mcp.spec import DiagramSpec

EXAMPLES_DIR = Path(__file__).resolve().parents[4] / "examples"


def _drawer(args: Any) -> Drawer:
    return Drawer(target="native" if args.native else "auto", live=not args.no_live, attach=args.attach)


def _out_dir(args: Any, default: Path | None = None) -> Path | None:
    return Path(args.out).expanduser() if args.out else default


def _load_spec(path: Path) -> DiagramSpec:
    return DiagramSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _finish(args: Any, s: Session, drawer: Drawer) -> int:
    """Draw the session's spec, show the result, and open the native preview."""
    try:
        out = draw(drawer, s, args.formats)
        ui.console.print(result_panel(out))
        if not args.no_open and drawer.target == "native":
            target = out.previews.get("html") or out.vsdx
            if target:
                open_file(target)
    finally:
        if not drawer.live:
            drawer.close()
    return 0


def _provider(args: Any, cfg: Any) -> Any:
    """The provider config to use: --provider/--model override the saved one."""
    pc = cfg.provider
    if args.provider:
        found = {p.provider: p for p in config.detect_providers(probe_ollama=args.provider == "ollama")}
        pc = found.get(args.provider) or config.ProviderConfig(
            provider=args.provider, model=config.DEFAULT_MODELS.get(args.provider, ""))
    if pc and args.model:
        pc.model = args.model
    return pc


def run(args: Any) -> int:
    ui.banner()
    cfg = config.load_config()
    s = Session(theme=args.theme or cfg.theme or "auto", focus=args.focus, out_dir=_out_dir(args))
    s.repos = scan_paths(args.path)
    ui.console.print(repo_table(s.repos))
    s.diagram_type = args.type or suggested_type(s.repos)
    ui.info(f"Diagram type: [accent2]{s.diagram_type}[/]")

    pc = _provider(args, cfg)
    if args.offline or pc is None:
        if pc is None and not args.offline:
            ui.warn("No AI provider configured (run `visio-ai setup`); drafting from a static scan.")
        s.spec = offline_draft(s.repos, s.diagram_type)
    else:
        from visio_mcp.ai import providers

        s.spec = run_agent(providers.make_llm(pc), pc, s)
    ui.console.print(ui.panel(spec_tree(s.spec), title="Draft"))
    if args.save_spec:
        Path(args.save_spec).write_text(s.spec.model_dump_json(indent=2, exclude_defaults=True), encoding="utf-8")
        ui.ok(f"Spec saved to {args.save_spec}")
    return _finish(args, s, _drawer(args))


def render(args: Any) -> int:
    path = Path(args.spec).expanduser()
    s = Session(spec=_load_spec(path), theme=args.theme or "auto", out_dir=_out_dir(args, path.parent))
    ui.banner()
    return _finish(args, s, _drawer(args))


def examples(args: Any) -> int:
    files = sorted(EXAMPLES_DIR.glob("*.json")) if EXAMPLES_DIR.is_dir() else []
    if not files:
        ui.fail("No examples folder found next to the package.")
        return 1
    drawer = _drawer(args)
    for f in files:
        s = Session(spec=_load_spec(f), theme=args.theme or "auto", out_dir=_out_dir(args))
        ui.ok(f"{f.stem}: {draw(drawer, s, args.formats).vsdx}")
    if not drawer.live:
        drawer.close()
    return 0
