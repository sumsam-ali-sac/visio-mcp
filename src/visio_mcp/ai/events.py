"""What the agent reports while it works, and the errors it can end with."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EventKind = Literal["status", "thinking", "tool", "tool_result", "text", "draft", "lint", "done", "error"]


@dataclass
class AgentEvent:
    kind: EventKind
    message: str
    detail: str = ""


class AgentError(Exception):
    """The agent could not produce a diagram."""


class AgentCancelled(AgentError):
    """cancel() was called."""
