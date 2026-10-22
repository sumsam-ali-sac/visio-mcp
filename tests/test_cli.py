"""The visio-ai terminal app: non-interactive commands and the handoff config writers."""

import json
from pathlib import Path

import pytest

from visio_mcp.cli.main import main as cli_main
from visio_mcp.cli import handoff


@pytest.fixture(autouse=True)
def wide_console(monkeypatch, tmp_path):
    from visio_mcp.cli import ui

    monkeypatch.setattr(ui.console, "width", 140)
    monkeypatch.setenv("VISIO_MCP_OUT", str(tmp_path / "out"))


def run(capsys, *argv: str) -> tuple[int, str]:
    code = cli_main(list(argv))
    return code, capsys.readouterr().out


def test_help_lists_commands(capsys):
    code, out = run(capsys, "--help")
    assert code == 0
    for cmd in ("visio-ai draw PATH", "visio-ai render", "visio-ai handoff", "visio-ai doctor"):
        assert cmd in out


def test_version(capsys):
    code, out = run(capsys, "--version")
    assert code == 0 and "visio-ai 0." in out


def test_themes(capsys):
    code, out = run(capsys, "themes")
    assert code == 0
    assert "blueprint" in out and "azure" in out


def test_studio_refuses_non_interactive(capsys):
    code, out = run(capsys, "studio")
    assert code == 2 and "visio-ai draw" in out


def test_render_missing_file_is_friendly(capsys, tmp_path):
    code, out = run(capsys, "render", str(tmp_path / "nope.json"), "--native", "--no-open")
    assert code == 1 and "nope.json" in out


def test_doctor_runs(capsys, monkeypatch, tmp_path):
    from visio_mcp.ai import config

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "AZURE_OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "detect_providers", lambda **kw: [])
    code, out = run(capsys, "doctor")
    assert code == 0
    assert "Visio desktop" in out and "AI provider" in out


# --- handoff ------------------------------------------------------------------------------


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_server_command_falls_back_to_module(monkeypatch):
    monkeypatch.setattr(handoff.shutil, "which", lambda name: None)
    cmd = handoff.server_command()
    assert cmd[1:] == ["-m", "visio_mcp.mcp"]


def test_gemini_register_merges_settings(home):
    settings = home / ".gemini" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    handoff._gemini_register(["visio-mcp"])
    data = json.loads(settings.read_text())
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["visio"]["command"] == "visio-mcp"


def test_copilot_register(home):
    handoff._copilot_register(["py", "-m", "visio_mcp.mcp"])
    data = json.loads((home / ".copilot" / "mcp-config.json").read_text())
    assert data["mcpServers"]["visio"] == {
        "type": "local", "command": "py", "args": ["-m", "visio_mcp.mcp"], "tools": ["*"],
    }


def test_codex_register_replaces_old_table(home):
    cfg = home / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('model = "gpt-5"\n\n[mcp_servers.visio]\ncommand = "old"\n\n[mcp_servers.other]\ncommand = "o"\n')
    handoff._codex_register(["visio-mcp"])
    text = cfg.read_text()
    assert text.count("[mcp_servers.visio]") == 1
    assert '"old"' not in text and 'command = "visio-mcp"' in text
    assert "[mcp_servers.other]" in text and 'model = "gpt-5"' in text
    import tomllib

    assert tomllib.loads(text)["mcp_servers"]["visio"]["args"] == []


def test_prompt_mentions_type_and_focus(tmp_path):
    p = handoff.build_prompt([tmp_path], "cloud", "the ingestion path")
    assert str(tmp_path) in p and "cloud" in p and "the ingestion path" in p
    assert "render_diagram" in p
