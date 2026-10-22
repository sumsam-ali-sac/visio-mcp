"""Anthropic Messages API with tool use, prompt caching and adaptive thinking."""

from __future__ import annotations

from typing import Any

from .base import Reply, ToolCall, ToolDef, ToolResult
from .errors import SETUP_HINT, LLMError, call_with_retries, short_message


def classify_error(exc: BaseException, model: str) -> LLMError | None:
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return LLMError("Anthropic rejected the API key.", SETUP_HINT, "auth")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return LLMError(f"Anthropic denied access: {short_message(exc)}", SETUP_HINT, "auth")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError("Anthropic rate limit reached; try again shortly.", "wait a minute or lower effort", "rate_limit")
    if isinstance(exc, anthropic.NotFoundError):
        return LLMError(f"Model '{model}' was not found.", "pick another model in visio-ai setup", "not_found")
    if isinstance(exc, anthropic.APIConnectionError):  # includes APITimeoutError
        return LLMError("Could not reach the Anthropic API.", "check your network or proxy", "connection")
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", 0) or 0
        if status in (429, 529, 503):  # overloaded
            return LLMError("Anthropic is overloaded; try again shortly.", "wait a minute", "rate_limit")
        if status == 400:
            return LLMError(f"Anthropic rejected the request: {short_message(exc)}", "", "bad_request")
        return LLMError(f"Anthropic API error {status}: {short_message(exc)}", "", "error")
    return None


class AnthropicLLM:
    name = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        effort: str | None = "high",
        max_tokens: int = 32000,
        client: Any = None,
    ):
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key, max_retries=1)
        self.client = client

    def start(self, system: str, tools: list[ToolDef]) -> AnthropicSession:
        return AnthropicSession(self, system, tools)


class AnthropicSession:
    """History is the native messages list; assistant turns keep response.content as-is
    (thinking blocks with signatures included), tool results go back in one user message."""

    def __init__(self, llm: AnthropicLLM, system: str, tools: list[ToolDef]):
        self.llm = llm
        # The system prompt is large and identical every turn: cache tools + system.
        self.system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        self.tools = [{"name": t.name, "description": t.description, "input_schema": t.schema} for t in tools]
        if self.tools:
            self.tools[-1]["cache_control"] = {"type": "ephemeral"}
        self.messages: list[dict] = []

    def send_user(self, text: str) -> Reply:
        self.messages.append({"role": "user", "content": [{"type": "text", "text": text}]})
        return self._call()

    def send_tool_results(self, results: list[ToolResult], text: str | None = None) -> Reply:
        blocks: list[dict] = [
            {"type": "tool_result", "tool_use_id": call.id, "content": out or "(empty)", "is_error": bool(err)}
            for call, out, err in results
        ]
        if text:
            blocks.append({"type": "text", "text": text})
        self.messages.append({"role": "user", "content": blocks})
        return self._call()

    def _mark_cache(self) -> None:
        # One moving breakpoint on the newest user turn caches the growing conversation
        # (system + this = 2 of the 4 allowed breakpoints).
        for m in self.messages:
            if m["role"] == "user" and isinstance(m["content"], list):
                for b in m["content"]:
                    if isinstance(b, dict):
                        b.pop("cache_control", None)
        last = self.messages[-1]
        if last["role"] == "user" and last["content"] and isinstance(last["content"][-1], dict):
            last["content"][-1]["cache_control"] = {"type": "ephemeral"}

    def request_kwargs(self) -> dict:
        kw: dict[str, Any] = {
            "model": self.llm.model,
            "max_tokens": self.llm.max_tokens,
            "system": self.system,
            "tools": self.tools,
            "tool_choice": {"type": "auto"},
            "messages": self.messages,
        }
        if self.llm.effort:
            kw["output_config"] = {"effort": self.llm.effort}
        return kw

    def _call(self) -> Reply:
        self._mark_cache()
        kw = self.request_kwargs()

        def go() -> Any:
            with self.llm.client.messages.stream(**kw) as stream:
                return stream.get_final_message()

        msg = call_with_retries(go, lambda e: classify_error(e, self.llm.model))
        # Pass the content back unchanged (thinking blocks must keep their signatures).
        self.messages.append({"role": "assistant", "content": msg.content})
        texts, thinking, calls = [], [], []
        for b in msg.content:
            t = getattr(b, "type", None)
            if t == "text":
                texts.append(b.text)
            elif t == "thinking":
                thinking.append(getattr(b, "thinking", "") or "")
            elif t == "tool_use":
                calls.append(ToolCall(b.id, b.name, dict(b.input or {})))
        u = getattr(msg, "usage", None)
        usage = {}
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "input_tokens", 0) or 0,
                "output_tokens": getattr(u, "output_tokens", 0) or 0,
                "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
            }
        return Reply("\n".join(texts).strip(), calls, msg.stop_reason or "end_turn", usage, msg, "\n".join(thinking).strip())
