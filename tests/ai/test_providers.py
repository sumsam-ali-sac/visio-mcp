"""Provider adapters with mocked SDK clients: message translation, errors and retries, the factory."""

from __future__ import annotations

import json
import types
from typing import Any

import pytest

from visio_mcp.ai import config as cfgmod
from visio_mcp.ai import providers as prov
from visio_mcp.ai.providers import LLMError, ToolDef
from visio_mcp.ai.providers import errors as prov_errors


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeAnthropicClient:
    def __init__(self, messages: list[Any]):
        self.queue = list(messages)
        self.requests: list[dict] = []
        self.messages = self

    def stream(self, **kw):
        self.requests.append(json.loads(json.dumps(kw, default=lambda o: o.model_dump())))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Stream(item)


def _amsg(content: list[dict], stop="tool_use"):
    import anthropic

    return anthropic.types.Message.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": content, "stop_reason": stop, "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 80},
    })


def test_anthropic_translation():
    m1 = _amsg([
        {"type": "thinking", "thinking": "plan it", "signature": "sig123"},
        {"type": "text", "text": "Reading files."},
        {"type": "tool_use", "id": "tu1", "name": "read_file", "input": {"path": "a.py"}},
        {"type": "tool_use", "id": "tu2", "name": "search", "input": {"pattern": "x"}},
    ])
    m2 = _amsg([{"type": "text", "text": "done"}], stop="end_turn")
    client = FakeAnthropicClient([m1, m2])
    llm = prov.AnthropicLLM("claude-opus-5-5", effort="high", client=client)
    s = llm.start("SYSTEM", [ToolDef("read_file", "d", {"type": "object", "properties": {}}),
                             ToolDef("search", "d", {"type": "object", "properties": {}})])
    r = s.send_user("hi")
    assert r.stop == "tool_use" and r.text == "Reading files." and r.thinking == "plan it"
    assert [(c.id, c.name, c.args) for c in r.tool_calls] == [("tu1", "read_file", {"path": "a.py"}),
                                                              ("tu2", "search", {"pattern": "x"})]
    assert r.usage["cache_read_input_tokens"] == 80
    req = client.requests[0]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    assert req["output_config"] == {"effort": "high"} and req["max_tokens"] == 32000
    assert req["tool_choice"] == {"type": "auto"}
    for banned in ("thinking", "temperature", "top_p"):
        assert banned not in req
    r2 = s.send_tool_results([(r.tool_calls[0], "file text", False), (r.tool_calls[1], "boom", True)], "hurry")
    assert r2.stop == "end_turn" and r2.text == "done"
    req2 = client.requests[1]
    assistant, user = req2["messages"][1], req2["messages"][2]
    assert assistant["content"][0]["type"] == "thinking" and assistant["content"][0]["signature"] == "sig123"
    assert [b["type"] for b in user["content"]] == ["tool_result", "tool_result", "text"]
    assert user["content"][1]["is_error"] is True and user["content"][0]["tool_use_id"] == "tu1"
    assert user["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in req2["messages"][0]["content"][0]  # moved to the newest turn


def _http(code):
    import httpx2

    return httpx2.Response(code, request=httpx2.Request("POST", "https://api.example"))


def test_anthropic_errors(monkeypatch):
    import anthropic

    sleeps: list[float] = []
    monkeypatch.setattr(prov_errors, "sleep", sleeps.append)
    ok = _amsg([{"type": "text", "text": "ok"}], stop="end_turn")
    rl = lambda: anthropic.RateLimitError("slow", response=_http(429), body=None)
    client = FakeAnthropicClient([rl(), rl(), ok])
    assert prov.AnthropicLLM("m", client=client).start("s", []).send_user("x").text == "ok"
    assert len(sleeps) == 2
    client = FakeAnthropicClient([rl(), rl(), rl(), rl()])
    with pytest.raises(LLMError) as ei:
        prov.AnthropicLLM("m", client=client).start("s", []).send_user("x")
    assert ei.value.kind == "rate_limit"
    client = FakeAnthropicClient([anthropic.AuthenticationError("bad", response=_http(401), body=None)])
    with pytest.raises(LLMError) as ei:
        prov.AnthropicLLM("m", client=client).start("s", []).send_user("x")
    assert ei.value.kind == "auth" and "visio-ai setup" in ei.value.hint
    client = FakeAnthropicClient([anthropic.NotFoundError("nf", response=_http(404), body=None)])
    with pytest.raises(LLMError) as ei:
        prov.AnthropicLLM("claude-x", client=client).start("s", []).send_user("x")
    assert ei.value.kind == "not_found" and "claude-x" in ei.value.message
    import httpx2

    client = FakeAnthropicClient([anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))])
    with pytest.raises(LLMError) as ei:
        prov.AnthropicLLM("m", client=client).start("s", []).send_user("x")
    assert ei.value.kind == "connection"


