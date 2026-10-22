"""Serverless Framework: functions and CloudFormation resources from serverless.yml."""

from __future__ import annotations

from ...lists import add_unique, as_list
from ...yaml import parse_yaml
from .cloudformation import parse_cfn
from .resource import resource


def parse_serverless(text: str, rel: str, out: list[dict], clouds: list[str]) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    prov = doc.get("provider")
    pname = (prov.get("name") if isinstance(prov, dict) else prov) or "aws"
    provider = {"aws": "aws", "azure": "azure", "google": "gcp"}.get(str(pname).lower(), "aws")
    add_unique(clouds, provider)
    funcs = doc.get("functions")
    if isinstance(funcs, dict):
        for fname, body in funcs.items():
            events = []
            if isinstance(body, dict):
                events = [next(iter(e)) for e in as_list(body.get("events")) if isinstance(e, dict) and e]
            out.append(resource("serverless", provider, "serverless::function", str(fname), rel, ",".join(events)))
    res = doc.get("resources")
    if isinstance(res, dict):
        parse_cfn(res, rel, out, clouds, "serverless")
