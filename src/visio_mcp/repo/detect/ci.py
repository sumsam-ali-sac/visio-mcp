"""CI/CD pipelines: GitHub Actions, Azure Pipelines, GitLab CI, Jenkins and Bitbucket into jobs with dependencies."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..lists import add_unique, as_list, as_str_list
from ..model import RepoInfo
from ..text import read_text
from ..yaml import parse_yaml
from .classify import Inventory


def short_step(step: Any) -> str:
    if not isinstance(step, dict):
        return ""
    if step.get("name"):
        return str(step["name"])
    if step.get("uses"):
        return str(step["uses"]).split("@")[0]
    run = step.get("run")
    return str(run).strip().splitlines()[0][:50] if run else ""


DEPLOY_RE = re.compile(r"deploy|release|publish|rollout|promote|ship", re.I)


def parse_github_workflow(text: str, rel: str, info: RepoInfo) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    pname = str(doc.get("name") or Path(rel).stem)
    on = doc.get("on", doc.get("true"))
    trig = ", ".join(as_str_list(on)) if on is not None else ""
    info.ci_triggers[rel] = trig[:60]
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return
    for jid, job in jobs.items():
        if not isinstance(job, dict):
            continue
        steps = [s for s in (short_step(x) for x in as_list(job.get("steps"))) if s]
        label = str(job.get("name") or jid)
        env = " ".join(steps) + " " + label + " " + str(jid)
        info.ci_jobs.append({
            "pipeline": rel, "pipeline_name": pname, "id": str(jid), "label": label,
            "needs": as_str_list(job.get("needs")), "runs_on": str(job.get("runs-on") or ""),
            "steps": steps[:8], "deploy": bool(DEPLOY_RE.search(env)) or bool(job.get("environment")),
        })
    low = text.lower()
    if "azure/" in low or "azure_" in low:
        add_unique(info.cloud, "azure")
    if "aws-actions/" in low:
        add_unique(info.cloud, "aws")
    if "google-github-actions/" in low:
        add_unique(info.cloud, "gcp")


def parse_azure_pipeline(text: str, rel: str, info: RepoInfo) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    info.ci_triggers[rel] = ", ".join(as_str_list(doc.get("trigger")))[:60] if doc.get("trigger") else ""
    pname = Path(rel).stem
    stages = [s for s in as_list(doc.get("stages")) if isinstance(s, dict)]
    if stages:
        prev = ""
        for s in stages:
            sid = str(s.get("stage") or s.get("displayName") or "stage")
            needs = as_str_list(s["dependsOn"]) if "dependsOn" in s else ([prev] if prev else [])
            jobs_txt = json.dumps(s.get("jobs"), default=str)
            info.ci_jobs.append({
                "pipeline": rel, "pipeline_name": pname, "id": sid, "label": str(s.get("displayName") or sid),
                "needs": [n for n in needs if n], "runs_on": "", "steps": [],
                "deploy": bool(DEPLOY_RE.search(sid)) or "deployment" in jobs_txt[:200],
            })
            prev = sid
        return
    jobs = [j for j in as_list(doc.get("jobs")) if isinstance(j, dict)]
    if jobs:
        for j in jobs:
            jid = str(j.get("job") or j.get("deployment") or j.get("displayName") or "job")
            info.ci_jobs.append({
                "pipeline": rel, "pipeline_name": pname, "id": jid, "label": str(j.get("displayName") or jid),
                "needs": as_str_list(j.get("dependsOn")), "runs_on": "",
                "steps": [s for s in (short_step({"name": x.get("displayName"), "uses": x.get("task"), "run": x.get("script")}) for x in as_list(j.get("steps")) if isinstance(x, dict)) if s][:8],
                "deploy": "deployment" in j or bool(DEPLOY_RE.search(jid)),
            })
    elif doc.get("steps"):
        info.ci_jobs.append({"pipeline": rel, "pipeline_name": pname, "id": "build", "label": "Build", "needs": [],
                             "runs_on": "", "steps": [], "deploy": False})


GITLAB_RESERVED = {"stages", "variables", "include", "default", "workflow", "image", "services", "cache",
                    "before_script", "after_script", "pages"}


def parse_gitlab(text: str, rel: str, info: RepoInfo) -> None:
    doc = parse_yaml(text)
    if not isinstance(doc, dict):
        return
    stages = as_str_list(doc.get("stages")) or ["build", "test", "deploy"]
    jobs = {k: v for k, v in doc.items() if isinstance(v, dict) and k not in GITLAB_RESERVED and not k.startswith(".")
            and ("script" in v or "stage" in v or "trigger" in v)}
    by_stage: dict[str, list[str]] = {}
    for k, v in jobs.items():
        by_stage.setdefault(str(v.get("stage") or "test"), []).append(k)
    pname = ".gitlab-ci"
    for k, v in jobs.items():
        st = str(v.get("stage") or "test")
        if "needs" in v:
            needs = [str(n.get("job")) if isinstance(n, dict) else str(n) for n in as_list(v["needs"]) if n]
        else:
            idx = stages.index(st) if st in stages else 0
            needs = by_stage.get(stages[idx - 1], []) if idx > 0 else []
        info.ci_jobs.append({
            "pipeline": rel, "pipeline_name": pname, "id": k, "label": k, "needs": needs[:6], "runs_on": "",
            "steps": [], "stage": st, "deploy": bool(DEPLOY_RE.search(k + st)),
        })


def parse_named_steps(text: str, rel: str, info: RepoInfo, rx: str) -> None:
    prev = ""
    for name in re.findall(rx, text, re.M):
        name = name.strip().strip("'\"")
        if not name or any(j["id"] == name and j["pipeline"] == rel for j in info.ci_jobs):
            continue
        info.ci_jobs.append({
            "pipeline": rel, "pipeline_name": Path(rel).name, "id": name, "label": name,
            "needs": [prev] if prev else [], "runs_on": "", "steps": [], "deploy": bool(DEPLOY_RE.search(name)),
        })
        prev = name


def detect_ci(root: Path, inv: Inventory, info: RepoInfo) -> None:
    for rel in sorted(inv.workflows)[:20]:
        parse_github_workflow(read_text(root / rel, 200_000), rel, info)
        add_unique(info.ci, rel)
    for rel in inv.ci_other:
        text = read_text(root / rel, 200_000)
        add_unique(info.ci, rel)
        low = rel.lower()
        if "azure-pipelines" in low:
            parse_azure_pipeline(text, rel, info)
        elif low.endswith(".gitlab-ci.yml"):
            parse_gitlab(text, rel, info)
        elif low.endswith("jenkinsfile"):
            parse_named_steps(text, rel, info, r"stage\s*\(\s*['\"]([^'\"]+)['\"]")
        elif low.endswith("bitbucket-pipelines.yml"):
            parse_named_steps(text, rel, info, r"^\s*(?:-\s*)?name:\s*(.+?)\s*$")