# ---------------------------------------------------------------- OpenAI adapter


class FakeOpenAIClient:
    def __init__(self, responses):
        self.queue = list(responses)
        self.requests: list[dict] = []
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kw):
        self.requests.append(json.loads(json.dumps(kw)))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ocomp(content=None, tool_calls=None, finish="tool_calls"):
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "gpt-5",
        "choices": [{"index": 0, "finish_reason": finish, "message": {
            "role": "assistant", "content": content, "tool_calls": tool_calls}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 7, "total_tokens": 57},
    })


def test_openai_translation():
    r1 = _ocomp(None, [
        {"id": "t1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}},
        {"id": "t2", "type": "function", "function": {"name": "search", "arguments": "{oops"}},
    ])
    r2 = _ocomp("all done", None, "stop")
    client = FakeOpenAIClient([r1, r2])
    schema = {"type": "object", "$defs": {"N": {"type": "object"}}, "properties": {"n": {"$ref": "#/$defs/N"}}}
    llm = prov.OpenAILLM("gpt-5", client, "openai", effort="medium")
    s = llm.start("SYS", [ToolDef("submit_diagram", "d", schema)])
    r = s.send_user("go")
    assert r.stop == "tool_use" and r.usage == {"input_tokens": 50, "output_tokens": 7}
    assert r.tool_calls[0].args == {"path": "a.py"} and "_parse_error" in r.tool_calls[1].args
    req = client.requests[0]
    assert req["messages"][0] == {"role": "system", "content": "SYS"}
    fn = req["tools"][0]["function"]
    assert fn["parameters"] == schema and "strict" not in fn
    assert req["reasoning_effort"] == "medium" and req["max_completion_tokens"] == 32000
    out = s.send_tool_results([(r.tool_calls[0], "text", False), (r.tool_calls[1], "bad", True)], "note")
    assert out.text == "all done" and out.stop == "end_turn"
    msgs = client.requests[1]["messages"]
    assert msgs[2]["role"] == "assistant" and msgs[2]["tool_calls"][1]["function"]["arguments"] == "{oops"
    assert msgs[3] == {"role": "tool", "tool_call_id": "t1", "content": "text"}
    assert msgs[4] == {"role": "tool", "tool_call_id": "t2", "content": "ERROR: bad"}
    assert msgs[5] == {"role": "user", "content": "note"}


def test_openai_ollama_and_azure_construction(monkeypatch):
    import openai

    made: list[tuple[str, dict]] = []

    class Rec:
        def __init__(self, name):
            self.name = name

        def __call__(self, **kw):
            made.append((self.name, kw))
            return FakeOpenAIClient([])

    monkeypatch.setattr(openai, "OpenAI", Rec("openai"))
    monkeypatch.setattr(openai, "AzureOpenAI", Rec("azure"))
    llm = prov.make_llm(cfgmod.ProviderConfig("ollama", "qwen3:latest"))
    assert made[-1][1]["base_url"] == "http://localhost:11434/v1" and made[-1][1]["api_key"] == "ollama"
    req = llm.start("s", []).request_kwargs()
    assert "max_completion_tokens" not in req and "reasoning_effort" not in req
    llm = prov.make_llm(cfgmod.ProviderConfig("azure", "", api_key="k", endpoint="https://e.openai.azure.com",
                                              deployment="gpt5dep", api_version="2025-04-01-preview"))
    name, kw = made[-1]
    assert name == "azure" and kw["azure_endpoint"] == "https://e.openai.azure.com" and kw["api_key"] == "k"
    assert llm.model == "gpt5dep" and llm.name == "azure"


def test_openai_errors(monkeypatch):
    import openai

    monkeypatch.setattr(prov_errors, "sleep", lambda s: None)
    client = FakeOpenAIClient([openai.AuthenticationError("bad", response=_http(401), body=None)])
    with pytest.raises(LLMError) as ei:
        prov.OpenAILLM("gpt-5", client).start("s", []).send_user("x")
    assert ei.value.kind == "auth"
    client = FakeOpenAIClient([openai.NotFoundError("nf", response=_http(404), body=None)])
    with pytest.raises(LLMError) as ei:
        prov.OpenAILLM("qwen3", client, "ollama").start("s", []).send_user("x")
    assert "ollama pull qwen3" in ei.value.hint
    client = FakeOpenAIClient([openai.RateLimitError("rl", response=_http(429), body=None), _ocomp("ok", None, "stop")])
    assert prov.OpenAILLM("gpt-5", client).start("s", []).send_user("x").text == "ok"


# ---------------------------------------------------------------- Gemini adapter


def test_gemini_schema_simplifier():
    from visio_mcp.spec import DiagramSpec

    s = prov.gemini_schema(DiagramSpec.model_json_schema())
    dumped = json.dumps(s)
    for bad in ("$defs", "$ref", "anyOf", "additionalProperties", '"title": "', '"default"', '"pattern"'):
        assert bad not in dumped
    node = s["properties"]["nodes"]["items"]
    assert node["properties"]["fill"]["type"] == "string"
    assert node["required"] == ["id"]
    assert s["properties"]["nodes"]["type"] == "array"
    assert prov.gemini_schema({"type": "object", "properties": {"c": {"const": "x"}, "t": {"type": ["integer", "null"]}}}) \
        == {"type": "object", "properties": {"c": {"enum": ["x"], "type": "string"}, "t": {"type": "integer"}}}


class FakeGeminiClient:
    def __init__(self, responses):
        self.queue = list(responses)
        self.calls: list[dict] = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_gemini_translation():
    from google.genai import types as gt

    fc_part = gt.Part(function_call=gt.FunctionCall(name="read_file", args={"path": "a.py"}),
                      thought_signature=b"sig")
    r1 = gt.GenerateContentResponse(candidates=[gt.Candidate(
        content=gt.Content(role="model", parts=[gt.Part(text="hmm", thought=True), gt.Part(text="Reading."), fc_part]),
        finish_reason=gt.FinishReason.STOP)],
        usage_metadata=gt.GenerateContentResponseUsageMetadata(prompt_token_count=11, candidates_token_count=3))
    r2 = gt.GenerateContentResponse(candidates=[gt.Candidate(
        content=gt.Content(role="model", parts=[gt.Part(text="ok")]), finish_reason=gt.FinishReason.STOP)])
    client = FakeGeminiClient([r1, r2])
    llm = prov.GeminiLLM("gemini-2.5-pro", client=client)
    from visio_mcp.spec import DiagramSpec

    s = llm.start("SYS", [ToolDef("submit_diagram", "d", DiagramSpec.model_json_schema())])
    r = s.send_user("go")
    assert r.stop == "tool_use" and r.text == "Reading." and r.thinking == "hmm"
    assert r.tool_calls[0].name == "read_file" and r.tool_calls[0].args == {"path": "a.py"}
    cfg = client.calls[0]["config"]
    assert cfg.system_instruction == "SYS" and cfg.automatic_function_calling.disable is True
    assert "$defs" not in json.dumps(cfg.tools[0].function_declarations[0].parameters_json_schema)
    r2_ = s.send_tool_results([(r.tool_calls[0], "content", False)], "note")
    assert r2_.text == "ok" and r2_.stop == "end_turn"
    contents = client.calls[1]["contents"]
    assert contents[1].parts[2].thought_signature == b"sig"  # model turn preserved as returned
    resp_parts = contents[2].parts
    assert resp_parts[0].function_response.name == "read_file"
    assert resp_parts[0].function_response.response == {"output": "content"}
    assert resp_parts[1].text == "note"


def test_gemini_errors(monkeypatch):
    from google.genai import errors

    monkeypatch.setattr(prov_errors, "sleep", lambda s: None)
    client = FakeGeminiClient([errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid",
                                                                    "status": "INVALID_ARGUMENT"}})])
    with pytest.raises(LLMError) as ei:
        prov.GeminiLLM("g", client=client).start("s", []).send_user("x")
    assert ei.value.kind == "auth"
    client = FakeGeminiClient([errors.ClientError(429, {"error": {"code": 429, "message": "q",
                                                                    "status": "RESOURCE_EXHAUSTED"}})] * 4)
    with pytest.raises(LLMError) as ei:
        prov.GeminiLLM("g", client=client).start("s", []).send_user("x")
    assert ei.value.kind == "rate_limit" and len(client.calls) == 4


