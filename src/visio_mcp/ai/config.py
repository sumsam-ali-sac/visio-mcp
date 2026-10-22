"""User settings for the AI terminal app: which model provider to use, theme, output folder.

Stored as a small TOML file in the platform config directory. API keys may live there
(file mode 600 on POSIX) or in the usual environment variables; they are never printed.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
import urllib.request
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Literal, get_args

ProviderName = Literal["anthropic", "openai", "azure", "gemini", "ollama"]
PROVIDERS: tuple[str, ...] = get_args(ProviderName)

# Defaults for the model picker. Edit here to move OpenAI / Gemini to newer models.
OPENAI_DEFAULT_MODEL = "gpt-5"
GEMINI_DEFAULT_MODEL = "gemini-2.5-pro"
OLLAMA_DEFAULT_MODEL = "qwen3:latest"

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-5-5",
    "openai": OPENAI_DEFAULT_MODEL,
    "azure": "",  # Azure uses the deployment name (AZURE_OPENAI_DEPLOYMENT); see default_model()
    "gemini": GEMINI_DEFAULT_MODEL,
    "ollama": OLLAMA_DEFAULT_MODEL,
}

SUGGESTED_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-1"],
    "openai": [OPENAI_DEFAULT_MODEL, "gpt-5-mini", "gpt-4.1", "o3"],
    "azure": [],
    "gemini": [GEMINI_DEFAULT_MODEL, "gemini-2.5-flash"],
    "ollama": [OLLAMA_DEFAULT_MODEL, "llama3.1:latest", "qwen2.5-coder:latest"],
}

ENV_KEYS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "azure": ("AZURE_OPENAI_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "ollama": (),
}

DEFAULT_AZURE_API_VERSION = "2025-04-01-preview"
OLLAMA_URL = "http://localhost:11434"


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "visio-mcp"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "visio-mcp"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "visio-mcp"


CONFIG_PATH: Path = _config_dir() / "config.toml"


@dataclass
class ProviderConfig:
    provider: ProviderName
    model: str
    api_key: str | None = None
    endpoint: str | None = None
    api_version: str | None = None
    deployment: str | None = None
    effort: str | None = None

    def __repr__(self) -> str:  # never leak the key
        parts = []
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name == "api_key" and v:
                v = "***"
            parts.append(f"{f.name}={v!r}")
        return f"ProviderConfig({', '.join(parts)})"

    __str__ = __repr__

    @property
    def label(self) -> str:
        """Short display name, e.g. 'anthropic / claude-opus-5-5'."""
        return f"{self.provider} / {self.model or self.deployment or '?'}"


@dataclass
class AppConfig:
    provider: ProviderConfig | None = None
    theme: str = "auto"
    out_dir: str | None = None
    live: bool = True
    attach: bool = False
    recent_paths: list[str] = field(default_factory=list)


def default_model(provider: str) -> str:
    if provider == "azure":
        return os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
    return DEFAULT_MODELS.get(provider, "")


def suggested_models(provider: str, probe: bool = False) -> list[str]:
    """Model ids for the picker, best first. probe=True also lists local Ollama models."""
    if provider == "azure":
        dep = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        return [dep] if dep else []
    out = list(SUGGESTED_MODELS.get(provider, []))
    if provider == "ollama" and probe:
        for name in ollama_models():
            if name not in out:
                out.append(name)
    return out


def resolve_key(cfg: ProviderConfig) -> str | None:
    """The API key: from the config, else from the provider's environment variable."""
    if cfg.api_key:
        return cfg.api_key
    if cfg.provider == "ollama":
        return "ollama"
    for var in ENV_KEYS.get(cfg.provider, ()):
        if os.environ.get(var):
            return os.environ[var]
    return None


def key_source(cfg: ProviderConfig) -> str:
    """Where the key comes from, for display ('config', 'env ANTHROPIC_API_KEY', 'missing')."""
    if cfg.api_key:
        return "config"
    for var in ENV_KEYS.get(cfg.provider, ()):
        if os.environ.get(var):
            return f"env {var}"
    return "none needed" if cfg.provider == "ollama" else "missing"


def ollama_base() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return OLLAMA_URL
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


