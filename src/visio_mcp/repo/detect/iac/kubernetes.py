"""Kubernetes manifests: workloads, services and ingresses from parsed YAML documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...lists import as_list


def parse_k8s_doc(doc: Any, rel: str) -> dict | None:
    if not isinstance(doc, dict) or not isinstance(doc.get("kind"), str) or "apiVersion" not in doc:
        return None
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    kind = doc["kind"]
    obj: dict[str, Any] = {
        "kind": kind, "name": str(meta.get("name") or ""), "namespace": str(meta.get("namespace") or ""),
        "file": rel, "labels": {}, "selector": {}, "images": [], "backends": [], "ports": [],
    }
    tmpl = spec.get("template")
    if kind == "CronJob":
        jt = spec.get("jobTemplate") or {}
        tmpl = ((jt.get("spec") or {}).get("template")) if isinstance(jt, dict) else None
    if isinstance(tmpl, dict):
        tm = tmpl.get("metadata") or {}
        if isinstance(tm, dict) and isinstance(tm.get("labels"), dict):
            obj["labels"] = {str(k): str(v) for k, v in tm["labels"].items()}
        ts = tmpl.get("spec") or {}
        if isinstance(ts, dict):
            for c in as_list(ts.get("containers")):
                if isinstance(c, dict):
                    if c.get("image"):
                        obj["images"].append(str(c["image"]))
                    for p in as_list(c.get("ports")):
                        if isinstance(p, dict) and p.get("containerPort"):
                            obj["ports"].append(str(p["containerPort"]))
    if kind == "Service":
        if isinstance(spec.get("selector"), dict):
            obj["selector"] = {str(k): str(v) for k, v in spec["selector"].items()}
        for p in as_list(spec.get("ports")):
            if isinstance(p, dict) and p.get("port"):
                obj["ports"].append(str(p["port"]))
        obj["service_type"] = str(spec.get("type") or "ClusterIP")
    if kind == "Ingress":
        def find(node: Any) -> None:
            if isinstance(node, dict):
                svc = node.get("service")
                if isinstance(svc, dict) and svc.get("name"):
                    obj["backends"].append(str(svc["name"]))
                if node.get("serviceName"):
                    obj["backends"].append(str(node["serviceName"]))
                for v in node.values():
                    find(v)
            elif isinstance(node, list):
                for v in node:
                    find(v)
        find(spec)
    return obj


def helm_objects(text: str, rel: str) -> list[dict]:
    """Objects in a Helm template: only kinds are reliable (the file is not plain YAML)."""
    return [
        {"kind": k, "name": Path(rel).stem, "namespace": "", "file": rel, "labels": {}, "selector": {},
         "images": [], "backends": [], "ports": [], "helm": True}
        for k in re.findall(r"^kind:\s*(\w+)", text, re.M)
    ]
