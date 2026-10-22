"""Markdown profiles of repos for an LLM: one repo digest and a multi-repo workspace digest."""

from __future__ import annotations

from collections import defaultdict

from .detect.cloud import CLOUD_PRETTY
from .detect.iac import IAC_PRETTY
from .links import cross_links, shared_infra
from .model import RepoInfo
from .tree import tree


def _cap(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    cut = text[: max(0, n - 2)]
    nl = cut.rfind("\n")
    if nl > n * 0.6:
        cut = cut[:nl]
    return cut.rstrip() + "\n…"


def _resource_section(info: RepoInfo) -> str:
    by_iac: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in info.resources:
        by_iac[r["iac"]][r["type"]].append(r["name"])
    lines: list[str] = []
    for iac, types in by_iac.items():
        lines.append(f"**{IAC_PRETTY.get(iac, iac)}**")
        for rtype, names in sorted(types.items()):
            shown = ", ".join(n for n in names[:6] if n) or ""
            more = f" (+{len(names) - 6})" if len(names) > 6 else ""
            lines.append(f"- {rtype}: {shown}{more}".rstrip(": "))
    return "\n".join(lines)


def _k8s_section(info: RepoInfo) -> str:
    by_kind: dict[str, list[str]] = defaultdict(list)
    for o in info.k8s_objects:
        label = o["name"] or "?"
        if o.get("images"):
            label += f" [{', '.join(i.rsplit('/', 1)[-1] for i in o['images'][:2])}]"
        by_kind[o["kind"]].append(label)
    return "\n".join(f"- {k}: {', '.join(v[:8])}" + (f" (+{len(v) - 8})" if len(v) > 8 else "") for k, v in sorted(by_kind.items()))


def _compose_section(info: RepoInfo) -> str:
    lines = []
    for name, s in info.compose_services.items():
        bits = []
        if s.get("image"):
            bits.append(f"image `{s['image']}`")
        if s.get("build"):
            bits.append(f"build `{s['build']}`")
        if s.get("ports"):
            bits.append("ports " + ", ".join(s["ports"][:3]))
        if s.get("depends_on"):
            bits.append("depends_on " + ", ".join(s["depends_on"]))
        if s.get("environment_hints"):
            bits.append("env " + ", ".join(s["environment_hints"][:4]))
        lines.append(f"- **{name}**: " + "; ".join(bits))
    return "\n".join(lines)


def _ci_section(info: RepoInfo) -> str:
    by_pipe: dict[str, list[dict]] = defaultdict(list)
    for j in info.ci_jobs:
        by_pipe[j["pipeline"]].append(j)
    lines = []
    for pipe, jobs in by_pipe.items():
        trig = info.ci_triggers.get(pipe)
        lines.append(f"**{pipe}**" + (f" (on: {trig})" if trig else ""))
        for j in jobs[:12]:
            needs = f" needs {', '.join(j['needs'])}" if j["needs"] else ""
            steps = f" - {'; '.join(j['steps'][:4])}" if j["steps"] else ""
            lines.append(f"- {j['id']}{needs}{steps}")
    for c in info.ci:
        if c not in by_pipe:
            lines.append(f"**{c}**")
    return "\n".join(lines)


def _stack_section(info: RepoInfo) -> str:
    rows = []
    if info.languages:
        rows.append("- Languages: " + ", ".join(f"{k} ({v})" for k, v in list(info.languages.items())[:6]))
    if info.frameworks:
        rows.append("- Frameworks: " + ", ".join(info.frameworks))
    if info.databases:
        rows.append("- Data stores: " + ", ".join(info.databases))
    if info.messaging:
        rows.append("- Messaging: " + ", ".join(info.messaging))
    if info.storage:
        rows.append("- Object storage: " + ", ".join(info.storage))
    if info.external_apis:
        rows.append("- External APIs: " + ", ".join(info.external_apis))
    if info.cloud:
        rows.append("- Cloud: " + ", ".join(CLOUD_PRETTY.get(c, c) for c in info.cloud))
    if info.iac_kinds:
        rows.append("- IaC/deploy: " + ", ".join(IAC_PRETTY.get(k, k) for k in info.iac_kinds))
    if info.containers:
        rows.append("- Dockerfiles: " + ", ".join(info.containers[:6]))
    if info.entrypoints:
        rows.append("- Entry points: " + ", ".join(info.entrypoints[:8]))
    if info.ci:
        rows.append("- CI: " + ", ".join(info.ci[:6]))
    rows.append(f"- Size: {info.file_count} files, ~{info.loc_estimate} lines of code")
    return "\n".join(rows)


def _deps_section(info: RepoInfo) -> str:
    lines = []
    for m, deps in list(info.dependencies.items())[:8]:
        lines.append(f"- {m}: " + ", ".join(deps[:30]) + (f" (+{len(deps) - 30})" if len(deps) > 30 else ""))
    return "\n".join(lines)


def digest(info: RepoInfo, max_chars: int = 12000) -> str:
    """Markdown profile of one repo for an LLM, ordered by usefulness and hard-capped at max_chars."""
    head = f"# {info.name}\n\n{info.summary}\n"
    sections: list[tuple[str, str, float]] = []  # title, body, max share of budget
    sections.append(("Stack", _stack_section(info), 0.25))
    if info.compose_services:
        sections.append(("Docker Compose services", _compose_section(info), 0.2))
    if info.resources:
        sections.append(("Infrastructure resources", _resource_section(info), 0.25))
    if info.k8s_objects:
        sections.append(("Kubernetes objects", _k8s_section(info), 0.15))
    if info.ci_jobs or info.ci:
        sections.append(("CI/CD", _ci_section(info), 0.15))
    try:
        sections.append(("Project tree", tree(info.path, max_entries=140, max_depth=3), 0.3))
    except OSError:
        pass
    if info.dependencies:
        sections.append(("Dependencies", _deps_section(info), 0.2))
    if info.references:
        sections.append(("Config references", "\n".join(f"- {r}" for r in info.references[:20]), 0.08))
    if info.readme:
        sections.append(("README (excerpt)", info.readme, 0.2))

    out = head
    for title, body, share in sections:
        if not body.strip():
            continue
        remaining = max_chars - len(out)
        if remaining < 200:
            break
        heading = f"\n## {title}\n"
        body = _cap(body, min(int(max_chars * share), remaining - len(heading) - 2))
        out += heading + ("```\n" + body + "\n```\n" if title == "Project tree" else body + "\n")
    if len(out) > max_chars:
        out = out[: max_chars - 2].rstrip() + "\n…"
    return out


def workspace_digest(repos: list[RepoInfo], max_chars: int = 20000) -> str:
    """Overview of several repos: one-liners, cross-repo links, then per-repo digests within budget."""
    lines = [f"# Workspace: {len(repos)} repositories\n"]
    for r in repos:
        lines.append(f"- **{r.name}** - {r.summary or 'no summary'}")
    links = cross_links(repos)
    shared = shared_infra(repos)
    if links or shared:
        lines.append("\n## Cross-repo links\n")
        lines += [f"- {a} -> {b} ({why})" for a, b, why in links]
        lines += shared
    head = "\n".join(lines) + "\n"
    if len(head) > max_chars:
        return head[: max_chars - 2].rstrip() + "\n…"
    out = head
    remaining = max_chars - len(out)
    if repos and remaining > 600:
        # Spread the budget; the first repos get a little more if there is room.
        per = max(600, remaining // len(repos))
        for r in repos:
            remaining = max_chars - len(out)
            if remaining < 400:
                out += "\n(other repositories omitted: out of space)\n"[: max(0, remaining)]
                break
            out += "\n---\n\n" + digest(r, min(per, remaining - 6))
    if len(out) > max_chars:
        out = out[: max_chars - 2].rstrip() + "\n…"
    return out
