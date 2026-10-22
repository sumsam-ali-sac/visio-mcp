"""Provider-neutral types: tool definitions, replies, and the LLM / Session protocols.

Each provider keeps its own native message history inside a Session, so provider-specific
parts (Anthropic thinking blocks with signatures, Gemini function-call parts with thought
signatures, OpenAI tool_call ids) round-trip unchanged. The agent only sees ToolCall/Reply.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolDef:
    name: str
    description: str
    schema: dict  # JSON schema of the arguments object


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]
    stop: str  # 'tool_use' | 'end_turn' | 'max_tokens' | 'refusal' | 'pause_turn' | other
    usage: dict = field(default_factory=dict)
    raw: Any = None
    thinking: str = ""  # summarized reasoning, when the provider returns it


ToolResult = tuple[ToolCall, str, bool]  # (call, output text, is_error)


class Session(Protocol):
    def send_user(self, text: str) -> Reply: ...

    def send_tool_results(self, results: list[ToolResult], text: str | None = None) -> Reply:
        """Answer every tool call of the last reply; `text` is appended as a user note."""
        ...


class LLM(Protocol):
    name: str
    model: str

    def start(self, system: str, tools: list[ToolDef]) -> Session: ...


def new_call_id() -> str:
    return "call_" + uuid.uuid4().hex[:12]
