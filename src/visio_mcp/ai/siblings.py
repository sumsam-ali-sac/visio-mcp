"""Lazy access to the repo, rules, lint and catalog packages, so tests can swap them in sys.modules."""

from __future__ import annotations

import importlib
from typing import Any


def sibling(name: str) -> Any:
    return importlib.import_module(f"visio_mcp.{name}")


def describe_kinds(provider: str | None = None) -> str:
    return sibling("catalog").describe_kinds(provider)


def rules_text(diagram_type: str, provider: str | None) -> str:
    return sibling("rules").get_rules(diagram_type, provider)


def diagram_types() -> list[str]:
    return [str(t) for t in sibling("rules").TYPES]
