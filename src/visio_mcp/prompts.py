"""Authoring instructions shipped with the server, so any MCP client knows how to use it.  (F4: implement)"""

from __future__ import annotations

from typing import Literal

GUIDE = "TODO"


def diagram_prompt(subject: str, source: Literal["prompt", "repo"] = "prompt") -> str:
    """Instructions for drawing `subject`, from a description or by exploring a repo."""
    raise NotImplementedError
