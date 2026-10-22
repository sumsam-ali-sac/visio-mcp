"""AI layer: agent loop with scripted fake LLMs, provider adapters with mocked SDK clients, config."""

from __future__ import annotations

import json
import os
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from visio_mcp.ai import agent as agent_mod
from visio_mcp.ai import config as cfgmod
from visio_mcp.ai import providers as prov
from visio_mcp.ai.agent import AgentCancelled, AgentError, AgentEvent, DiagramAgent, extract_spec
from visio_mcp.ai.providers import LLMError, Reply, ToolCall, ToolDef

# ---------------------------------------------------------------- fakes for sibling modules


@dataclass
class FakeRepo:
    path: str
    name: str
    languages: list[str] = field(default_factory=lambda: ["Python"])
    frameworks: list[str] = field(default_factory=lambda: ["FastAPI"])
    cloud: list[str] = field(default_factory=list)
    summary: str = "demo"
    suggested_types: list[str] = field(default_factory=lambda: ["architecture"])


class FakeFS:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def list_dir(self, rel: str = ".", depth: int = 1) -> str:
        self.calls.append(("list_dir", rel, depth))
        return "api/\nworker/\ndocker-compose.yml"

    def read_file(self, rel: str, start_line: int = 1, max_lines: int = 400) -> str:
        self.calls.append(("read_file", rel, start_line, max_lines))
        if ".." in rel:
            raise ValueError(f"path escapes the workspace: {rel}")
        return f"1: content of {rel}"

    def search(self, pattern: str, glob: str | None = None, max_hits: int = 60) -> str:
        self.calls.append(("search", pattern, glob, max_hits))
        return "api/db.py:3: DATABASE_URL = os.environ['DATABASE_URL']"

    def find_files(self, glob: str, max_hits: int = 200) -> str:
        self.calls.append(("find_files", glob, max_hits))
        return "docker-compose.yml"


@pytest.fixture
def fakes(monkeypatch):
    """Stub visio_mcp.scanner / rules / lint so the agent is tested in isolation."""
    scanner = types.ModuleType("visio_mcp.scanner")
    scanner.RepoFS = lambda roots: FakeFS()  # type: ignore[attr-defined]
    scanner.digest = lambda info, max_chars=12000: f"DIGEST {info.name}"  # type: ignore[attr-defined]
    scanner.workspace_digest = lambda repos, max_chars=20000: "WS " + ",".join(r.name for r in repos)  # type: ignore[attr-defined]
    rules = types.ModuleType("visio_mcp.rules")
    rules.get_rules = lambda t, provider=None: f"RULES-{t}-{provider}"  # type: ignore[attr-defined]
    rules.TYPES = ["architecture", "erd", "pipeline"]  # type: ignore[attr-defined]
    rules.type_summary = lambda: {"architecture": "x"}  # type: ignore[attr-defined]
    lint = types.ModuleType("visio_mcp.lint")
    state: dict[str, Any] = {"findings": lambda spec: []}
    lint.normalize = lambda spec: (spec.model_copy(update={"theme": "pro"}) if spec.theme == "auto" else spec, ["n1"])  # type: ignore[attr-defined]
    lint.lint = lambda spec: state["findings"](spec)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "visio_mcp.scanner", scanner)
    monkeypatch.setitem(sys.modules, "visio_mcp.rules", rules)
    monkeypatch.setitem(sys.modules, "visio_mcp.lint", lint)
    return state


SPEC = {
    "title": "Demo",
    "nodes": [{"id": "api", "label": "Api", "kind": "api"}, {"id": "db", "label": "Db", "kind": "database"}],
    "edges": [{"source": "api", "target": "db", "label": "SQL"}],
}


class FakeSession:
    def __init__(self, script: list[Reply]):
        self.script = list(script)
        self.sent: list[tuple[str, Any]] = []

    def _next(self) -> Reply:
        if not self.script:
            raise AssertionError("script exhausted")
        return self.script.pop(0)

    def send_user(self, text: str) -> Reply:
        self.sent.append(("user", text))
        return self._next()

    def send_tool_results(self, results, text=None) -> Reply:
        self.sent.append(("tools", (results, text)))
        return self._next()


class FakeLLM:
    name = "fake"
    model = "fake-1"

    def __init__(self, script: list[Reply]):
        self.session = FakeSession(script)
        self.system = ""
        self.tools: list[ToolDef] = []

    def start(self, system, tools):
        self.system, self.tools = system, tools
        return self.session


_n = 0


def call(name: str, **args) -> ToolCall:
    global _n
    _n += 1
    return ToolCall(f"c{_n}", name, args)


