"""DiagramAgent loop driven by scripted fake LLMs, with sibling packages swapped for fakes."""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from typing import Any

import pytest

from visio_mcp.ai.agent import DiagramAgent
from visio_mcp.ai.events import AgentCancelled, AgentError, AgentEvent
from visio_mcp.ai.providers import LLMError, Reply, ToolCall, ToolDef
from visio_mcp.ai.submission import extract_spec


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
    """Stub visio_mcp.repo / rules / lint so the agent is tested in isolation."""
    scanner = types.ModuleType("visio_mcp.repo")
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
    monkeypatch.setitem(sys.modules, "visio_mcp.repo", scanner)
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


def test_extract_spec():
    assert extract_spec("blah " + json.dumps(SPEC) + " trailing").title == "Demo"
    assert extract_spec('{"spec": ' + json.dumps(SPEC) + "}").title == "Demo"
    assert extract_spec("no json {here}") is None
