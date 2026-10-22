"""Diagramming ground rules: the knowledge base an agent reads before writing a DiagramSpec.

The rules are Markdown files shipped as package data in ``visio_mcp/rules/``:

- ``general.md``: universal rules for every diagram
- ``<type>.md``: one per DiagramType (flowchart, architecture, cloud, c4-context, ...)
- ``cloud-azure.md``, ``cloud-aws.md``, ``cloud-gcp.md``: provider conventions

Every type file starts with a ``**Use when:**`` line (see `type_summary`) and holds one
```json example spec (see `example`). ``visio_mcp.lint`` enforces the same rules in code.
"""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources
from typing import get_args

from visio_mcp.spec import DiagramType

TYPES: tuple[str, ...] = tuple(t for t in get_args(DiagramType) if t != "auto")
PROVIDERS: tuple[str, ...] = ("azure", "aws", "gcp")
_PROVIDER_ALIASES = {"microsoft": "azure", "amazon": "aws", "google": "gcp", "gcloud": "gcp"}

_USE_WHEN = re.compile(r"^\*\*Use when:\*\*\s*(.+)$", re.MULTILINE)
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


@cache
def _read(name: str) -> str:
    return resources.files("visio_mcp").joinpath("rules", f"{name}.md").read_text(encoding="utf-8")


def _check_type(diagram_type: str) -> str:
    key = diagram_type.strip().lower()
    if key not in TYPES:
        raise ValueError(f"unknown diagram type {diagram_type!r}; choose one of: {', '.join(TYPES)}")
    return key


def _check_provider(provider: str) -> str:
    key = provider.strip().lower()
    key = _PROVIDER_ALIASES.get(key, key)
    if key not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; choose one of: {', '.join(PROVIDERS)}")
    return key


def general() -> str:
    """Universal rules that apply to every diagram."""
    return _read("general")


def type_rules(diagram_type: str) -> str:
    """The rules file for one diagram type (no general rules)."""
    return _read(_check_type(diagram_type))


def provider_rules(provider: str) -> str:
    """Conventions for one cloud provider: azure, aws or gcp."""
    return _read(f"cloud-{_check_provider(provider)}")


def get_rules(diagram_type: str, provider: str | None = None) -> str:
    """General rules + the type's rules + provider rules.

    Provider rules are added when `provider` is given, or for type 'cloud' (all three
    providers when none is named).
    """
    dtype = _check_type(diagram_type)
    parts = [general(), _read(dtype)]
    if provider:
        parts.append(provider_rules(provider))
    elif dtype == "cloud":
        parts.extend(provider_rules(p) for p in PROVIDERS)
    return "\n\n---\n\n".join(p.strip() for p in parts) + "\n"


def type_summary() -> dict[str, str]:
    """One line per diagram type: when to use it."""
    out = {}
    for t in TYPES:
        m = _USE_WHEN.search(_read(t))
        out[t] = m.group(1).strip() if m else ""
    return out


def example(diagram_type: str) -> dict:
    """The example DiagramSpec (as a dict) from the type's rules file."""
    dtype = _check_type(diagram_type)
    m = _JSON_BLOCK.search(_read(dtype))
    if not m:
        raise ValueError(f"rules for {dtype!r} have no ```json example")
    return json.loads(m.group(1))
