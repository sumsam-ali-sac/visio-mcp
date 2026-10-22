"""Pipeline diagrams: CI jobs and their deploy targets, or a suggested flow when no CI exists."""

from __future__ import annotations

from visio_mcp.spec import DiagramSpec

from ..detect.cloud import CLOUD_PRETTY
from ..model import RepoInfo
from ..text import short
from .builder import Builder, catalog_kind
from .labels import diagram_title


def build_pipeline(repos: list[RepoInfo]) -> DiagramSpec:
    b = Builder()
    multi = len(repos) > 1
    targets: dict[str, str] = {}
    any_ci = any(r.ci_jobs for r in repos)
    for r in repos:
        pipes: dict[str, list[dict]] = {}
        for j in r.ci_jobs:
            pipes.setdefault(j["pipeline"], []).append(j)
        cloud = CLOUD_PRETTY.get(r.cloud[0], r.cloud[0]) if r.cloud else ""
        for pipe, jobs in pipes.items():
            pname = jobs[0]["pipeline_name"]
            grp = b.group(f"pipe:{r.name}:{pipe}", f"{r.name}: {pname}" if multi else pname, "tier")
            trig = r.ci_triggers.get(pipe) or "push"
            start = b.node(f"{r.name}_{pname}_start", short(trig, 22) or "Trigger", catalog_kind("start", "process"), grp)
            ids = {}
            for j in jobs:
                ids[j["id"]] = b.node(f"{r.name}_{pname}_{j['id']}", j["label"], catalog_kind("process"), grp,
                                      short(", ".join(j["steps"][:2]), 30), emphasis=bool(j["deploy"]))
            for j in jobs:
                needs = [n for n in j["needs"] if n in ids]
                if not needs:
                    b.edge(start, ids[j["id"]])
                for n in needs:
                    b.edge(ids[n], ids[j["id"]])
                if j["deploy"]:
                    label = cloud or "Environment"
                    if (r.name, label) not in targets:
                        targets[(r.name, label)] = b.node(f"{r.name}_target", label, catalog_kind("cloud", "external"),
                                                           b.group("targets", "Targets", "external"))
                    b.edge(ids[j["id"]], targets[(r.name, label)], "deploys")
    if not any_ci:  # no pipeline files: sketch the usual flow from what the repo contains
        for r in repos:
            grp = b.group(f"pipe:{r.name}", f"{r.name} (suggested)", "tier")
            steps = [("Commit", catalog_kind("start", "process"))]
            steps.append(("Lint & test", catalog_kind("process")))
            steps.append(("Build", catalog_kind("process")))
            if r.containers or r.compose_services:
                steps.append(("Docker image", catalog_kind("container", "storage")))
            steps.append(("Deploy", catalog_kind("process")))
            prev = None
            for label, kind in steps:
                nid = b.node(f"{r.name}_{label}", label, kind, grp, emphasis=label == "Deploy")
                b.edge(prev, nid)
                prev = nid
            if prev:
                tgt = b.node(f"{r.name}_env", CLOUD_PRETTY.get(r.cloud[0], "Environment") if r.cloud else "Environment",
                             catalog_kind("cloud", "external"), b.group("targets", "Targets", "external"))
                b.edge(prev, tgt, "deploys")
    return b.build(diagram_title(repos, "pipeline"), "pipeline", "flowchart-lr")