def ollama_models(base: str | None = None, timeout: float = 0.3) -> list[str]:
    """Names of locally pulled Ollama models; empty when Ollama is not running."""
    try:
        with urllib.request.urlopen(f"{base or ollama_base()}/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def _ollama_up(base: str, timeout: float = 0.3) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def detect_providers(probe_ollama: bool = True) -> list[ProviderConfig]:
    """Providers usable right now from environment variables (keys are not copied in)."""
    env = os.environ
    found: list[ProviderConfig] = []
    if env.get("ANTHROPIC_API_KEY"):
        found.append(ProviderConfig("anthropic", DEFAULT_MODELS["anthropic"]))
    if env.get("AZURE_OPENAI_API_KEY") and env.get("AZURE_OPENAI_ENDPOINT"):
        dep = env.get("AZURE_OPENAI_DEPLOYMENT")
        found.append(
            ProviderConfig(
                "azure",
                dep or "",
                endpoint=env["AZURE_OPENAI_ENDPOINT"],
                api_version=env.get("AZURE_OPENAI_API_VERSION") or DEFAULT_AZURE_API_VERSION,
                deployment=dep,
            )
        )
    if env.get("OPENAI_API_KEY"):
        found.append(ProviderConfig("openai", DEFAULT_MODELS["openai"]))
    if env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"):
        found.append(ProviderConfig("gemini", DEFAULT_MODELS["gemini"]))
    if probe_ollama:
        base = ollama_base()
        if _ollama_up(base):
            models = ollama_models(base)
            model = OLLAMA_DEFAULT_MODEL if (not models or OLLAMA_DEFAULT_MODEL in models) else models[0]
            found.append(ProviderConfig("ollama", model, endpoint=base))
    return found


# ---------------------------------------------------------------- TOML I/O


def _toml_str(s: str) -> str:
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif o < 0x20 or o == 0x7F:
            out.append(f"\\u{o:04X}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return _toml_str(str(v))


def dumps(cfg: AppConfig) -> str:
    lines = ["# visio-mcp AI settings (written by visio-ai setup)"]
    for name in ("theme", "out_dir", "live", "attach", "recent_paths"):
        v = getattr(cfg, name)
        if v is not None:
            lines.append(f"{name} = {_toml_value(v)}")
    if cfg.provider is not None:
        lines.append("")
        lines.append("[provider]")
        for f in fields(cfg.provider):
            v = getattr(cfg.provider, f.name)
            if v is not None and v != "":
                lines.append(f"{f.name} = {_toml_value(v)}")
    return "\n".join(lines) + "\n"


def loads(text: str) -> AppConfig:
    data = tomllib.loads(text)
    prov = None
    p = data.get("provider")
    if isinstance(p, dict) and p.get("provider") in PROVIDERS:
        known = {f.name for f in fields(ProviderConfig)}
        kw = {k: (str(v) if v is not None else None) for k, v in p.items() if k in known}
        kw.setdefault("model", default_model(kw["provider"]))
        prov = ProviderConfig(**kw)
    recent = data.get("recent_paths", [])
    return AppConfig(
        provider=prov,
        theme=str(data.get("theme", "auto")),
        out_dir=data.get("out_dir") or None,
        live=bool(data.get("live", True)),
        attach=bool(data.get("attach", False)),
        recent_paths=[str(x) for x in recent] if isinstance(recent, list) else [],
    )


def load_config(path: Path | str | None = None) -> AppConfig:
    """Read the config; a missing or unreadable file gives the defaults."""
    p = Path(path) if path else CONFIG_PATH
    try:
        return loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError):
        return AppConfig()


def save_config(cfg: AppConfig, path: Path | str | None = None) -> Path:
    """Write the config atomically, readable only by the user on POSIX."""
    p = Path(path) if path else CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(dumps(cfg))
    os.replace(tmp, p)
    if os.name == "posix":
        os.chmod(p, 0o600)
    return p


def remember_path(cfg: AppConfig, path: str, keep: int = 10) -> None:
    """Move path to the front of recent_paths."""
    cfg.recent_paths = [path] + [x for x in cfg.recent_paths if x != path]
    del cfg.recent_paths[keep:]
