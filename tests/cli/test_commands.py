"""visio-ai commands that run without a terminal."""

from pathlib import Path

import pytest

from visio_mcp.cli.main import main as cli_main


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


def test_doctor_accepts_azure_sign_in_without_a_key(capsys, monkeypatch, tmp_path):
    from visio_mcp.ai import config

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    config.save_config(config.AppConfig(provider=config.ProviderConfig(
        "azure", "gpt", endpoint="https://res.openai.azure.com", deployment="gpt")))
    code, out = run(capsys, "doctor")
    assert code == 0
    assert "Azure sign-in (Entra ID)" in out and "API key missing" not in out


def test_render_native_writes_a_vsdx(capsys, tmp_path):
    spec = Path(__file__).resolve().parents[2] / "examples" / "ci-pipeline.json"
    code, out = run(capsys, "render", str(spec), "--native", "--no-open", "--out", str(tmp_path / "r"))
    assert code == 0 and "Diagram ready" in out
    assert list((tmp_path / "r").glob("*.vsdx"))


def test_scan_json_and_table(capsys, tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("print('hi')\n")
    (tmp_path / "app" / "requirements.txt").write_text("fastapi\n")
    code, out = run(capsys, "scan", str(tmp_path / "app"), "--json")
    assert code == 0 and '"name": "app"' in out
    code, out = run(capsys, "scan", str(tmp_path / "app"))
    assert code == 0 and "Repository" in out


def test_kinds_and_rules(capsys):
    assert "aws-lambda" in run(capsys, "kinds", "--provider", "aws")[1]
    assert "lane" in run(capsys, "rules", "swimlane")[1].lower()


def test_unknown_scan_path_is_friendly(capsys, tmp_path):
    code, out = run(capsys, "scan", str(tmp_path / "missing"))
    assert code == 1 and "missing" in out
