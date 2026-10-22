"""Text views of a repo for people and LLMs: tree, digest, workspace digest, cross-repo links."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ._common import (
    NOISE_FILES,
    NOISE_SUFFIXES,
    GitIgnore,
    is_ignored_dir,
    resolve_dir,
)
from .detect import _CLOUD_PRETTY, _IAC_PRETTY
from .draft_tables import lookup_resource
from .model import RepoInfo

MAX_FILES_SHOWN = 12
FILES_COLLAPSE_OVER = 16
MAX_DIRS_SHOWN = 40


# --------------------------------------------------------------------------- tree


@dataclass
class TreeNode:
    name: str
    is_dir: bool
    children: list["TreeNode"] = field(default_factory=list)
    more_files: int = 0
    more_dirs: int = 0
    hidden: bool = False  # dir whose contents were not scanned (depth limit)


def _scan_entries(path: str, rel: str, gi: GitIgnore) -> tuple[list[str], list[str]]:
    dirs: list[str] = []
    files: list[str] = []
    try:
        with os.scandir(path) as it:
            for e in it:
                name = e.name
                erel = f"{rel}/{name}" if rel else name
                try:
                    if e.is_dir(follow_symlinks=False):
                        if is_ignored_dir(name) or gi.ignored(erel, name, True):
                            continue
                        dirs.append(name)
                    elif e.is_file(follow_symlinks=False) or e.is_symlink():
                        if name in NOISE_FILES or name.endswith(NOISE_SUFFIXES) or gi.ignored(erel, name, False):
                            continue
                        files.append(name)
                except OSError:
                    continue
    except OSError:
        pass
    key = lambda s: (s.lower(), s)  # noqa: E731
    return sorted(dirs, key=key), sorted(files, key=key)


def build_tree(path: str, rel: str, depth: int, max_depth: int, gi: GitIgnore) -> TreeNode:
    name = os.path.basename(path.rstrip(os.sep)) or path
    node = TreeNode(name, True)
    if depth >= max_depth:
        node.hidden = True
        return node
    dirs, files = _scan_entries(path, rel, gi)
    for d in dirs[:MAX_DIRS_SHOWN]:
        node.children.append(build_tree(os.path.join(path, d), f"{rel}/{d}" if rel else d, depth + 1, max_depth, gi))
    node.more_dirs = max(0, len(dirs) - MAX_DIRS_SHOWN)
    shown = files if len(files) <= FILES_COLLAPSE_OVER else files[: MAX_FILES_SHOWN - 4]
    for f in shown:
        node.children.append(TreeNode(f, False))
    node.more_files = len(files) - len(shown)
    return node


def _count(node: TreeNode, eff: int, depth: int = 0) -> int:
    n = (1 if node.more_dirs else 0) + (1 if node.more_files else 0)
    for c in node.children:
        n += 1
        if c.is_dir and depth + 1 < eff:
            n += _count(c, eff, depth + 1)
    return n


def _render(node: TreeNode, eff: int, depth: int, lines: list[str]) -> None:
    pad = "  " * (depth + 1)
    for c in node.children:
        if c.is_dir:
            expand = depth + 1 < eff
            has_more = c.hidden or bool(c.children) or c.more_files or c.more_dirs
            lines.append(f"{pad}{c.name}/" + ("" if expand or not has_more else " …"))
            if expand:
                _render(c, eff, depth + 1, lines)
        else:
            lines.append(f"{pad}{c.name}")
    if node.more_dirs:
        lines.append(f"{pad}… {node.more_dirs} more dirs")
    if node.more_files:
        lines.append(f"{pad}… {node.more_files} more files")


def render_tree(top: TreeNode, title: str, max_entries: int, max_depth: int) -> str:
    eff = max(1, max_depth)
    while eff > 1 and _count(top, eff) > max_entries:
        eff -= 1
    lines = [title.rstrip("/") + "/"]
    _render(top, eff, 0, lines)
    if len(lines) - 1 > max_entries:
        lines = lines[: max_entries + 1] + ["  … (truncated)"]
    return "\n".join(lines)


def tree(path: str | Path, max_entries: int = 300, max_depth: int = 4) -> str:
    """Compact indented tree: dirs first, noise skipped, .gitignore honored, huge dirs collapsed."""
    root = resolve_dir(path)
    top = build_tree(str(root), "", 0, max(1, max_depth), GitIgnore(root))
    return render_tree(top, root.name or str(root), max(1, max_entries), max(1, max_depth))


# --------------------------------------------------------------------------- digest


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
        lines.append(f"**{_IAC_PRETTY.get(iac, iac)}**")
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
        rows.append("- Cloud: " + ", ".join(_CLOUD_PRETTY.get(c, c) for c in info.cloud))
    if info.iac_kinds:
        rows.append("- IaC/deploy: " + ", ".join(_IAC_PRETTY.get(k, k) for k in info.iac_kinds))
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
        if title == "Project tree" and out.endswith("\n…\n```\n"):
            pass
    if len(out) > max_chars:
        out = out[: max_chars - 2].rstrip() + "\n…"
    return out


# --------------------------------------------------------------------------- cross-repo


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
