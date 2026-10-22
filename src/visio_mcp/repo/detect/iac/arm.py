"""Azure ARM templates: resources from a parsed deployment template."""

from __future__ import annotations

from typing import Any

from ...lists import add_unique, as_list
from .resource import resource


def parse_arm(doc: dict, rel: str, out: list[dict], clouds: list[str]) -> None:
    def visit(items: Any, parent: str = "") -> None:
        for r in as_list(items):
            if not isinstance(r, dict) or not isinstance(r.get("type"), str):
                continue
            rtype = r["type"] if "/" in r["type"] and r["type"].lower().startswith("microsoft.") else f"{parent}/{r['type']}"
            hint = "functionapp" if "functionapp" in str(r.get("kind", "")).lower() else ""
            out.append(resource("arm", "azure", rtype, str(r.get("name", "")), rel, hint))
            visit(r.get("resources"), rtype)

    visit(doc.get("resources"))
    add_unique(clouds, "azure")
