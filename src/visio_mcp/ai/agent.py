"""DiagramAgent: explores local repos with read-only tools and returns a DiagramSpec."""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from visio_mcp.spec import DiagramSpec

from . import prompts
from .events import AgentCancelled, AgentError, AgentEvent, EventKind
from .providers import LLM, LLMError, Reply, Session, ToolCall, ToolDef, ToolResult
from .siblings import describe_kinds, rules_text, sibling
from .submission import Submissions, extract_spec
from .text import clip
from .tools import SUBMIT, describe_call, run_tool, tool_defs

MAX_TOOL_OUTPUT = 24000  # chars per tool result sent back to the model


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
        self.fs = fs if fs is not None else sibling("repo").RepoFS([Path(r.path) for r in self.repos])
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
            rules_text(self.diagram_type, self.provider_hint),
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
        self._emit("status", f"Refining: {clip(feedback, 80)}")
        msg = prompts.refine_message(feedback, self.spec.model_dump_json(exclude_defaults=True))
        pending, self._pending = self._pending, []
        if pending:
            return self._loop(lambda s: s.send_tool_results(pending, msg))
        return self._loop(lambda s: s.send_user(msg))

    def cancel(self) -> None:
        """Stop at the next step (between model calls / tool calls)."""
        self._cancel.set()

    def tools(self) -> list[ToolDef]:
        return tool_defs()

    # ------------------------------------------------------------ loop

    def _reset_round(self) -> None:
        self._steps = 0
        self._submissions = Submissions(self.diagram_type)
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
            self._emit("thinking", clip(reply.thinking, 240), reply.thinking)
        if reply.text:
            self._texts.append(reply.text)
            self._emit("text", clip(reply.text, 240), reply.text)
        return reply

    def _loop(self, first: Callable[[Session], Reply]) -> DiagramSpec:
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
        if self._submissions.last_valid is not None:
            self._emit("status", "Step budget used up; keeping the last valid submission")
            return self._accept(self._submissions.last_valid, results)
        return self._fallback(results)

    def _fallback(self, pending: list[ToolResult]) -> DiagramSpec:
        self._pending = pending
        if self._submissions.last_valid is not None:
            return self._accept(self._submissions.last_valid, pending)
        for text in reversed(self._texts):
            spec = extract_spec(text)
            if spec is not None:
                self._emit("status", "Model did not call submit_diagram; using the JSON spec from its reply")
                spec, _ = self._submissions.normalize(spec)
                self._emit("draft", f"Draft: {len(spec.nodes)} nodes", spec.model_dump_json(exclude_defaults=True))
                return self._accept(spec, pending)
        self._emit("error", "The model did not submit a diagram.")
        raise AgentError("The model finished without submitting a diagram. Try again, or pick a stronger model.")

    # ------------------------------------------------------------ tool calls

    def _dispatch(self, call: ToolCall) -> tuple[str, bool, DiagramSpec | None]:
        """Run one tool call -> (output, is_error, accepted spec or None)."""
        args = call.args or {}
        self._emit("tool", describe_call(call), json.dumps(args)[:2000] if call.name != SUBMIT else "")
        if "_parse_error" in args:
            return self._result(call, f"Could not parse your tool arguments: {args['_parse_error']}", True)
        try:
            if call.name == SUBMIT:
                out, is_err, spec = self._submissions.submit(args, self._emit)
                return self._result(call, out, is_err, spec)
            out = run_tool(self.fs, call.name, args, self.diagram_type, self.provider_hint)
        except (ValueError, KeyError, TypeError, OSError, LookupError) as exc:
            return self._result(call, f"{type(exc).__name__}: {exc}", True)
        return self._result(call, out, False)

    def _result(self, call: ToolCall, out: str, is_err: bool, spec: DiagramSpec | None = None):
        out = str(out)
        if len(out) > MAX_TOOL_OUTPUT:
            out = out[:MAX_TOOL_OUTPUT] + f"\n… [truncated {len(out) - MAX_TOOL_OUTPUT} chars; narrow the request]"
        first = out.strip().splitlines()[0] if out.strip() else "(empty)"
        lines = out.count("\n") + 1 if out else 0
        msg = f"{call.name}: " + ("error: " + clip(first, 120) if is_err else f"{lines} lines")
        if call.name == SUBMIT:
            msg = f"submit_diagram: {clip(first, 140)}"
        self._emit("tool_result", msg, out[:4000])
        return out, is_err, spec

    # ------------------------------------------------------------ helpers

    def _digest(self) -> str:
        try:
            repo = sibling("repo")
            if len(self.repos) == 1:
                return repo.digest(self.repos[0])
            return repo.workspace_digest(self.repos)
        except Exception as exc:  # noqa: BLE001 - the digest is a convenience, never fatal
            self._emit("status", f"Could not build the workspace digest ({exc}); exploring from scratch")
            return "\n".join(f"- {getattr(r, 'name', '?')}: {getattr(r, 'path', '?')}" for r in self.repos)

    def _emit(self, kind: EventKind, message: str, detail: str = "") -> None:
        if self.on_event is not None:
            try:
                self.on_event(AgentEvent(kind, message, detail))
            except Exception:  # noqa: BLE001 - a UI bug must not kill the agent
                pass
