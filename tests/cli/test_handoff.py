"""Registering the MCP server with AI coding apps and building the launch prompt."""

import json
from pathlib import Path

import pytest

from visio_mcp.cli import coding_apps


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def test_server_command_falls_back_to_module(monkeypatch):
    monkeypatch.setattr(coding_apps.shutil, "which", lambda name: None)
    cmd = coding_apps.server_command()
    assert cmd[1:] == ["-m", "visio_mcp.mcp"]


def test_gemini_register_merges_settings(home):
    settings = home / ".gemini" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    coding_apps._gemini_register(["visio-mcp"])
    data = json.loads(settings.read_text())
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["visio"]["command"] == "visio-mcp"


def test_copilot_register(home):
    coding_apps._copilot_register(["py", "-m", "visio_mcp.mcp"])
    data = json.loads((home / ".copilot" / "mcp-config.json").read_text())
    assert data["mcpServers"]["visio"] == {
        "type": "local", "command": "py", "args": ["-m", "visio_mcp.mcp"], "tools": ["*"],
    }


def test_codex_register_replaces_old_table(home):
    cfg = home / ".codex" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('model = "gpt-5"\n\n[mcp_servers.visio]\ncommand = "old"\n\n[mcp_servers.other]\ncommand = "o"\n')
    coding_apps._codex_register(["visio-mcp"])
    text = cfg.read_text()
    assert text.count("[mcp_servers.visio]") == 1
    assert '"old"' not in text and 'command = "visio-mcp"' in text
    assert "[mcp_servers.other]" in text and 'model = "gpt-5"' in text
    import tomllib

    assert tomllib.loads(text)["mcp_servers"]["visio"]["args"] == []


def test_prompt_mentions_type_and_focus(tmp_path):
    p = coding_apps.build_prompt([tmp_path], "cloud", "the ingestion path")
    assert str(tmp_path) in p and "cloud" in p and "the ingestion path" in p
    assert "render_diagram" in p
