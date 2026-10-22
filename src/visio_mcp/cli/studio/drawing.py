"""Drawing the session's spec and presenting it: the draft outline and the result panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree

from visio_mcp import lint
from visio_mcp.cli import ui
from visio_mcp.cli.studio.session import Session
from visio_mcp.output.result import DrawOutput
from visio_mcp.output.drawer import Drawer
from visio_mcp.output.files import default_out_dir, slug
from visio_mcp.spec import DiagramSpec


def draw(drawer: Drawer, s: Session, formats: list[str] | None = None) -> DrawOutput:
    """Render s.spec with the session's theme into its output folder."""
    assert s.spec is not None
    spec = s.spec if s.theme == "auto" else s.spec.model_copy(update={"theme": s.theme})
    vsdx = (s.out_dir or default_out_dir()) / f"{slug(spec.title)}.vsdx"
    where = "live in Visio" if drawer.target == "visio" else "as a native .vsdx"
    fmts = formats or (["png"] if drawer.target == "visio" else ["png", "svg", "html"])
    with ui.spinner(f"Drawing {where}…") as status:
        out = drawer.render(spec, vsdx, fmts, progress=lambda m: status.update(Text(f"{m}…", style="muted")))
    s.output = out
    return out


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


def result_panel(out: DrawOutput) -> Panel:
    """What was drawn: summary, files, and the first few warnings and suggestions."""
    r, plan = out.result, out.plan
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
    notes = [*r.warnings, *r.suggestions]
    if notes:
        body.append(Text(""))
        for w in notes[:6]:
            body.append(Text(f"• {w}", style="warn" if w in r.warnings else "muted"))
        if len(notes) > 6:
            body.append(Text(f"  … {len(notes) - 6} more (/lint)", style="muted"))
    title = "Drawn live in Visio" if out.target == "visio" else "Diagram ready"
    return ui.panel(Group(*body), title=title, style=ui.GOOD)
