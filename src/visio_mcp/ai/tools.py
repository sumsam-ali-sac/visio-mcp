"""The tools the model can call: definitions, execution against the sandboxed RepoFS, and call descriptions."""

from __future__ import annotations

from typing import Any

from visio_mcp.spec import DiagramSpec

from .providers import ToolCall, ToolDef
from .siblings import describe_kinds, diagram_types, rules_text
from .text import clip

SUBMIT = "submit_diagram"
TOOL_NAMES = ("list_dir", "read_file", "search", "find_files", "get_rules", "list_kinds", SUBMIT)


def tool_defs() -> list[ToolDef]:
    types = diagram_types()
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
        ToolDef(SUBMIT, "Submit the finished diagram. The arguments ARE the DiagramSpec object. "
                "Returns validation errors or lint findings to fix, or 'accepted'.",
                DiagramSpec.model_json_schema()),
    ]


def run_tool(fs: Any, name: str, a: dict, diagram_type: str, provider_hint: str | None) -> str:
    """Execute one exploration tool; raises ValueError/OSError/LookupError for the agent to report."""
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
        t = str(a.get("diagram_type") or diagram_type)
        return rules_text(t, a.get("provider") or provider_hint) or "(no rules)"
    if name == "list_kinds":
        return describe_kinds(a.get("provider") or None)
    raise ValueError(f"unknown tool '{name}'. Available: {', '.join(TOOL_NAMES)}")


def describe_call(call: ToolCall) -> str:
    """Short human-readable line for a tool call."""
    a = call.args or {}
    n = call.name
    if n == "read_file":
        extra = f" @{a['start_line']}" if a.get("start_line") not in (None, 1) else ""
        return f"read_file {a.get('path', '?')}{extra}"
    if n == "list_dir":
        return f"list_dir {a.get('path') or '.'}"
    if n == "search":
        g = f" in {a['glob']}" if a.get("glob") else ""
        return f"search '{clip(str(a.get('pattern', '')), 60)}'{g}"
    if n == "find_files":
        return f"find_files {a.get('glob', '?')}"
    if n == "get_rules":
        return f"get_rules {a.get('diagram_type', '')}"
    if n == "list_kinds":
        return f"list_kinds {a.get('provider') or ''}".strip()
    if n == SUBMIT:
        body = a.get("spec") if isinstance(a.get("spec"), dict) else a
        nodes = body.get("nodes")
        return f"submit_diagram ({len(nodes) if isinstance(nodes, list) else 0} nodes)"
    return n
