"""Coercion of parsed YAML/JSON values to lists, and unique appends."""

from __future__ import annotations

from typing import Any


def as_list(v: Any) -> list[Any]:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def as_str_list(v: Any) -> list[str]:
    if isinstance(v, dict):
        return [str(k) for k in v]
    return [str(x) for x in as_list(v) if x is not None and not isinstance(x, (dict, list))]


def add_unique(lst: list[str], item: str) -> None:
    if item and item not in lst:
        lst.append(item)