def tools(*calls: ToolCall, text: str = "") -> Reply:
    return Reply(text, list(calls), "tool_use", {"input_tokens": 10, "output_tokens": 5}, None)


def end(text: str = "") -> Reply:
    return Reply(text, [], "end_turn", {}, None)


def make_agent(script, events=None, **kw) -> tuple[DiagramAgent, FakeLLM]:
    llm = FakeLLM(script)
    repos = kw.pop("repos", [FakeRepo("/tmp/demo", "demo")])
    a = DiagramAgent(llm, repos, on_event=(events.append if events is not None else None), **kw)
    return a, llm


# ---------------------------------------------------------------- agent


def test_end_to_end_tool_dispatch_and_events(fakes):
    events: list[AgentEvent] = []
    script = [
        tools(call("list_dir", path="."), call("read_file", path="api/main.py"),
              call("search", pattern="DATABASE_URL", glob="**/*.py"), call("find_files", glob="**/*.yml"),
              text="Looking around."),
        tools(call("get_rules", diagram_type="erd"), call("list_kinds")),
        tools(call("submit_diagram", **SPEC)),
    ]
    a, llm = make_agent(script, events)
    spec = a.run()
    assert spec.title == "Demo" and spec.theme == "pro"  # normalized
    assert spec.type == "architecture"  # filled from the requested type
    fs = a.fs
    assert ("read_file", "api/main.py", 1, 400) in fs.calls
    assert ("search", "DATABASE_URL", "**/*.py", 60) in fs.calls
    # parallel calls answered in ONE send_tool_results with all results in order
    kind, (results, note) = llm.session.sent[1]
    assert kind == "tools" and [r[0].name for r in results] == ["list_dir", "read_file", "search", "find_files"]
    assert all(not err for _, _, err in results)
    rules_out = llm.session.sent[2][1][0][0][1]
    assert rules_out == "RULES-erd-None"
    assert "database" in llm.session.sent[2][1][0][1][1]  # list_kinds
    # system prompt embeds rules + kinds; first message embeds the digest
    assert "RULES-architecture-None" in llm.system and "database" in llm.system
    assert "DIGEST demo" in llm.session.sent[0][1]
    assert [t.name for t in llm.tools][-1] == "submit_diagram"
    assert "$defs" in llm.tools[-1].schema
    msgs = [(e.kind, e.message) for e in events]
    assert ("tool", "read_file api/main.py") in msgs
    assert ("tool", "search 'DATABASE_URL' in **/*.py") in msgs
    assert any(k == "text" and m == "Looking around." for k, m in msgs)
    kinds = [e.kind for e in events]
    assert kinds[0] == "status" and "draft" in kinds and kinds[-1] == "done"
    assert a.usage["input_tokens"] == 30


def test_tool_errors_become_is_error_results(fakes):
    script = [
        tools(call("read_file", path="../etc/passwd"), call("nope"), call("read_file"),
              ToolCall("x", "search", {"_parse_error": "bad json"})),
        tools(call("submit_diagram", **SPEC)),
    ]
    a, llm = make_agent(script)
    a.run()
    results = llm.session.sent[1][1][0]
    assert [err for _, _, err in results] == [True, True, True, True]
    assert "escapes" in results[0][1] and "unknown tool" in results[1][1] and "bad json" in results[3][1]


