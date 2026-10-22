"""Provider-neutral chat with tools.

Each provider keeps its own native message history inside a Session, so provider-specific
parts (Anthropic thinking blocks with signatures, Gemini function-call parts with thought
signatures, OpenAI tool_call ids) round-trip unchanged. The agent only sees ToolCall/Reply.

SDKs are imported lazily so the app starts fast and works with only one SDK installed.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar

from visio_mcp.ai.config import (
    DEFAULT_AZURE_API_VERSION,
    ProviderConfig,
    ollama_base,
    resolve_key,
)

T = TypeVar("T")

SETUP_HINT = "check your API key: run visio-ai setup"
RETRY_DELAYS: tuple[float, ...] = (2.0, 5.0, 12.0)  # backoff for rate limits / overload, 3 retries
_sleep: Callable[[float], None] = time.sleep  # patched in tests


# ---------------------------------------------------------------- neutral types


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


class LLMError(Exception):
    """A friendly, user-facing model error."""

    def __init__(self, message: str, hint: str = "", kind: str = "error"):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.kind = kind  # 'auth' | 'rate_limit' | 'connection' | 'not_found' | 'bad_request' | 'error'

    def __str__(self) -> str:
        return f"{self.message} ({self.hint})" if self.hint else self.message


def _call_with_retries(fn: Callable[[], T], classify: Callable[[BaseException], LLMError | None]) -> T:
    """Run fn; map SDK errors to LLMError; retry rate limits / overload with backoff."""
    attempt = 0
    while True:
        try:
            return fn()
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - classified below
            err = classify(exc)
            if err is None:
                raise
            if err.kind == "rate_limit" and attempt < len(RETRY_DELAYS):
                _sleep(RETRY_DELAYS[attempt])
                attempt += 1
                continue
            raise err from exc


def _short(exc: BaseException, limit: int = 300) -> str:
    msg = getattr(exc, "message", None) or str(exc)
    msg = " ".join(str(msg).split())
    return msg[:limit]


def _new_id() -> str:
    return "call_" + uuid.uuid4().hex[:12]


# ---------------------------------------------------------------- Anthropic


def _classify_anthropic(exc: BaseException, model: str) -> LLMError | None:
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return LLMError("Anthropic rejected the API key.", SETUP_HINT, "auth")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return LLMError(f"Anthropic denied access: {_short(exc)}", SETUP_HINT, "auth")
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
            return LLMError(f"Anthropic rejected the request: {_short(exc)}", "", "bad_request")
        return LLMError(f"Anthropic API error {status}: {_short(exc)}", "", "error")
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

        msg = _call_with_retries(go, lambda e: _classify_anthropic(e, self.llm.model))
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


# ---------------------------------------------------------------- OpenAI / Azure / Ollama


def _classify_openai(exc: BaseException, provider: str, model: str) -> LLMError | None:
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
            return LLMError(f"{who} rejected the request: {_short(exc)}", "", "bad_request")
        return LLMError(f"{who} API error {status}: {_short(exc)}", "", "error")
    return None


_FINISH = {"tool_calls": "tool_use", "function_call": "tool_use", "stop": "end_turn", "length": "max_tokens",
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
        resp = _call_with_retries(
            lambda: self.llm.client.chat.completions.create(**kw),
            lambda e: _classify_openai(e, self.llm.name, self.llm.model),
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
            tid = tc.id or _new_id()
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
        stop = _FINISH.get(choice.finish_reason or "", choice.finish_reason or "end_turn")
        if calls:
            stop = "tool_use"
        if getattr(msg, "refusal", None):
            stop = "refusal"
        thinking = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
        text = (msg.content or "") if not getattr(msg, "refusal", None) else msg.refusal
        return Reply(text.strip(), calls, stop, usage, resp, str(thinking).strip())


# ---------------------------------------------------------------- Gemini

# Keys Gemini's function-declaration schema accepts (an OpenAPI 3 subset).
_GEMINI_KEYS = {"type", "description", "enum", "items", "properties", "required", "format", "nullable",
                "minimum", "maximum"}


def gemini_schema(schema: dict) -> dict:
    """Simplify a JSON schema for Gemini: inline $ref/$defs, collapse anyOf-with-null,
    turn const into enum, drop keys Gemini rejects (additionalProperties, title, default,
    pattern, $schema...)."""
    defs = schema.get("$defs") or schema.get("definitions") or {}

    def walk(node: Any, seen: tuple[str, ...]) -> Any:
        if isinstance(node, list):
            return [walk(x, seen) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = str(node["$ref"]).split("/")[-1]
            if name in seen or name not in defs:
                return {"type": "object", "description": node.get("description", name)}
            merged = {**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}
            return walk(merged, seen + (name,))
        for key in ("anyOf", "oneOf"):
            if key in node:
                options = [o for o in node[key] if not (isinstance(o, dict) and o.get("type") == "null")]
                base = {k: v for k, v in node.items() if k != key}
                if options:
                    picked = walk(options[0], seen)
                    if isinstance(picked, dict):
                        out = {**picked, **walk(base, seen)}
                        if "description" in picked and "description" in base:
                            out["description"] = base["description"]
                        return out
                return walk({**base, "type": "string"}, seen)
        if "allOf" in node and isinstance(node["allOf"], list) and node["allOf"]:
            merged: dict = {}
            for part in node["allOf"]:
                p = walk(part, seen)
                if isinstance(p, dict):
                    merged.update(p)
            rest = {k: v for k, v in node.items() if k != "allOf"}
            return {**merged, **walk(rest, seen)}
        out: dict[str, Any] = {}
        if "const" in node:
            out["enum"] = [node["const"]]
        typ = node.get("type")
        if isinstance(typ, list):  # ["string", "null"]
            non_null = [t for t in typ if t != "null"]
            typ = non_null[0] if non_null else "string"
        for k, v in node.items():
            if k not in _GEMINI_KEYS:
                continue
            if k == "type":
                out["type"] = typ
            elif k == "properties":
                out["properties"] = {pk: walk(pv, seen) for pk, pv in v.items()}
            elif k == "items":
                out["items"] = walk(v, seen)
            elif k == "enum":
                out["enum"] = [str(x) for x in v if x is not None]
            else:
                out[k] = v
        if "enum" in out:
            out["type"] = "string"
        if "properties" in out:
            out.setdefault("type", "object")
            if "required" in out:
                out["required"] = [r for r in out["required"] if r in out["properties"]]
        if out.get("type") == "object" and not out.get("properties"):
            # Gemini rejects empty objects; an object with no fields is passed as free text.
            out.pop("required", None)
        if out.get("type") == "array" and "items" not in out:
            out["items"] = {"type": "string"}
        return out

    return walk({k: v for k, v in schema.items() if k not in ("$defs", "definitions")}, ())


def _classify_gemini(exc: BaseException, model: str) -> LLMError | None:
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", 0) or 0
        msg = _short(exc)
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
        resp = _call_with_retries(
            lambda: self.llm.client.models.generate_content(
                model=self.llm.model, contents=self.contents, config=self.config
            ),
            lambda e: _classify_gemini(e, self.llm.model),
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
                    our = fc.id or _new_id()
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


# ---------------------------------------------------------------- factory


def make_llm(cfg: ProviderConfig) -> LLM:
    """Build the LLM for a provider config. Raises LLMError when settings are missing."""
    key = resolve_key(cfg)
    if cfg.provider == "anthropic":
        if not key:
            raise LLMError("No Anthropic API key found.", "run visio-ai setup or set ANTHROPIC_API_KEY", "auth")
        return AnthropicLLM(cfg.model or "claude-opus-5-5", key, effort=cfg.effort or "high")
    if cfg.provider == "openai":
        if not key:
            raise LLMError("No OpenAI API key found.", "run visio-ai setup or set OPENAI_API_KEY", "auth")
        return OpenAILLM.openai(cfg.model, key, effort=cfg.effort)
    if cfg.provider == "azure":
        import os

        endpoint = cfg.endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        deployment = cfg.deployment or cfg.model or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        version = cfg.api_version or os.environ.get("AZURE_OPENAI_API_VERSION")
        if not key:
            raise LLMError("No Azure OpenAI API key found.", "run visio-ai setup or set AZURE_OPENAI_API_KEY", "auth")
        if not endpoint or not deployment:
            raise LLMError("Azure OpenAI needs an endpoint and a deployment name.",
                           "run visio-ai setup or set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_DEPLOYMENT", "error")
        return OpenAILLM.azure(deployment, endpoint, key, version, effort=cfg.effort)
    if cfg.provider == "gemini":
        if not key:
            raise LLMError("No Gemini API key found.", "run visio-ai setup or set GEMINI_API_KEY", "auth")
        return GeminiLLM(cfg.model, key)
    if cfg.provider == "ollama":
        return OpenAILLM.ollama(cfg.model, cfg.endpoint)
    raise LLMError(f"Unknown provider '{cfg.provider}'.", "choose anthropic, openai, azure, gemini or ollama")


__all__ = [
    "LLM", "LLMError", "Reply", "Session", "ToolCall", "ToolDef", "ToolResult",
    "AnthropicLLM", "OpenAILLM", "GeminiLLM", "gemini_schema", "make_llm",
]
