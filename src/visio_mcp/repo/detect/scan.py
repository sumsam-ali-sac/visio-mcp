"""Profile one repository folder: orchestrates the detectors into a RepoInfo."""

from __future__ import annotations

from pathlib import Path

from ..ignore import GitIgnore
from ..model import RepoInfo
from ..paths import resolve_dir
from ..text import read_text
from ..walk import walk
from .classify import classify
from .cloud import detect_cloud
from .ci import detect_ci
from .compose import read_compose
from .corpus import build_corpus
from .data import detect_data
from .entrypoints import find_entrypoints
from .frameworks import detect_frameworks
from .iac import detect_iac
from .languages import language_profile
from .manifests import read_dependencies
from .references import build_references
from .summary import summarize, suggest_types


def scan(path: str | Path) -> RepoInfo:
    """Profile one repository folder. Fast: one directory walk plus a few hundred small reads."""
    root = resolve_dir(path)
    files = walk(root, GitIgnore(root))
    info = RepoInfo(path=root, name=root.name or str(root))
    info.is_git = (root / ".git").exists()
    info.file_count = len(files)
    inv = classify(files)

    info.languages, info.loc_estimate = language_profile(inv.langs, inv.code_bytes)
    deps = read_dependencies(root, inv.manifests, info)
    info.containers = sorted(inv.dockerfiles, key=lambda r: (r.count("/"), r))[:30]
    compose_text = read_compose(root, inv.composes, info)
    clouds = detect_iac(root, inv, info)
    detect_ci(root, inv, info)
    corpus = build_corpus(root, inv, compose_text)

    detect_frameworks(info, deps, inv.markers)
    detect_data(info, deps, corpus)
    detect_cloud(info, deps, clouds, inv.markers)
    info.entrypoints = find_entrypoints(inv.entry_cands, files)
    info.references = build_references(info, corpus)
    if inv.readme_rel:
        text = read_text(root / inv.readme_rel, 20_000)
        info.readme = "\n".join(text.splitlines()[:80])[:6000]

    info.suggested_types = suggest_types(info, inv.all_rel)
    info.summary = summarize(info)
    return info
