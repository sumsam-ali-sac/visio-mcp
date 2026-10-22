"""Studio pieces that need no terminal: type voting, outline, result panel and slash commands."""

import json
from pathlib import Path

import pytest

from fake_visio import FakeVisio
from visio_mcp.cli import ui
from visio_mcp.cli.studio import refine
from visio_mcp.cli.studio.drawing import draw, result_panel, spec_tree
from visio_mcp.cli.studio.explore import repo_table
from visio_mcp.cli.studio.session import Session, provider_label, suggested_type
from visio_mcp.output.drawer import Drawer
from visio_mcp.repo import RepoInfo
from visio_mcp.spec import DiagramSpec

SPEC = DiagramSpec.model_validate({
    "title": "Shop",
    "nodes": [{"id": "web", "kind": "service", "label": "Web", "technology": "React", "group": "app"},
              {"id": "db", "kind": "database", "label": "Orders DB"}],
    "edges": [{"source": "web", "target": "db", "label": "SQL"}],
    "groups": [{"id": "app", "label": "App Tier", "kind": "tier"}],
})


@pytest.fixture(autouse=True)
def wide_console(monkeypatch, tmp_path):
    monkeypatch.setattr(ui.console, "width", 140)
    monkeypatch.setenv("VISIO_MCP_OUT", str(tmp_path))


@pytest.fixture
def session() -> Session:
    return Session(spec=SPEC)


@pytest.fixture
def drawer() -> Drawer:
    return Drawer(backend=FakeVisio())


def info(name: str, *types: str) -> RepoInfo:
    return RepoInfo(path=Path(name), name=name, suggested_types=list(types))


def test_suggested_type_votes_by_rank():
    assert suggested_type([]) == "architecture"
    assert suggested_type([info("a", "pipeline", "architecture")]) == "pipeline"
    assert suggested_type([info("a"), info("b")]) == "architecture"


def test_provider_label():
    class Cfg:
        provider, model = "anthropic", "opus"

    assert provider_label(Cfg()) == "Claude · opus"


def test_repo_table_lists_each_repo(capsys):
    r = info("billing", "cloud")
    r.languages, r.cloud, r.ci = {"python": 10}, ["azure"], ["github"]
    ui.console.print(repo_table([r]))
    out = capsys.readouterr().out
    assert "billing" in out and "python" in out and "Azure" in out and "CI" in out and "cloud" in out


def test_spec_tree_nests_nodes_under_groups(capsys):
    ui.console.print(spec_tree(SPEC))
    out = capsys.readouterr().out
    assert out.index("App Tier") < out.index("Web") and "React" in out and "Orders DB" in out


def test_draw_and_result_panel(capsys, session, drawer, tmp_path):
    out = draw(drawer, session)
    assert session.output is out
    ui.console.print(result_panel(out))
    text = capsys.readouterr().out
    assert "2 nodes" in text and "1 connectors" in text and "VSDX" in text
    assert (tmp_path / "shop.vsdx").as_posix() in text.replace("\n", "")


def test_theme_command_redraws_and_undo_restores(capsys, session, drawer):
    draw(drawer, session)
    assert refine.handle_command("theme", "dark", drawer, session) is None
    assert session.spec.theme == "dark" and len(session.history) == 1
    refine.handle_command("undo", "", drawer, session)
    assert session.spec.theme != "dark" and not session.history


def test_bad_theme_and_layout_are_reported(capsys, session, drawer):
    refine.handle_command("theme", "nope", drawer, session)
    refine.handle_command("layout", "nope", drawer, session)
    out = capsys.readouterr().out
    assert "unknown layout" in out and not session.history


def test_save_writes_the_spec(capsys, session, drawer, tmp_path):
    target = tmp_path / "shop.json"
    refine.handle_command("save", str(target), drawer, session)
    assert json.loads(target.read_text())["title"] == "Shop"


def test_quit_new_help_and_unknown(capsys, session, drawer):
    assert refine.handle_command("q", "", drawer, session) == "quit"
    assert refine.handle_command("new", "", drawer, session) == "new"
    assert refine.handle_command("help", "", drawer, session) is None
    assert "/undo" in capsys.readouterr().out
    refine.handle_command("bogus", "", drawer, session)
    assert "Unknown command /bogus" in capsys.readouterr().out


def test_studio_flow_offline_end_to_end(capsys, monkeypatch, tmp_path):
    from visio_mcp.cli import prompts
    from visio_mcp.cli.studio import flow

    code = tmp_path / "app"
    code.mkdir()
    (code / "requirements.txt").write_text("fastapi\npsycopg2\n")
    (code / "main.py").write_text("import fastapi\n")
    answers = {"Diagram type": "architecture", "How should we explore the code?": "offline", "Theme": "dark",
               "✎": "/quit"}
    monkeypatch.setattr(prompts, "select", lambda msg, *a, **k: answers[msg])
    monkeypatch.setattr(prompts, "text", lambda msg, *a, **k: answers.get(msg, ""))
    monkeypatch.setattr(prompts, "confirm", lambda *a, **k: False)
    monkeypatch.setattr(flow.aiconfig, "load_config", lambda: flow.aiconfig.AppConfig())
    monkeypatch.setattr(flow.aiconfig, "save_config", lambda cfg: None)
    monkeypatch.setattr(flow, "_make_drawer", lambda args, cfg: Drawer(backend=FakeVisio()))

    class Args:
        path, type, focus, theme, out, native, no_open = str(code), None, "", None, str(tmp_path / "o"), True, True

    assert flow.studio(Args()) == 0
    out = capsys.readouterr().out
    assert "Draft" in out and ("Diagram ready" in out or "Drawn live" in out)
    assert list((tmp_path / "o").glob("*.vsdx"))
