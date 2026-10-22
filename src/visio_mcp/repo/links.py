"""Relationships between repos in a workspace: cross-repo links and shared infrastructure."""

from __future__ import annotations

import re
from collections import defaultdict

from .model import RepoInfo
from .resources import lookup_resource


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _name_variants(name: str) -> set[str]:
    low = name.lower()
    base = {low, low.replace("_", "-"), low.replace("-", "_"), _norm(low)}
    return {b for b in base if len(b) >= 4}


def cross_links(repos: list[RepoInfo]) -> list[tuple[str, str, str]]:
    """(from_repo, to_repo, reason) links: compose/image/build refs, env URLs naming another repo, shared deps."""
    links: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    names = {r.name: _name_variants(r.name) for r in repos}

    def add(a: str, b: str, why: str) -> None:
        if a != b and (a, b) not in seen:
            seen.add((a, b))
            links.append((a, b, why))

    for r in repos:
        text_sources: list[tuple[str, str]] = []
        for s_name, s in r.compose_services.items():
            if s.get("image"):
                text_sources.append(("compose image", s["image"]))
            if s.get("build") and s["build"].startswith(".."):
                text_sources.append(("compose build", s["build"]))
            text_sources += [("compose env", h) for h in s.get("environment_hints", [])]
        text_sources += [("config", ref) for ref in r.references]
        deps = [d for ds in r.dependencies.values() for d in ds]
        for other in repos:
            if other is r:
                continue
            variants = names[other.name]
            for why, text in text_sources:
                t = text.lower()
                if any(re.search(r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])", t) or v in re.split(r"[/:]", t) for v in variants):
                    add(r.name, other.name, f"{why} references {other.name}")
                    break
            else:
                if any(d.rsplit("/", 1)[-1] in variants for d in deps):
                    add(r.name, other.name, "depends on its package")
    return links


def shared_infra(repos: list[RepoInfo]) -> list[str]:
    out: list[str] = []
    for attr, label in (("databases", "data store"), ("messaging", "messaging"), ("storage", "storage")):
        users: dict[str, list[str]] = defaultdict(list)
        for r in repos:
            for item in getattr(r, attr):
                users[item].append(r.name)
        for item, who in sorted(users.items()):
            if len(who) > 1:
                out.append(f"- Shared {label} **{item}**: {', '.join(who)}")
    # same named queue/topic/database resource in multiple repos
    named: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in repos:
        for res in r.resources:
            e = lookup_resource(res)
            if e and e.role == "data" and res["name"] and not res["name"].startswith(("[", "$")):
                named[(res["type"], res["name"])].append(r.name)
    for (rtype, name), who in sorted(named.items()):
        if len(set(who)) > 1:
            out.append(f"- Shared resource {rtype} `{name}`: {', '.join(sorted(set(who)))}")
    return out
