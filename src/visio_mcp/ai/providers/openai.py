"""OpenAI Chat Completions with function tools: OpenAI, Azure OpenAI and Ollama."""

from __future__ import annotations

import json
from typing import Any

from ..config import DEFAULT_AZURE_API_VERSION, azure_endpoint_root, ollama_base
from .base import Reply, ToolCall, ToolDef, ToolResult, new_call_id
from .errors import SETUP_HINT, LLMError, call_with_retries, short_message

AZURE_SCOPE = "https://cognitiveservices.azure.com/.default"
AZURE_SIGN_IN_HINT = ("run `az login` (and `az account set --subscription ...` for the right tenant), and make sure "
                      "your account has the 'Cognitive Services OpenAI User' role on the Azure OpenAI resource")
# Credential errors from azure-identity, matched by name so the package stays optional for other providers.
SIGN_IN_ERRORS = ("ClientAuthenticationError", "CredentialUnavailableError")


def classify_error(exc: BaseException, provider: str, model: str, signed_in: bool = False) -> LLMError | None:
    import openai

    who = {"azure": "Azure OpenAI", "ollama": "Ollama"}.get(provider, "OpenAI")
    if type(exc).__name__ in SIGN_IN_ERRORS:
        return LLMError("Could not get an Azure sign-in token.", AZURE_SIGN_IN_HINT, "auth")
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        if provider == "azure" and signed_in:
            return LLMError("Azure OpenAI rejected your Azure sign-in.", AZURE_SIGN_IN_HINT, "auth")
        if provider == "azure":
            return LLMError("Azure OpenAI rejected the API key.",
                            "if key access is disabled on the resource, leave the key empty in visio-ai setup "
                            "to use your Azure sign-in (az login)", "auth")
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


def reasoning_rejects_tools(exc: BaseException | None) -> bool:
    """A 400 saying this reasoning model can't use function tools at the requested reasoning effort."""
    if getattr(exc, "status_code", None) != 400:
        return False
    text = short_message(exc, 2000).lower()
    return "reasoning" in text and ("tool" in text or "function" in text)


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
        self.signed_in = False  # Azure: authenticating with an Entra ID token instead of a key

    @classmethod
    def openai(cls, model: str, api_key: str | None, effort: str | None = None) -> OpenAILLM:
        import openai

        return cls(model, openai.OpenAI(api_key=api_key, max_retries=1), "openai", effort)

    @classmethod
    def azure(
        cls, deployment: str, endpoint: str, api_key: str | None, api_version: str | None, effort: str | None = None
    ) -> OpenAILLM:
        """Azure OpenAI with an API key, or with the user's Azure sign-in when there is no key
        (az login, VS Code, managed identity) for resources that have key access disabled."""
        import openai

        auth: dict[str, Any] = {"api_key": api_key} if api_key else {"azure_ad_token_provider": entra_token_provider()}
        client = openai.AzureOpenAI(
            azure_endpoint=azure_endpoint_root(endpoint) or endpoint,
            api_version=api_version or DEFAULT_AZURE_API_VERSION,
            max_retries=1,
            **auth,
        )
        llm = cls(deployment, client, "azure", effort)
        llm.signed_in = not api_key
        return llm

    @classmethod
    def ollama(cls, model: str, base_url: str | None = None) -> OpenAILLM:
        import openai

        base = (base_url or ollama_base()).rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return cls(model, openai.OpenAI(base_url=base, api_key="ollama", max_retries=1), "ollama", None, None)

    def start(self, system: str, tools: list[ToolDef]) -> OpenAISession:
        return OpenAISession(self, system, tools)


def entra_token_provider() -> Any:
    """A bearer-token callable from the user's Azure sign-in (DefaultAzureCredential)."""
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    except ImportError as exc:
        raise LLMError("Azure sign-in needs the azure-identity package.",
                       "reinstall visio-mcp, or set an API key in visio-ai setup", "auth") from exc
    return get_bearer_token_provider(DefaultAzureCredential(), AZURE_SCOPE)


class OpenAISession:
    """History is the native chat messages list (system, user, assistant with tool_calls, tool)."""

    def __init__(self, llm: OpenAILLM, system: str, tools: list[ToolDef]):
        self.llm = llm
        self.effort_override: str | None = None  # set once a reasoning model rejects tools at its default effort
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
        effort = self.effort_override or self.llm.effort
        if effort and self.llm.name in ("openai", "azure"):
            kw["reasoning_effort"] = effort
        return kw

    def _create(self) -> Any:
        kw = self.request_kwargs()
        return call_with_retries(
            lambda: self.llm.client.chat.completions.create(**kw),
            lambda e: classify_error(e, self.llm.name, self.llm.model, self.llm.signed_in),
        )

    def _call(self) -> Reply:
        try:
            resp = self._create()
        except LLMError as err:
            # Some reasoning models refuse function tools unless reasoning is off: retry once with
            # reasoning_effort "none" and keep it for the rest of this session.
            if self.effort_override or not self.tools or not reasoning_rejects_tools(err.__cause__):
                raise
            self.effort_override = "none"
            resp = self._create()
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
