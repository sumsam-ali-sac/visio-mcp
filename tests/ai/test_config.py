"""AI settings: TOML round trip, provider detection from the environment, config directory."""

from __future__ import annotations

import os
from pathlib import Path

from visio_mcp.ai import config as cfgmod


def test_config_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "config.toml"
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", path)
    cfg = cfgmod.AppConfig(
        provider=cfgmod.ProviderConfig("azure", "dep", api_key='s"k\\1\n', endpoint="https://e", deployment="dep",
                                       api_version="2025-04-01-preview", effort="medium"),
        theme="azure", out_dir="C:\\Users\\me\\out", live=False, attach=True, recent_paths=["/a", "/b ü"],
    )
    cfgmod.save_config(cfg)
    assert cfgmod.load_config() == cfg
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600
    assert cfgmod.load_config(tmp_path / "missing.toml") == cfgmod.AppConfig()
    (tmp_path / "bad.toml").write_text("this is = = not toml")
    assert cfgmod.load_config(tmp_path / "bad.toml") == cfgmod.AppConfig()


def test_key_never_in_repr():
    p = cfgmod.ProviderConfig("anthropic", "claude-opus-5-5", api_key="sk-secret-123")
    a = cfgmod.AppConfig(provider=p)
    for s in (repr(p), str(p), repr(a), str(a), p.label):
        assert "sk-secret-123" not in s
    assert "***" in repr(p)


def test_detect_providers_and_resolve_key(monkeypatch):
    for v in list(os.environ):
        if v.startswith(("ANTHROPIC", "OPENAI", "AZURE_OPENAI", "GEMINI", "GOOGLE_API")):
            monkeypatch.delenv(v)
    assert cfgmod.detect_providers(probe_ollama=False) == []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "z")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://e")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "dep")
    found = {p.provider: p for p in cfgmod.detect_providers(probe_ollama=False)}
    assert set(found) == {"anthropic", "gemini", "azure"}
    assert found["anthropic"].model == "claude-opus-5-5" and found["anthropic"].api_key is None
    assert found["azure"].deployment == "dep" and found["azure"].api_version == cfgmod.DEFAULT_AZURE_API_VERSION
    assert cfgmod.resolve_key(found["gemini"]) == "g"
    assert cfgmod.resolve_key(cfgmod.ProviderConfig("gemini", "x", api_key="cfg")) == "cfg"
    assert cfgmod.resolve_key(cfgmod.ProviderConfig("openai", "x")) is None
    assert cfgmod.suggested_models("anthropic")[0] == "claude-opus-5-5"
    assert "claude-fable-5-1" in cfgmod.suggested_models("anthropic")
    assert cfgmod.suggested_models("azure") == ["dep"]


def test_detect_ollama_probe(monkeypatch):
    for v in list(os.environ):
        if v.startswith(("ANTHROPIC", "OPENAI", "AZURE_OPENAI", "GEMINI", "GOOGLE_API", "OLLAMA")):
            monkeypatch.delenv(v)

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"models": [{"name": "llama3.1:latest"}]}'

    seen = []
    monkeypatch.setattr(cfgmod.urllib.request, "urlopen", lambda url, timeout: seen.append(timeout) or R())
    found = cfgmod.detect_providers()
    assert found[0].provider == "ollama" and found[0].model == "llama3.1:latest"
    assert all(t <= 0.3 for t in seen)


def test_config_dir_platforms(monkeypatch, tmp_path):
    monkeypatch.setattr(cfgmod.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cfgmod._config_dir() == tmp_path / "visio-mcp"
    monkeypatch.setattr(cfgmod.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    assert cfgmod._config_dir() == tmp_path / "AppData" / "visio-mcp"
    monkeypatch.setattr(cfgmod.sys, "platform", "darwin")
    assert cfgmod._config_dir() == Path.home() / "Library" / "Application Support" / "visio-mcp"
