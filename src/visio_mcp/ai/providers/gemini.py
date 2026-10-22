"""Google Gemini (google-genai SDK) with function calling."""

from __future__ import annotations

from typing import Any

from .base import Reply, ToolCall, ToolDef, ToolResult, new_call_id
from .errors import SETUP_HINT, LLMError, call_with_retries, short_message
from .gemini_schema import gemini_schema


def classify_error(exc: BaseException, model: str) -> LLMError | None:
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", 0) or 0
        msg = short_message(exc)
        low = msg.lower()
        if code in (401, 403) or "api key" in low or "api_key" in low:
            return LLMError("Gemini rejected the API key.", SETUP_HINT, "auth")
        if code == 429 or getattr(exc, "status", "") == "RESOURCE_EXHAUSTED":
            return LLMError("Gemini rate limit or quota reached; try again shortly.", "wait a minute", "rate_limit")
        if code == 404:
            return LLMError(f"Model '{model}' was not found on Gemini.", "pick another model in visio-ai setup", "not_found")
        if code in (500, 503):
            return LLMError("Gemini is overloaded; try again shortly.", "wait a minute", "rate_limit")
        if code == 400:
            return LLMError(f"Gemini rejected the request: {msg}", "", "bad_request")
        return LLMError(f"Gemini API error {code}: {msg}", "", "error")
    name = type(exc).__name__
    if "Connect" in name or "Timeout" in name or isinstance(exc, (ConnectionError, TimeoutError)):
        return LLMError("Could not reach the Gemini API.", "check your network or proxy", "connection")
    return None


class GeminiLLM:
    name = "gemini"

    def __init__(self, model: str, api_key: str | None = None, client: Any = None, max_tokens: int = 32000):
        self.model = model
        self.max_tokens = max_tokens
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self.client = client

    def start(self, system: str, tools: list[ToolDef]) -> GeminiSession:
        return GeminiSession(self, system, tools)


class GeminiSession:
    """History is a list of genai Content; model turns are appended exactly as returned so
    function-call parts and thought signatures round-trip."""

    def __init__(self, llm: GeminiLLM, system: str, tools: list[ToolDef]):
        from google.genai import types

        self.llm = llm
        self.types = types
        decls = [
            types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=gemini_schema(t.schema))
            for t in tools
        ]
        self.config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=decls)] if decls else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=llm.max_tokens,
        )
        self.contents: list[Any] = []
        self._native_ids: dict[str, str | None] = {}  # our id -> Gemini's id (may be None)

    def send_user(self, text: str) -> Reply:
        t = self.types
        self.contents.append(t.Content(role="user", parts=[t.Part.from_text(text=text)]))
        return self._call()

    def send_tool_results(self, results: list[ToolResult], text: str | None = None) -> Reply:
        t = self.types
        parts = []
        for call, out, err in results:
            payload = {"error": out} if err else {"output": out}
            parts.append(t.Part(function_response=t.FunctionResponse(
                id=self._native_ids.get(call.id), name=call.name, response=payload)))
        if text:
            parts.append(t.Part.from_text(text=text))
        self.contents.append(t.Content(role="user", parts=parts))
        return self._call()

    def _call(self) -> Reply:
        resp = call_with_retries(
            lambda: self.llm.client.models.generate_content(
                model=self.llm.model, contents=self.contents, config=self.config
            ),
            lambda e: classify_error(e, self.llm.model),
        )
        cands = getattr(resp, "candidates", None) or []
        cand = cands[0] if cands else None
        content = getattr(cand, "content", None)
        texts, thinking, calls = [], [], []
        if content is not None and content.parts:
            self.contents.append(content)
            for p in content.parts:
                if getattr(p, "function_call", None) is not None:
                    fc = p.function_call
                    our = fc.id or new_call_id()
                    self._native_ids[our] = fc.id
                    calls.append(ToolCall(our, fc.name or "", dict(fc.args or {})))
                elif getattr(p, "text", None):
                    (thinking if getattr(p, "thought", False) else texts).append(p.text)
        finish = str(getattr(getattr(cand, "finish_reason", None), "name", getattr(cand, "finish_reason", "")) or "")
        if calls:
            stop = "tool_use"
        elif finish == "MAX_TOKENS":
            stop = "max_tokens"
        elif cand is None or finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
            stop = "refusal"
        else:
            stop = "end_turn"
        um = getattr(resp, "usage_metadata", None)
        usage = {}
        if um is not None:
            usage = {"input_tokens": getattr(um, "prompt_token_count", 0) or 0,
                     "output_tokens": getattr(um, "candidates_token_count", 0) or 0}
        return Reply("\n".join(texts).strip(), calls, stop, usage, resp, "\n".join(thinking).strip())
