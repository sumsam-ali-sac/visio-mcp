"""The RepoInfo profile."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoInfo:
    path: Path
    name: str
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    iac: list[str] = field(default_factory=list)
    cloud: list[str] = field(default_factory=list)
    containers: list[str] = field(default_factory=list)
    compose_services: dict[str, dict] = field(default_factory=dict)
    ci: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    messaging: list[str] = field(default_factory=list)
    external_apis: list[str] = field(default_factory=list)
    readme: str = ""
    file_count: int = 0
    loc_estimate: int = 0
    is_git: bool = False
    suggested_types: list[str] = field(default_factory=list)
    summary: str = ""
    # Extras beyond the core contract (used by digest / heuristic_spec).
    iac_kinds: list[str] = field(default_factory=list)  # terraform, bicep, arm, cloudformation, sam, cdk, ...
    resources: list[dict] = field(default_factory=list)  # {iac, provider, type, name, file, hint}
    k8s_objects: list[dict] = field(default_factory=list)  # {kind, name, namespace, file, ...}
    ci_jobs: list[dict] = field(default_factory=list)  # {pipeline, pipeline_name, id, label, needs, deploy, ...}
    ci_triggers: dict[str, str] = field(default_factory=dict)  # pipeline file -> trigger summary
    dependencies: dict[str, list[str]] = field(default_factory=dict)  # manifest -> dependency names
    storage: list[str] = field(default_factory=list)  # 'Azure Blob Storage', 'S3', 'MinIO', ...
    references: list[str] = field(default_factory=list)  # env/URL snippets that may name other systems
