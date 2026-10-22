"""The studio's shared state (Session) and small helpers about diagram types and providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from visio_mcp import rules
from visio_mcp.output.result import DrawOutput
from visio_mcp.repo import RepoInfo
from visio_mcp.spec import DiagramSpec

PROVIDER_NAMES = {"anthropic": "Claude", "openai": "OpenAI", "azure": "Azure OpenAI", "gemini": "Gemini",
                  "ollama": "Ollama"}


@dataclass
class Session:
    repos: list[RepoInfo] = field(default_factory=list)
    diagram_type: str = "architecture"
    focus: str = ""
    theme: str = "auto"
    spec: DiagramSpec | None = None
    history: list[DiagramSpec] = field(default_factory=list)
    output: DrawOutput | None = None
    agent: Any = None
    out_dir: Path | None = None


def type_info() -> dict[str, str]:
    """Diagram type -> when to use it."""
    return rules.type_summary()


def suggested_type(repos: list[RepoInfo]) -> str:
    """The diagram type the scanned repos vote for most."""
    votes: dict[str, float] = {}
    for r in repos:
        for i, t in enumerate(r.suggested_types[:3]):
            votes[t] = votes.get(t, 0) + 3 - i
    if len(repos) > 1:
        votes["architecture"] = votes.get("architecture", 0) + 2
    return max(votes, key=votes.get) if votes else "architecture"  # type: ignore[arg-type]


def provider_label(cfg: Any) -> str:
    return f"{PROVIDER_NAMES.get(cfg.provider, cfg.provider)} · {cfg.model}"