def test_invalid_spec_then_resubmit(fakes):
    bad = {"title": "X", "nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "zzz"}]}
    script = [tools(call("submit_diagram", **bad)), tools(call("submit_diagram", spec=json.dumps(SPEC)))]
    a, llm = make_agent(script)
    spec = a.run()
    res = llm.session.sent[1][1][0][0]
    assert res[2] is True and "unknown nodes" in res[1]
    assert len(spec.nodes) == 2


def test_lint_feedback_loop(fakes):
    fakes["findings"] = lambda spec: ["label too long"] if len(spec.nodes) < 3 else []
    better = dict(SPEC, nodes=SPEC["nodes"] + [{"id": "user", "kind": "user"}])
    events: list[AgentEvent] = []
    script = [tools(call("submit_diagram", **SPEC)), tools(call("submit_diagram", **better))]
    a, llm = make_agent(script, events)
    spec = a.run()
    assert len(spec.nodes) == 3
    feedback = llm.session.sent[1][1][0][0]
    assert feedback[2] is False and "label too long" in feedback[1] and "resubmit" in feedback[1]
    assert any(e.kind == "lint" for e in events)
    assert [e.kind for e in events].count("draft") == 2


def test_lint_accepts_same_spec_resubmitted_and_after_two_rounds(fakes):
    fakes["findings"] = lambda spec: ["meh"]
    a, llm = make_agent([tools(call("submit_diagram", **SPEC)), tools(call("submit_diagram", **SPEC))])
    assert a.run().title == "Demo"
    assert len(llm.session.sent) == 2
    other = dict(SPEC, title="Other")
    third = dict(SPEC, title="Third")
    a, llm = make_agent([tools(call("submit_diagram", **SPEC)), tools(call("submit_diagram", **other)),
                         tools(call("submit_diagram", **third))])
    assert a.run().title == "Third"


def test_step_budget_nudge(fakes):
    script = [tools(call("list_dir")) for _ in range(3)] + [tools(call("submit_diagram", **SPEC))]
    a, llm = make_agent(script, max_steps=4)
    a.run()
    notes = [p[1] for k, p in llm.session.sent if k == "tools"]
    assert notes[:2] == [None, None] and "running low on steps" in notes[2]


def test_out_of_steps_raises_without_spec(fakes):
    a, _ = make_agent([tools(call("list_dir")) for _ in range(3)], max_steps=3)
    with pytest.raises(AgentError):
        a.run()


def test_no_submit_nudge_then_json_fallback(fakes):
    text = "Here it is:\n```json\n" + json.dumps(SPEC) + "\n```"
    a, llm = make_agent([end("I think I'm done."), end(text)])
    spec = a.run()
    assert spec.title == "Demo"
    assert "submit_diagram" in llm.session.sent[1][1]


def test_no_submit_nudge_then_tool_call(fakes):
    a, llm = make_agent([end("done"), tools(call("submit_diagram", **SPEC))])
    assert a.run().title == "Demo"


def test_no_submit_no_json_raises(fakes):
    events: list[AgentEvent] = []
    a, _ = make_agent([end("hmm"), end("still no")], events)
    with pytest.raises(AgentError):
        a.run()
    assert events[-1].kind == "error"


def test_refusal_raises(fakes):
    a, _ = make_agent([Reply("no", [], "refusal", {}, None)])
    with pytest.raises(AgentError):
        a.run()


def test_refine_continues_same_session(fakes):
    sub = call("submit_diagram", **SPEC)
    grouped = dict(SPEC, groups=[{"id": "data", "label": "Data"}],
                   nodes=[SPEC["nodes"][0], dict(SPEC["nodes"][1], group="data")], theme="azure")
    script = [tools(sub), tools(call("read_file", path="x.py")), tools(call("submit_diagram", **grouped))]
    a, llm = make_agent(script)
    a.run()
    spec = a.refine("group the databases and use the azure theme")
    assert spec.theme == "azure" and spec.groups[0].id == "data"
    kind, (results, note) = llm.session.sent[1]
    assert kind == "tools" and results[0][0] is sub and "accepted" in results[0][1]
    assert "group the databases" in note and '"Demo"' in note  # feedback + current spec
    assert a.spec is spec


def test_refine_before_run_raises(fakes):
    a, _ = make_agent([])
    with pytest.raises(AgentError):
        a.refine("x")


def test_cancel(fakes):
    a, llm = make_agent([tools(call("list_dir"), call("list_dir"))])
    a.on_event = lambda e: a.cancel() if e.kind == "tool_result" else None
    with pytest.raises(AgentCancelled):
        a.run()
    assert len(a._pending) == 2 and a._pending[1][2] is True


def test_llm_error_emits_event(fakes):
    class Boom(FakeLLM):
        def start(self, system, tools):
            s = FakeSession([])
            s.send_user = lambda text: (_ for _ in ()).throw(LLMError("bad key", "run visio-ai setup", "auth"))
            return s

    events: list[AgentEvent] = []
    a = DiagramAgent(Boom([]), [FakeRepo("/x", "x")], on_event=events.append)
    with pytest.raises(LLMError):
        a.run()
    assert events[-1].kind == "error" and events[-1].detail == "run visio-ai setup"


def test_workspace_digest_and_cloud_hint(fakes):
    repos = [FakeRepo("/a", "a", cloud=["Azure (bicep)"]), FakeRepo("/b", "b", cloud=["azure"])]
    a, llm = make_agent([tools(call("submit_diagram", **SPEC))], repos=repos)
    a.run()
    assert "WS a,b" in llm.session.sent[0][1]
    assert a.provider_hint == "azure" and "RULES-architecture-azure" in llm.system


def test_describe_kinds_fallback(monkeypatch):
    from visio_mcp import catalog

    fake = types.ModuleType("visio_mcp.catalog")
    fake.kinds = catalog.kinds  # type: ignore[attr-defined]  # no describe_kinds
    monkeypatch.setitem(sys.modules, "visio_mcp.catalog", fake)
    out = agent_mod.describe_kinds(None)
    assert "- database:" in out and "- api:" in out


def test_extract_spec():
    assert extract_spec("blah " + json.dumps(SPEC) + " trailing").title == "Demo"
    assert extract_spec('{"spec": ' + json.dumps(SPEC) + "}").title == "Demo"
    assert extract_spec("no json {here}") is None


# ---------------------------------------------------------------- Anthropic adapter


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
    monkeypatch.setattr(prov, "_sleep", sleeps.append)
    ok = _amsg([{"type": "text", "text": "ok"}], stop="end_turn")
    rl = lambda: anthropic.RateLimitError("slow", response=_http(429), body=None)  # noqa: E731
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

    monkeypatch.setattr(prov, "_sleep", lambda s: None)
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

    monkeypatch.setattr(prov, "_sleep", lambda s: None)
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


# ---------------------------------------------------------------- config


def test_config_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "config.toml"
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", path)
    cfg = cfgmod.AppConfig(
        provider=cfgmod.ProviderConfig("azure", "dep", api_key='s"k\\1\n', endpoint="https://e", deployment="dep",
                                       api_version="2025-04-01-preview", effort="medium"),
        theme="azure", out_dir="C:\\Users\\me\\out", live=False, attach=True, recent_paths=["/a", "/b ü"],
    )
    cfgmod.save_config(cfg)
    assert cfgmod.load_config() == cfg
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600
    assert cfgmod.load_config(tmp_path / "missing.toml") == cfgmod.AppConfig()
    (tmp_path / "bad.toml").write_text("this is = = not toml")
    assert cfgmod.load_config(tmp_path / "bad.toml") == cfgmod.AppConfig()


def test_key_never_in_repr():
    p = cfgmod.ProviderConfig("anthropic", "claude-opus-5-5", api_key="sk-secret-123")
    a = cfgmod.AppConfig(provider=p)
    for s in (repr(p), str(p), repr(a), str(a), p.label):
        assert "sk-secret-123" not in s
    assert "***" in repr(p)


def test_detect_providers_and_resolve_key(monkeypatch):
    for v in list(os.environ):
        if v.startswith(("ANTHROPIC", "OPENAI", "AZURE_OPENAI", "GEMINI", "GOOGLE_API")):
            monkeypatch.delenv(v)
    assert cfgmod.detect_providers(probe_ollama=False) == []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "z")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://e")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "dep")
    found = {p.provider: p for p in cfgmod.detect_providers(probe_ollama=False)}
    assert set(found) == {"anthropic", "gemini", "azure"}
    assert found["anthropic"].model == "claude-opus-5-5" and found["anthropic"].api_key is None
    assert found["azure"].deployment == "dep" and found["azure"].api_version == cfgmod.DEFAULT_AZURE_API_VERSION
    assert cfgmod.resolve_key(found["gemini"]) == "g"
    assert cfgmod.resolve_key(cfgmod.ProviderConfig("gemini", "x", api_key="cfg")) == "cfg"
    assert cfgmod.resolve_key(cfgmod.ProviderConfig("openai", "x")) is None
    assert cfgmod.suggested_models("anthropic")[0] == "claude-opus-5-5"
    assert "claude-fable-5-1" in cfgmod.suggested_models("anthropic")
    assert cfgmod.suggested_models("azure") == ["dep"]


def test_detect_ollama_probe(monkeypatch):
    for v in list(os.environ):
        if v.startswith(("ANTHROPIC", "OPENAI", "AZURE_OPENAI", "GEMINI", "GOOGLE_API", "OLLAMA")):
            monkeypatch.delenv(v)

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"models": [{"name": "llama3.1:latest"}]}'

    seen = []
    monkeypatch.setattr(cfgmod.urllib.request, "urlopen", lambda url, timeout: seen.append(timeout) or R())
    found = cfgmod.detect_providers()
    assert found[0].provider == "ollama" and found[0].model == "llama3.1:latest"
    assert all(t <= 0.3 for t in seen)


def test_config_dir_platforms(monkeypatch, tmp_path):
    monkeypatch.setattr(cfgmod.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cfgmod._config_dir() == tmp_path / "visio-mcp"
    monkeypatch.setattr(cfgmod.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    assert cfgmod._config_dir() == tmp_path / "AppData" / "visio-mcp"
    monkeypatch.setattr(cfgmod.sys, "platform", "darwin")
    assert cfgmod._config_dir() == Path.home() / "Library" / "Application Support" / "visio-mcp"