def test_make_llm_missing_key(monkeypatch):
    for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    for p in ("anthropic", "openai", "gemini"):
        with pytest.raises(LLMError) as ei:
            prov.make_llm(cfgmod.ProviderConfig(p, "m"))
        assert ei.value.kind == "auth"


def test_make_llm_anthropic(monkeypatch):
    import anthropic

    seen = {}
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: seen.update(kw) or object())
    llm = prov.make_llm(cfgmod.ProviderConfig("anthropic", "claude-opus-5-5", api_key="sk-x"))
    assert seen["api_key"] == "sk-x" and llm.effort == "high" and llm.model == "claude-opus-5-5"


# ---------------------------------------------------------------- Azure sign-in (Entra ID)


def _azure_recorder(monkeypatch):
    import openai

    made: list[dict] = []

    def rec(**kw):
        made.append(kw)
        return FakeOpenAIClient([])

    monkeypatch.setattr(openai, "AzureOpenAI", rec)
    return made


def test_azure_without_key_uses_entra_sign_in(monkeypatch):
    made = _azure_recorder(monkeypatch)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    token = object()
    monkeypatch.setattr(prov.openai, "entra_token_provider", lambda: token)
    llm = prov.make_llm(cfgmod.ProviderConfig("azure", "", endpoint="https://e.openai.azure.com/openai/v1/",
                                              deployment="dep"))
    kw = made[-1]
    assert kw["azure_ad_token_provider"] is token and "api_key" not in kw
    assert kw["azure_endpoint"] == "https://e.openai.azure.com"  # the portal's /openai/v1 URL is normalized
    assert llm.signed_in


