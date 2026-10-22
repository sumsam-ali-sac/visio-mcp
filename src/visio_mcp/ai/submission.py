"""Checking what the model submits: schema validation, normalization, rule lint rounds and JSON-in-text fallback."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from visio_mcp.spec import DiagramSpec

from .events import EventKind
from .siblings import sibling

MAX_LINT_ROUNDS = 2  # lint findings are returned on the first two submissions

Emit = Callable[[EventKind, str, str], None]


def validation_message(exc: ValidationError) -> str:
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


class Submissions:
    """One round of `submit_diagram` calls: validates each, runs lint, and remembers the last valid spec."""

    def __init__(self, diagram_type: str):
        self.diagram_type = diagram_type
        self.count = 0
        self.last_valid: DiagramSpec | None = None
        self._last_raw: dict | None = None

    def normalize(self, spec: DiagramSpec) -> tuple[DiagramSpec, list[str]]:
        if spec.type == "auto" and self.diagram_type != "auto":
            try:
                spec = spec.model_copy(update={"type": self.diagram_type})
            except ValueError:
                pass
        spec, notes = sibling("lint").normalize(spec)
        return spec, list(notes or [])

    def submit(self, args: dict, emit: Emit) -> tuple[str, bool, DiagramSpec | None]:
        """Returns (text for the model, is_error, accepted spec or None)."""
        data: Any = args
        if set(args) == {"spec"}:  # tolerate {"spec": {...}} or {"spec": "<json>"}
            data = args["spec"]
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as exc:
                    return f"spec is not valid JSON: {exc}", True, None
        try:
            raw = DiagramSpec.model_validate(data)
        except ValidationError as exc:
            return ("The spec is invalid. Fix these and call submit_diagram again with the full spec:\n"
                    + validation_message(exc), True, None)
        self.count += 1
        same_as_before = self._last_raw is not None and raw.model_dump() == self._last_raw
        self._last_raw = raw.model_dump()
        spec, notes = self.normalize(raw)
        self.last_valid = spec
        emit("draft", f"Draft {self.count}: {len(spec.nodes)} nodes, {len(spec.edges)} edges",
             spec.model_dump_json(exclude_defaults=True))
        findings = list(sibling("lint").lint(spec))
        if findings and self.count <= MAX_LINT_ROUNDS and not same_as_before:
            emit("lint", f"{len(findings)} rule finding(s); asking the model to fix", "\n".join(findings))
            text = (
                "The spec is valid but breaks these diagram rules:\n"
                + "\n".join(f"- {f}" for f in findings)
                + "\n\nFix them and call submit_diagram again with the complete spec. If you judge a "
                "finding acceptable here, resubmit the same spec unchanged."
            )
            if notes:
                text += "\n\nNormalization notes: " + "; ".join(notes)
            return text, False, None
        if findings:
            emit("lint", f"Accepted with {len(findings)} finding(s)", "\n".join(findings))
        return "accepted: the diagram is being drawn.", False, spec
