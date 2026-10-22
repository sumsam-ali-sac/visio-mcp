"""CloudFormation / SAM templates: resources from a parsed template."""

from __future__ import annotations

from ...lists import add_unique
from .resource import resource


def parse_cfn(doc: dict, rel: str, out: list[dict], clouds: list[str], iac: str) -> None:
    resources = doc.get("Resources") if isinstance(doc, dict) else None
    if not isinstance(resources, dict):
        return
    for lid, body in resources.items():
        if isinstance(body, dict) and isinstance(body.get("Type"), str):
            out.append(resource(iac, "aws", body["Type"], str(lid), rel))
    add_unique(clouds, "aws")
