"""OpenAI Chat Completions with function tools: OpenAI, Azure OpenAI and Ollama."""

from __future__ import annotations

import json
from typing import Any

from ..config import DEFAULT_AZURE_API_VERSION, ollama_base
from .base import Reply, ToolCall, ToolDef, ToolResult, new_call_id
from .errors import SETUP_HINT, LLMError, call_with_retries, short_message


def classify_error(exc: BaseException, provider: str, model: str) -> LLMError | None:
    import openai

    who = {"azure": "Azure OpenAI", "ollama": "Ollama"}.get(provider, "OpenAI")
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return LLMError(f"{who} rejected the API key.", SETUP_HINT, "auth")
    if isinstance(exc, openai.RateLimitError):
        return LLMError(f"{who} rate limit reached; try again shortly.", "wait a minute", "rate_limit")
    if isinstance(exc, openai.NotFoundError):
        hint = {
            "azure": "check the deployment name and endpoint in visio-ai setup",
            "ollama": f"run: ollama pull {model}",
        }.get(provider, "pick another model in visio-ai setup")
        return LLMError(f"Model '{model}' was not found on {who}.", hint, "not_found")
    if isinstance(exc, openai.APIConnectionError):
        hint = "start it with: ollama serve" if provider == "ollama" else "check your network, proxy or endpoint"
        return LLMError(f"Could not reach {who}.", hint, "connection")
    if isinstance(exc, openai.APIStatusError):
        status = getattr(exc, "status_code", 0) or 0
        if status in (429, 503):
            return LLMError(f"{who} is overloaded; try again shortly.", "wait a minute", "rate_limit")
        if status == 400:
            return LLMError(f"{who} rejected the request: {short_message(exc)}", "", "bad_request")
        return LLMError(f"{who} API error {status}: {short_message(exc)}", "", "error")
    return None


FINISH = {"tool_calls": "tool_use", "function_call": "tool_use", "stop": "end_turn", "length": "max_tokens",
           "content_filter": "refusal"}


class OpenAILLM:
    """Chat Completions with function tools: works for OpenAI, Azure OpenAI and Ollama."""

    def __init__(
        self,
        model: str,
        client: Any,
        provider: str = "openai",
        effort: str | None = None,
        max_tokens: int | None = 32000,
    ):
        self.name = provider
        self.model = model
        self.client = client
        self.effort = effort
        self.max_tokens = max_tokens

    @classmethod
    def openai(cls, model: str, api_key: str | None, effort: str | None = None) -> OpenAILLM:
        import openai

        return cls(model, openai.OpenAI(api_key=api_key, max_retries=1), "openai", effort)

    @classmethod
    def azure(
        cls, deployment: str, endpoint: str, api_key: str | None, api_version: str | None, effort: str | None = None
    ) -> OpenAILLM:
        import openai

        client = openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version or DEFAULT_AZURE_API_VERSION,
            api_key=api_key,
            max_retries=1,
        )
        return cls(deployment, client, "azure", effort)

    @classmethod
    def ollama(cls, model: str, base_url: str | None = None) -> OpenAILLM:
        import openai

        base = (base_url or ollama_base()).rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return cls(model, openai.OpenAI(base_url=base, api_key="ollama", max_retries=1), "ollama", None, None)

    def start(self, system: str, tools: list[ToolDef]) -> OpenAISession:
        return OpenAISession(self, system, tools)


class OpenAISession:
    """History is the native chat messages list (system, user, assistant with tool_calls, tool)."""

    def __init__(self, llm: OpenAILLM, system: str, tools: list[ToolDef]):
        self.llm = llm
        self.messages: list[dict] = [{"role": "system", "content": system}]
        # Not strict mode: the spec schema has optional fields and $defs.
        self.tools = [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema}}
            for t in tools
        ]

    def send_user(self, text: str) -> Reply:
        self.messages.append({"role": "user", "content": text})
        return self._call()

    def send_tool_results(self, results: list[ToolResult], text: str | None = None) -> Reply:
        for call, out, err in results:
            content = out or "(empty)"
            if err:
                content = "ERROR: " + content
            self.messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
        if text:
            self.messages.append({"role": "user", "content": text})
        return self._call()

    def request_kwargs(self) -> dict:
        kw: dict[str, Any] = {"model": self.llm.model, "messages": self.messages}
        if self.tools:
            kw["tools"] = self.tools
            kw["tool_choice"] = "auto"
        if self.llm.max_tokens and self.llm.name in ("openai", "azure"):
            kw["max_completion_tokens"] = self.llm.max_tokens
        if self.llm.effort and self.llm.name in ("openai", "azure"):
            kw["reasoning_effort"] = self.llm.effort
        return kw

    def _call(self) -> Reply:
        kw = self.request_kwargs()
        resp = call_with_retries(
            lambda: self.llm.client.chat.completions.create(**kw),
            lambda e: classify_error(e, self.llm.name, self.llm.model),
        )
        if not getattr(resp, "choices", None):
            raise LLMError(f"{self.llm.name} returned no choices.", "", "error")
        choice = resp.choices[0]
        msg = choice.message
        calls: list[ToolCall] = []
        native_calls: list[dict] = []
        for tc in msg.tool_calls or []:
            fn = getattr(tc, "function", None)
            if fn is None:  # custom tool calls are not used here
                continue
            tid = tc.id or new_call_id()
            raw_args = fn.arguments or "{}"
            try:
                args = json.loads(raw_args)
                if not isinstance(args, dict):
                    args = {"_parse_error": f"arguments must be a JSON object, got {type(args).__name__}"}
            except json.JSONDecodeError as exc:
                args = {"_parse_error": f"invalid JSON arguments: {exc}"}
            calls.append(ToolCall(tid, fn.name, args))
            native_calls.append({"id": tid, "type": "function", "function": {"name": fn.name, "arguments": raw_args}})
        hist: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if native_calls:
            hist["tool_calls"] = native_calls
        self.messages.append(hist)
        u = getattr(resp, "usage", None)
        usage = {}
        if u is not None:
            usage = {"input_tokens": getattr(u, "prompt_tokens", 0) or 0,
                     "output_tokens": getattr(u, "completion_tokens", 0) or 0}
        stop = FINISH.get(choice.finish_reason or "", choice.finish_reason or "end_turn")
        if calls:
            stop = "tool_use"
        if getattr(msg, "refusal", None):
            stop = "refusal"
        thinking = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
        text = (msg.content or "") if not getattr(msg, "refusal", None) else msg.refusal
        return Reply(text.strip(), calls, stop, usage, resp, str(thinking).strip())