def test_azure_with_key_does_not_sign_in(monkeypatch):
    made = _azure_recorder(monkeypatch)
    monkeypatch.setattr(prov.openai, "entra_token_provider", lambda: pytest.fail("no sign-in with a key"))
    llm = prov.make_llm(cfgmod.ProviderConfig("azure", "", api_key="k", endpoint="https://e.openai.azure.com",
                                              deployment="dep"))
    assert made[-1]["api_key"] == "k" and not llm.signed_in


def test_azure_sign_in_errors_point_to_az_login(monkeypatch):
    import openai

    monkeypatch.setattr(prov_errors, "sleep", lambda s: None)

    class ClientAuthenticationError(Exception):  # azure.core's credential error, matched by name
        pass

    llm = prov.OpenAILLM("dep", FakeOpenAIClient([ClientAuthenticationError("no account")]), "azure")
    llm.signed_in = True
    with pytest.raises(LLMError) as ei:
        llm.start("s", []).send_user("x")
    assert ei.value.kind == "auth" and "az login" in ei.value.hint
    assert "Cognitive Services OpenAI User" in ei.value.hint

    llm = prov.OpenAILLM("dep", FakeOpenAIClient([openai.PermissionDeniedError("no", response=_http(403), body=None)]),
                         "azure")
    llm.signed_in = True
    with pytest.raises(LLMError) as ei:
        llm.start("s", []).send_user("x")
    assert "sign-in" in ei.value.message and "Cognitive Services OpenAI User" in ei.value.hint

    keyed = prov.OpenAILLM("dep", FakeOpenAIClient([openai.AuthenticationError("bad", response=_http(401), body=None)]),
                           "azure")
    with pytest.raises(LLMError) as ei:
        keyed.start("s", []).send_user("x")
    assert "API key" in ei.value.message and "az login" in ei.value.hint


# ---------------------------------------------------------------- reasoning models and function tools


def _bad_request(msg: str):
    import openai

    return openai.BadRequestError(msg, response=_http(400), body=None)


def test_reasoning_model_rejecting_tools_retries_without_reasoning(monkeypatch):
    err = _bad_request("Function tools with reasoning_effort are not supported for gpt-6-luna in /v1/chat/completions.")
    client = FakeOpenAIClient([err, _ocomp("first", None, "stop"), _ocomp("second", None, "stop")])
    s = prov.OpenAILLM("gpt-6-luna", client, "azure").start("s", [ToolDef("t", "d", {"type": "object"})])
    assert s.send_user("x").text == "first"
    assert "reasoning_effort" not in client.requests[0]
    assert client.requests[1]["reasoning_effort"] == "none"
    assert s.send_user("y").text == "second"
    assert client.requests[2]["reasoning_effort"] == "none"  # remembered for the session


def test_other_bad_requests_are_not_retried():
    client = FakeOpenAIClient([_bad_request("messages[1].content is too long")])
    s = prov.OpenAILLM("gpt-6-luna", client, "azure").start("s", [ToolDef("t", "d", {"type": "object"})])
    with pytest.raises(LLMError) as ei:
        s.send_user("x")
    assert ei.value.kind == "bad_request" and len(client.requests) == 1


def test_reasoning_retry_happens_once():
    err = "Function tools with reasoning_effort are not supported for this model."
    client = FakeOpenAIClient([_bad_request(err), _bad_request(err)])
    s = prov.OpenAILLM("m", client, "openai", effort="high").start("s", [ToolDef("t", "d", {"type": "object"})])
    with pytest.raises(LLMError):
        s.send_user("x")
    assert [r.get("reasoning_effort") for r in client.requests] == ["high", "none"]
