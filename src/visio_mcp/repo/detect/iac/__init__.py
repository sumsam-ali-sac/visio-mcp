"""Infrastructure-as-code detection: Terraform, Bicep, ARM, CloudFormation/SAM, Serverless, CDK, Kubernetes, Helm."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ...lists import add_unique
from ...model import RepoInfo
from ...text import read_text
from ...walk import FileEntry
from ...yaml import parse_yaml, yaml_docs
from ..classify import Inventory
from .arm import parse_arm
from .bicep import parse_bicep
from .cdk import scan_cdk
from .cloudformation import parse_cfn
from .kubernetes import helm_objects, parse_k8s_doc
from .serverless import parse_serverless
from .terraform import parse_terraform


IAC_PRETTY = {
    "terraform": "Terraform", "bicep": "Bicep", "arm": "ARM templates", "cloudformation": "CloudFormation",
    "sam": "AWS SAM", "cdk": "AWS CDK", "serverless": "Serverless Framework", "pulumi": "Pulumi",
    "kubernetes": "Kubernetes", "helm": "Helm", "docker-compose": "Docker Compose", "kustomize": "Kustomize",
}


def _by_depth(rels: list[str]) -> list[str]:
    return sorted(rels, key=lambda r: (r.count("/"), r))


def _hinted(f: FileEntry) -> tuple[int, int, str]:
    """Sort key: files whose path suggests infrastructure come first."""
    low = f.rel.lower()
    hint = any(h in low for h in ("k8s", "kube", "manifest", "deploy", "helm", "chart", "infra", "cloudformation",
                                  "template", "stack", "sam", "serverless"))
    return (0 if hint else 1, f.depth, f.rel)


def _scan_hcl(root: Path, inv: Inventory, info: RepoInfo, clouds: list[str]) -> None:
    for rel in _by_depth(inv.tf_files)[:80]:
        parse_terraform(read_text(root / rel, 400_000), rel, info.resources, clouds)
        add_unique(info.iac, rel)
        add_unique(info.iac_kinds, "terraform")
    for rel in _by_depth(inv.bicep_files)[:80]:
        parse_bicep(read_text(root / rel, 400_000), rel, info.resources, clouds)
        add_unique(info.iac, rel)
        add_unique(info.iac_kinds, "bicep")


def _scan_yaml(root: Path, inv: Inventory, info: RepoInfo, clouds: list[str]) -> None:
    helm_prefixes = tuple(h + "/" if h else "" for h in inv.helm_dirs)
    for f in sorted(inv.yaml_cands, key=_hinted)[:200]:
        text = read_text(root / f.rel, 200_000)
        if f.name.lower().startswith("serverless."):
            parse_serverless(text, f.rel, info.resources, clouds)
            add_unique(info.iac, f.rel)
            add_unique(info.iac_kinds, "serverless")
            continue
        if "AWSTemplateFormatVersion" in text or re.search(r"^\s+Type:\s*['\"]?AWS::", text, re.M):
            sam = "Serverless-2016-10-31" in text or "AWS::Serverless" in text
            parse_cfn(parse_yaml(text), f.rel, info.resources, clouds, "sam" if sam else "cloudformation")
            add_unique(info.iac, f.rel)
            add_unique(info.iac_kinds, "sam" if sam else "cloudformation")
            continue
        if re.search(r"^apiVersion:", text, re.M) and re.search(r"^kind:\s*\w+", text, re.M):
            if "/templates/" in "/" + f.rel and any(f.rel.startswith(p) for p in helm_prefixes):
                info.k8s_objects.extend(helm_objects(text, f.rel))
                add_unique(info.iac, f.rel)
                continue
            objects = [o for o in (parse_k8s_doc(doc, f.rel) for doc in yaml_docs(text)) if o]
            if objects:
                info.k8s_objects.extend(objects)
                add_unique(info.iac, f.rel)
                add_unique(info.iac_kinds, "kubernetes")


def _scan_json(root: Path, inv: Inventory, info: RepoInfo, clouds: list[str]) -> None:
    for f in sorted(inv.json_cands, key=_hinted)[:60]:
        text = read_text(root / f.rel, 400_000)
        if "deploymentTemplate" in text or "schema.management.azure.com" in text:
            try:
                parse_arm(json.loads(text), f.rel, info.resources, clouds)
            except ValueError:
                continue
            add_unique(info.iac, f.rel)
            add_unique(info.iac_kinds, "arm")
        elif "AWSTemplateFormatVersion" in text or '"AWS::' in text:
            try:
                doc = json.loads(text)
            except ValueError:
                continue
            parse_cfn(doc, f.rel, info.resources, clouds, "cloudformation")
            add_unique(info.iac, f.rel)
            add_unique(info.iac_kinds, "cloudformation")


def _apply_markers(root: Path, inv: Inventory, info: RepoInfo, clouds: list[str]) -> None:
    for h in inv.helm_dirs:
        add_unique(info.iac, (h + "/Chart.yaml") if h else "Chart.yaml")
    for mk in ("helm", "pulumi", "kustomize"):
        if mk in inv.markers:
            add_unique(info.iac_kinds, mk)
    if "pulumi" in inv.markers:
        for rel in sorted(inv.all_rel):
            if rel.endswith("pulumi.yaml") or rel.endswith("pulumi.yml"):
                add_unique(info.iac, rel)
    if "cdk" in inv.markers:
        add_unique(info.iac_kinds, "cdk")
        for d in inv.cdk_dirs:
            add_unique(info.iac, (d + "/cdk.json") if d else "cdk.json")
        scan_cdk(root, inv.files, inv.cdk_dirs, info)
        add_unique(clouds, "aws")
    if "serverless" in inv.markers and "serverless" not in info.iac_kinds:
        add_unique(info.iac_kinds, "serverless")


def detect_iac(root: Path, inv: Inventory, info: RepoInfo) -> list[str]:
    """Fill info.resources / k8s_objects / iac / iac_kinds; return the cloud providers the IaC targets."""
    clouds: list[str] = []
    _scan_hcl(root, inv, info, clouds)
    _scan_yaml(root, inv, info, clouds)
    _scan_json(root, inv, info, clouds)
    _apply_markers(root, inv, info, clouds)
    return clouds
