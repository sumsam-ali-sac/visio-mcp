"""Human-facing conclusions about a profiled repo: suggested diagram types and a one-line summary."""

from __future__ import annotations

from ..model import RepoInfo
from .cloud import CLOUD_PRETTY
from .frameworks import FRONTEND
from .iac import IAC_PRETTY
from .languages import primary_language


def suggest_types(info: RepoInfo, all_rel: set[str]) -> list[str]:
    has_cloud_res = any(r["provider"] in CLOUD_PRETTY for r in info.resources)
    iac_first = sum(1 for r in info.resources if r["provider"] in CLOUD_PRETTY) >= 3 and not info.frameworks
    out = ["cloud", "architecture"] if iac_first else ["architecture"]
    if (has_cloud_res or info.cloud) and "cloud" not in out:
        out.append("cloud")
    out.append("c4-container")
    if info.compose_services or info.k8s_objects or info.containers or has_cloud_res:
        out.append("deployment")
    if info.ci_jobs or info.ci:
        out.append("pipeline")
    erd_signal = any(
        r.endswith(("models.py", "schema.prisma", ".sql", "entities.py")) or "/migrations/" in "/" + r or "/entities/" in r
        or "/models/" in r for r in all_rel
    )
    if info.databases and erd_signal:
        out.append("erd")
    if info.messaging:
        out.append("dataflow")
    return out


def summarize(info: RepoInfo) -> str:
    primary = primary_language(info.languages)
    fe = [f for f in info.frameworks if f in FRONTEND]
    be = [f for f in info.frameworks if f not in FRONTEND]
    iac_main = [k for k in info.iac_kinds if k not in ("docker-compose", "kubernetes", "helm", "kustomize")]
    n_res = sum(1 for r in info.resources if r["type"] != "module")
    app_frameworks = info.frameworks
    if not app_frameworks and iac_main and (not primary or info.languages.get(primary, 0) < 3 or primary in ("Shell",)):
        cloud = " and ".join(CLOUD_PRETTY[c] for c in info.cloud) if info.cloud else "cloud"
        base = f"{' + '.join(IAC_PRETTY.get(k, k) for k in iac_main)} infrastructure for {cloud}"
        if n_res:
            base += f" ({n_res} resources)"
        return base
    fw = " + ".join((be[:1] + fe[:1]) if (be and fe) else (info.frameworks[:2]))
    kind = "web app" if fe and not be else ("service" if be else "project")
    parts = [" ".join(p for p in (primary, fw, kind) if p)]
    data = (info.databases + [m for m in info.messaging if m != "Celery"])[:4]
    summary = parts[0]
    if data:
        summary += " with " + (", ".join(data[:-1]) + " and " + data[-1] if len(data) > 1 else data[0])
    if info.cloud and iac_main:
        summary += f", deployed to {' and '.join(CLOUD_PRETTY[c] for c in info.cloud)} via {', '.join(IAC_PRETTY.get(k, k) for k in iac_main)}"
    elif "kubernetes" in info.iac_kinds or "helm" in info.iac_kinds:
        summary += ", deployed to Kubernetes"
    elif info.cloud:
        summary += f", using {' and '.join(CLOUD_PRETTY[c] for c in info.cloud)} services"
    elif info.compose_services:
        summary += ", run with Docker Compose"
    elif info.containers:
        summary += ", containerized with Docker"
    if info.ci:
        ci_names = []
        for c in info.ci:
            n = ("GitHub Actions" if c.startswith(".github/") else "Azure Pipelines" if "azure-pipelines" in c
                 else "GitLab CI" if "gitlab" in c else "Jenkins" if "Jenkinsfile" in c else "CI")
            if n not in ci_names:
                ci_names.append(n)
        summary += f"; CI on {', '.join(ci_names)}"
    return summary
