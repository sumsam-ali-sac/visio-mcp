"""DiagramAgent: explores local repos with read-only tools and returns a DiagramSpec."""

from __future__ import annotations

import importlib
import json
import math
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from visio_mcp.ai import prompts
from visio_mcp.ai.providers import LLM, Reply, Session, ToolCall, ToolDef, ToolResult
from visio_mcp.spec import DiagramSpec

EventKind = Literal["status", "thinking", "tool", "tool_result", "text", "draft", "lint", "done", "error"]

MAX_TOOL_OUTPUT = 24000  # chars per tool result sent back to the model
MAX_LINT_ROUNDS = 2  # lint findings are returned on the first two submissions


@dataclass
class AgentEvent:
    kind: EventKind
    message: str
    detail: str = ""


class AgentError(Exception):
    """The agent could not produce a diagram."""


class AgentCancelled(AgentError):
    """cancel() was called."""


def _mod(name: str) -> Any:
    """Import a sibling module lazily (scanner/rules/lint/catalog may be swapped in tests)."""
    return importlib.import_module(f"visio_mcp.{name}")


def describe_kinds(provider: str | None = None) -> str:
    catalog = _mod("catalog")
    fn = getattr(catalog, "describe_kinds", None)
    if callable(fn):
        return fn(provider)
    lines = []
    for k in catalog.kinds().values():
        kp = getattr(k, "provider", None)
        if kp and provider and kp != provider:
            continue
        if kp and not provider:
            continue
        lines.append(f"- {k.name}: {k.description}")
    return "\n".join(lines)


def _rules_text(diagram_type: str, provider: str | None) -> str:
    try:
        return _mod("rules").get_rules(diagram_type, provider)
    except (ImportError, AttributeError):
        return ""


def _diagram_types() -> list[str]:
    try:
        types = getattr(_mod("rules"), "TYPES", None)
        if types:
            return [str(t) for t in types]
    except ImportError:
        pass
    return [t for t in DiagramSpec.model_fields["type"].annotation.__args__ if t != "auto"]  # type: ignore[union-attr]


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _cloud_hint(repos: list[Any]) -> str | None:
    seen: set[str] = set()
    for r in repos:
        cloud = getattr(r, "cloud", None) or []
        if isinstance(cloud, str):
            cloud = [cloud]
        for c in cloud:
            low = str(c).lower()
            for p in ("azure", "aws", "gcp"):
                if p in low:
                    seen.add(p)
    return seen.pop() if len(seen) == 1 else None


def _validation_message(exc: ValidationError) -> str:
    lines = []
    for e in exc.errors()[:20]:
        loc = ".".join(str(x) for x in e.get("loc", ()))
        lines.append(f"- {loc or 'spec'}: {e.get('msg')}")
    return "\n".join(lines)


def extract_spec(text: str) -> DiagramSpec | None:
    """Find a DiagramSpec JSON object in free text (fenced block or bare object); last valid wins."""
    candidates: list[str] = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
            candidates.append(json.dumps(obj))
            i = text.find("{", end)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
    found = None
    for c in candidates:
        try:
            data = json.loads(c)
            if isinstance(data, dict) and isinstance(data.get("spec"), dict):
                data = data["spec"]
            found = DiagramSpec.model_validate(data)
        except (ValueError, ValidationError):
            continue
    return found


