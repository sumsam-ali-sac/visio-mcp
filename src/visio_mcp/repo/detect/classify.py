"""One pass over the file list that sorts files into the buckets the detectors read."""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field

from ..walk import FileEntry
from .compose import COMPOSE_RE
from .entrypoints import is_entry_candidate
from .languages import LANG, SAMPLE_EXT, is_test_path
from .manifests import is_manifest

CI_ROOT_FILES = (
    "azure-pipelines.yml", "azure-pipelines.yaml", ".gitlab-ci.yml", "jenkinsfile", "bitbucket-pipelines.yml",
    ".travis.yml", "cloudbuild.yaml", "cloudbuild.yml", "buildspec.yml", ".drone.yml",
)


ENV_EXAMPLE_RE = re.compile(r"^(\.?env([.\-_][\w.\-]*)?\.(example|sample|template|dist)|(example|sample)\.env|\.env\.example)$", re.I)
CONFIG_RE = re.compile(r"^(appsettings(\.[\w\-]+)?\.json|application(-[\w]+)?\.(properties|ya?ml)|local\.settings(\.example)?\.json)$", re.I)


@dataclass
class Inventory:
    files: list[FileEntry]
    all_rel: set[str] = field(default_factory=set)  # lower-cased relative paths
    langs: Counter[str] = field(default_factory=Counter)
    code_bytes: int = 0
    manifests: list[FileEntry] = field(default_factory=list)
    dockerfiles: list[str] = field(default_factory=list)
    composes: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    ci_other: list[str] = field(default_factory=list)
    tf_files: list[str] = field(default_factory=list)
    bicep_files: list[str] = field(default_factory=list)
    yaml_cands: list[FileEntry] = field(default_factory=list)
    json_cands: list[FileEntry] = field(default_factory=list)
    env_examples: list[str] = field(default_factory=list)
    configs: list[str] = field(default_factory=list)
    samples: list[FileEntry] = field(default_factory=list)
    entry_cands: list[FileEntry] = field(default_factory=list)
    readme_rel: str = ""
    markers: set[str] = field(default_factory=set)  # tool markers: cdk, helm, pulumi, next, django, ...
    helm_dirs: list[str] = field(default_factory=list)
    cdk_dirs: list[str] = field(default_factory=list)


def _classify_config(inv: Inventory, f: FileEntry, low: str, ext: str, depth: int) -> None:
    """Infrastructure, framework-marker and config files (the first matching rule wins)."""
    rel, name = f.rel, f.name
    if ext == ".tf" and f.size < 400_000:
        inv.tf_files.append(rel)
    elif ext == ".bicep" and f.size < 400_000:
        inv.bicep_files.append(rel)
    elif low == "cdk.json":
        inv.cdk_dirs.append(rel.rsplit("/", 1)[0] if "/" in rel else "")
        inv.markers.add("cdk")
    elif low in ("pulumi.yaml", "pulumi.yml"):
        inv.markers.add("pulumi")
    elif low == "chart.yaml":
        inv.helm_dirs.append(rel.rsplit("/", 1)[0] if "/" in rel else "")
        inv.markers.add("helm")
    elif low in ("kustomization.yaml", "kustomization.yml"):
        inv.markers.add("kustomize")
    elif low == "host.json":
        inv.markers.add("azure-functions")
    elif low in ("azure.yaml", "azure.yml"):
        inv.markers.add("azd")
    elif low in ("serverless.yml", "serverless.yaml"):
        inv.yaml_cands.append(f)
        inv.markers.add("serverless")
    elif low in ("next.config.js", "next.config.mjs", "next.config.ts"):
        inv.markers.add("next")
    elif low == "angular.json":
        inv.markers.add("angular")
    elif low.startswith("nuxt.config."):
        inv.markers.add("nuxt")
    elif low == "svelte.config.js":
        inv.markers.add("svelte")
    elif low == "manage.py":
        inv.markers.add("django")
    elif low in ("app.yaml", "app.yml") and depth == 0:
        inv.markers.add("gae")
    elif low == "firebase.json":
        inv.markers.add("firebase")
    elif low == "samconfig.toml":
        inv.markers.add("sam")
    elif ENV_EXAMPLE_RE.match(name):
        inv.env_examples.append(rel)
    elif CONFIG_RE.match(name) and f.size < 100_000:
        inv.configs.append(rel)
    elif ext in (".yaml", ".yml") and f.size < 200_000:
        inv.yaml_cands.append(f)
    elif ext == ".json" and f.size < 400_000 and re.search(
            r"template|azuredeploy|deploy|\.arm\.|infra|stack", low) and low not in ("package.json", "package-lock.json"):
        inv.json_cands.append(f)


def classify(files: list[FileEntry]) -> Inventory:
    inv = Inventory(files)
    for f in files:
        name, rel = f.name, f.rel
        low = name.lower()
        ext = os.path.splitext(low)[1]
        depth = f.depth
        inv.all_rel.add(rel.lower())
        lang = LANG.get(ext)
        if lang:
            inv.langs[lang] += 1
            if lang not in ("HTML", "CSS", "SQL"):
                inv.code_bytes += f.size
            if ext in SAMPLE_EXT and f.size < 60_000 and not is_test_path(rel):
                inv.samples.append(f)
        if is_manifest(low, ext):
            inv.manifests.append(f)
        if low == "dockerfile" or low.startswith("dockerfile.") or low.endswith(".dockerfile"):
            inv.dockerfiles.append(rel)
        if COMPOSE_RE.match(name):
            inv.composes.append(rel)
            continue
        if rel.startswith(".github/workflows/") and ext in (".yml", ".yaml"):
            inv.workflows.append(rel)
            continue
        if (depth <= 1 and low in CI_ROOT_FILES) or rel == ".circleci/config.yml":
            inv.ci_other.append(rel)
            continue
        _classify_config(inv, f, low, ext, depth)
        if low.startswith("readme") and depth == 0 and (not inv.readme_rel or ext in (".md", "")):
            inv.readme_rel = rel
        if is_entry_candidate(low, rel, depth):
            inv.entry_cands.append(f)
    return inv