class DiagramAgent:
    def __init__(
        self,
        llm: LLM,
        repos: list[Any],
        diagram_type: str = "architecture",
        focus: str = "",
        provider_hint: str | None = None,
        on_event: Callable[[AgentEvent], None] | None = None,
        max_steps: int = 40,
        fs: Any = None,
    ):
        self.llm = llm
        self.repos = list(repos)
        self.diagram_type = diagram_type
        self.focus = focus
        self.provider_hint = provider_hint if provider_hint is not None else _cloud_hint(self.repos)
        self.on_event = on_event
        self.max_steps = max_steps
        self.fs = fs if fs is not None else _mod("scanner").RepoFS([Path(r.path) for r in self.repos])
        self.spec: DiagramSpec | None = None  # last accepted spec
        self.usage: dict[str, int] = {}
        self._session: Session | None = None
        self._pending: list[ToolResult] = []  # results owed for the last turn (after accept)
        self._cancel = threading.Event()
        self._reset_round()

    # ------------------------------------------------------------ public

    def run(self) -> DiagramSpec:
        """Explore the repos and return the accepted, normalized spec."""
        self._cancel.clear()
        self._reset_round()
        system = prompts.build_system_prompt(
            self.diagram_type,
            _rules_text(self.diagram_type, self.provider_hint),
            describe_kinds(self.provider_hint),
            self.provider_hint,
        )
        names = [getattr(r, "name", str(getattr(r, "path", "repo"))) for r in self.repos]
        self._emit("status", f"Exploring {', '.join(names) or 'workspace'} with {self.llm.name} / {self.llm.model}")
        self._session = self.llm.start(system, self.tools())
        digest = self._digest()
        first = prompts.first_message(digest, self.diagram_type, self.focus, names)
        return self._loop(lambda s: s.send_user(first))

    def refine(self, feedback: str) -> DiagramSpec:
        """Continue the same conversation with a change request; returns the new spec."""
        if self._session is None or self.spec is None:
            raise AgentError("Nothing to refine yet: run() first.")
        self._cancel.clear()
        self._reset_round()
        self._emit("status", f"Refining: {_clip(feedback, 80)}")
        msg = prompts.refine_message(feedback, self.spec.model_dump_json(exclude_defaults=True))
        pending, self._pending = self._pending, []
        if pending:
            return self._loop(lambda s: s.send_tool_results(pending, msg))
        return self._loop(lambda s: s.send_user(msg))

    def cancel(self) -> None:
        """Stop at the next step (between model calls / tool calls)."""
        self._cancel.set()

    def tools(self) -> list[ToolDef]:
        types = _diagram_types()
        return [
            ToolDef("list_dir", "List a folder of the workspace (read-only). Paths are relative to the workspace root.",
                    {"type": "object", "properties": {
                        "path": {"type": "string", "description": "Folder, default '.'."},
                        "depth": {"type": "integer", "description": "Levels to show, 1-3. Default 1."}}}),
            ToolDef("read_file", "Read part of a text file with line numbers. Read only what you need.",
                    {"type": "object", "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer", "description": "1-based, default 1."},
                        "max_lines": {"type": "integer", "description": "Default 400."}},
                     "required": ["path"]}),
            ToolDef("search", "Regex search across the workspace text files; returns path:line: text hits.",
                    {"type": "object", "properties": {
                        "pattern": {"type": "string", "description": "Python regex, e.g. 'DATABASE_URL|REDIS_URL'."},
                        "glob": {"type": "string", "description": "Optional file filter, e.g. '**/*.py'."},
                        "max_hits": {"type": "integer", "description": "Default 60."}},
                     "required": ["pattern"]}),
            ToolDef("find_files", "Find files by glob, e.g. '**/docker-compose*.yml' or '**/*.tf'.",
                    {"type": "object", "properties": {
                        "glob": {"type": "string"},
                        "max_hits": {"type": "integer", "description": "Default 200."}},
                     "required": ["glob"]}),
            ToolDef("get_rules", "Ground rules for a diagram type (those for the requested type are already in "
                    "your instructions).",
                    {"type": "object", "properties": {"diagram_type": {"type": "string", "enum": types}},
                     "required": ["diagram_type"]}),
            ToolDef("list_kinds", "Node kinds usable in the spec; pass a cloud provider (azure, aws, gcp) for its "
                    "service icons.",
                    {"type": "object", "properties": {"provider": {"type": "string", "enum": ["azure", "aws", "gcp"]}}}),
            ToolDef("submit_diagram", "Submit the finished diagram. The arguments ARE the DiagramSpec object. "
                    "Returns validation errors or lint findings to fix, or 'accepted'.",
                    DiagramSpec.model_json_schema()),
        ]

    # ------------------------------------------------------------ loop

    def _reset_round(self) -> None:
        self._steps = 0
        self._submissions = 0
        self._last_submitted: dict | None = None
        self._last_valid: DiagramSpec | None = None
        self._budget_nudged = False
        self._submit_nudged = False
        self._texts: list[str] = []

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            self._emit("error", "Cancelled")
            raise AgentCancelled("cancelled")

    def _model(self, fn: Callable[[Session], Reply]) -> Reply:
        self._check_cancel()
        assert self._session is not None
        self._steps += 1
        reply = fn(self._session)
        for k, v in (reply.usage or {}).items():
            if isinstance(v, int):
                self.usage[k] = self.usage.get(k, 0) + v
        if reply.thinking:
            self._emit("thinking", _clip(reply.thinking, 240), reply.thinking)
        if reply.text:
            self._texts.append(reply.text)
            self._emit("text", _clip(reply.text, 240), reply.text)
        return reply

    def _loop(self, first: Callable[[Session], Reply]) -> DiagramSpec:
        from visio_mcp.ai.providers import LLMError

        try:
            return self._loop_inner(first)
        except LLMError as exc:
            self._emit("error", exc.message, exc.hint)
            raise

    def _loop_inner(self, first: Callable[[Session], Reply]) -> DiagramSpec:
        self._pending = []
        reply = self._model(first)
        while True:
            if reply.stop == "refusal" and not reply.tool_calls:
                self._emit("error", "The model declined this request.", reply.text)
                raise AgentError("The model declined to produce this diagram.")
            if reply.tool_calls:
                results: list[ToolResult] = []
                accepted: DiagramSpec | None = None
                for i, call in enumerate(reply.tool_calls):
                    if self._cancel.is_set():
                        # Owe an answer for every call so the session can still be refined later.
                        self._pending = results + [(c, "cancelled by the user", True) for c in reply.tool_calls[i:]]
                        self._check_cancel()
                    out, is_err, spec = self._dispatch(call)
                    if spec is not None:
                        accepted = spec
                    results.append((call, out, is_err))
                if accepted is not None:
                    return self._accept(accepted, results)
                if self._steps >= self.max_steps:
                    return self._out_of_steps(results)
                note = None
                if not self._budget_nudged and self._steps >= math.ceil(self.max_steps * 0.75):
                    self._budget_nudged = True
                    note = prompts.NUDGE_BUDGET
                    self._emit("status", "Running low on steps; asking the model to submit")
                if self._cancel.is_set():
                    self._pending = results
                    self._check_cancel()
                reply = self._model(lambda s, r=results, n=note: s.send_tool_results(r, n))
                continue
            # The model ended its turn without calling a tool.
            if self._steps >= self.max_steps or self._submit_nudged:
                return self._fallback([])
            self._submit_nudged = True
            self._emit("status", "Asking the model to submit the diagram")
            reply = self._model(lambda s: s.send_user(prompts.NUDGE_SUBMIT))

    def _accept(self, spec: DiagramSpec, results: list[ToolResult]) -> DiagramSpec:
        self._pending = results  # answered at the start of refine()
        self.spec = spec
        self._emit("done", f"{spec.title}: {len(spec.nodes)} nodes, {len(spec.edges)} edges, "
                   f"{len(spec.groups)} groups", spec.model_dump_json(indent=1, exclude_defaults=True))
        return spec

    def _out_of_steps(self, results: list[ToolResult]) -> DiagramSpec:
        if self._last_valid is not None:
            self._emit("status", "Step budget used up; keeping the last valid submission")
            return self._accept(self._last_valid, results)
        return self._fallback(results)

    def _fallback(self, pending: list[ToolResult]) -> DiagramSpec:
        self._pending = pending
        if self._last_valid is not None:
            return self._accept(self._last_valid, pending)
        for text in reversed(self._texts):
            spec = extract_spec(text)
            if spec is not None:
                self._emit("status", "Model did not call submit_diagram; using the JSON spec from its reply")
                spec, _ = self._normalize(spec)
                self._emit("draft", f"Draft: {len(spec.nodes)} nodes", spec.model_dump_json(exclude_defaults=True))
                return self._accept(spec, pending)
        self._emit("error", "The model did not submit a diagram.")
        raise AgentError("The model finished without submitting a diagram. Try again, or pick a stronger model.")

    # ------------------------------------------------------------ tools

    def _dispatch(self, call: ToolCall) -> tuple[str, bool, DiagramSpec | None]:
        """Run one tool call -> (output, is_error, accepted spec or None)."""
        args = call.args or {}
        self._emit("tool", self._describe(call), json.dumps(args)[:2000] if call.name != "submit_diagram" else "")
        if "_parse_error" in args:
            return self._result(call, f"Could not parse your tool arguments: {args['_parse_error']}", True)
        try:
            if call.name == "submit_diagram":
                return self._submit(call, args)
            out = self._run_tool(call.name, args)
        except (ValueError, KeyError, TypeError, OSError, LookupError) as exc:
            return self._result(call, f"{type(exc).__name__}: {exc}", True)
        return self._result(call, out, False)

    def _result(self, call: ToolCall, out: str, is_err: bool, spec: DiagramSpec | None = None):
        out = str(out)
        if len(out) > MAX_TOOL_OUTPUT:
            out = out[:MAX_TOOL_OUTPUT] + f"\n… [truncated {len(out) - MAX_TOOL_OUTPUT} chars; narrow the request]"
        first = out.strip().splitlines()[0] if out.strip() else "(empty)"
        lines = out.count("\n") + 1 if out else 0
        msg = f"{call.name}: " + ("error: " + _clip(first, 120) if is_err else f"{lines} lines")
        if call.name == "submit_diagram":
            msg = f"submit_diagram: {_clip(first, 140)}"
        self._emit("tool_result", msg, out[:4000])
        return out, is_err, spec

    def _run_tool(self, name: str, a: dict) -> str:
        fs = self.fs
        if name == "list_dir":
            return fs.list_dir(str(a.get("path") or a.get("rel") or "."), int(a.get("depth") or 1))
        if name == "read_file":
            path = a.get("path") or a.get("rel")
            if not path:
                raise ValueError("read_file needs 'path'")
            return fs.read_file(str(path), int(a.get("start_line") or 1), int(a.get("max_lines") or 400))
        if name == "search":
            if not a.get("pattern"):
                raise ValueError("search needs 'pattern'")
            return fs.search(str(a["pattern"]), a.get("glob") or None, int(a.get("max_hits") or 60))
        if name == "find_files":
            if not a.get("glob"):
                raise ValueError("find_files needs 'glob'")
            return fs.find_files(str(a["glob"]), int(a.get("max_hits") or 200))
        if name == "get_rules":
            t = str(a.get("diagram_type") or self.diagram_type)
            return _mod("rules").get_rules(t, a.get("provider") or self.provider_hint) or "(no rules)"
        if name == "list_kinds":
            return describe_kinds(a.get("provider") or None)
        raise ValueError(f"unknown tool '{name}'. Available: list_dir, read_file, search, find_files, "
                         "get_rules, list_kinds, submit_diagram")

    def _submit(self, call: ToolCall, args: dict) -> tuple[str, bool, DiagramSpec | None]:
        data: Any = args
        if set(args) == {"spec"}:  # tolerate {"spec": {...}} or {"spec": "<json>"}
            data = args["spec"]
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as exc:
                    return self._result(call, f"spec is not valid JSON: {exc}", True)
        try:
            raw = DiagramSpec.model_validate(data)
        except ValidationError as exc:
            return self._result(
                call, "The spec is invalid. Fix these and call submit_diagram again with the full spec:\n"
                + _validation_message(exc), True)
        self._submissions += 1
        same_as_before = self._last_submitted is not None and raw.model_dump() == self._last_submitted
        self._last_submitted = raw.model_dump()
        spec, notes = self._normalize(raw)
        self._last_valid = spec
        self._emit("draft", f"Draft {self._submissions}: {len(spec.nodes)} nodes, {len(spec.edges)} edges",
                   spec.model_dump_json(exclude_defaults=True))
        findings = list(_mod("lint").lint(spec))
        if findings and self._submissions <= MAX_LINT_ROUNDS and not same_as_before:
            self._emit("lint", f"{len(findings)} rule finding(s); asking the model to fix", "\n".join(findings))
            text = (
                "The spec is valid but breaks these diagram rules:\n"
                + "\n".join(f"- {f}" for f in findings)
                + "\n\nFix them and call submit_diagram again with the complete spec. If you judge a "
                "finding acceptable here, resubmit the same spec unchanged."
            )
            if notes:
                text += "\n\nNormalization notes: " + "; ".join(notes)
            return self._result(call, text, False)
        if findings:
            self._emit("lint", f"Accepted with {len(findings)} finding(s)", "\n".join(findings))
        return self._result(call, "accepted: the diagram is being drawn.", False, spec)

    def _normalize(self, spec: DiagramSpec) -> tuple[DiagramSpec, list[str]]:
        if spec.type == "auto" and self.diagram_type != "auto":
            try:
                spec = spec.model_copy(update={"type": self.diagram_type})
            except ValueError:
                pass
        spec, notes = _mod("lint").normalize(spec)
        return spec, list(notes or [])

    # ------------------------------------------------------------ helpers

    def _digest(self) -> str:
        try:
            scanner = _mod("scanner")
            if len(self.repos) == 1:
                return scanner.digest(self.repos[0])
            return scanner.workspace_digest(self.repos)
        except Exception as exc:  # noqa: BLE001 - the digest is a convenience, never fatal
            self._emit("status", f"Could not build the workspace digest ({exc}); exploring from scratch")
            return "\n".join(f"- {getattr(r, 'name', '?')}: {getattr(r, 'path', '?')}" for r in self.repos)

    @staticmethod
    def _describe(call: ToolCall) -> str:
        a = call.args or {}
        n = call.name
        if n == "read_file":
            extra = f" @{a['start_line']}" if a.get("start_line") not in (None, 1) else ""
            return f"read_file {a.get('path', '?')}{extra}"
        if n == "list_dir":
            return f"list_dir {a.get('path') or '.'}"
        if n == "search":
            g = f" in {a['glob']}" if a.get("glob") else ""
            return f"search '{_clip(str(a.get('pattern', '')), 60)}'{g}"
        if n == "find_files":
            return f"find_files {a.get('glob', '?')}"
        if n == "get_rules":
            return f"get_rules {a.get('diagram_type', '')}"
        if n == "list_kinds":
            return f"list_kinds {a.get('provider') or ''}".strip()
        if n == "submit_diagram":
            body = a.get("spec") if isinstance(a.get("spec"), dict) else a
            nodes = body.get("nodes")
            return f"submit_diagram ({len(nodes) if isinstance(nodes, list) else 0} nodes)"
        return n

    def _emit(self, kind: EventKind, message: str, detail: str = "") -> None:
        if self.on_event is not None:
            try:
                self.on_event(AgentEvent(kind, message, detail))
            except Exception:  # noqa: BLE001 - a UI bug must not kill the agent
                pass
