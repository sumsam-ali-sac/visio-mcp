"""Deployment diagrams: Docker Compose, Kubernetes, containers and cloud resources."""

from __future__ import annotations

from collections.abc import Callable

from visio_mcp.spec import DiagramSpec

from ..detect.compose import image_family
from ..model import RepoInfo
from ..text import short
from .architecture import build_architecture
from .builder import Builder, catalog_kind
from .cloud import add_cloud
from .labels import diagram_title


def build_deployment(repos: list[RepoInfo]) -> DiagramSpec:
    b = Builder()
    fam: dict[str, str] = {}
    multi = len(repos) > 1
    net: str | None = None

    def internet() -> str:
        nonlocal net
        if net is None:
            net = b.node("internet", "Internet", catalog_kind("internet", "cloud"), b.group("clients", "Clients", "tier"))
        return net

    for r in repos:
        if r.compose_services:
            g = b.group(f"compose:{r.name}", f"Docker Compose{f' ({r.name})' if multi else ''}", "environment")
            svcmap: dict[str, str] = {}
            for sname, s in r.compose_services.items():
                f = image_family(s.get("image", ""))
                cat = f[1] if f and f[1] in ("database", "cache", "queue", "storage") else ""
                kind = {"database": catalog_kind("database"), "cache": catalog_kind("cache", "database"), "queue": catalog_kind("queue"),
                        "storage": catalog_kind("storage", "database")}.get(cat) or (
                    catalog_kind("gateway") if f and f[1] == "gateway" else catalog_kind("container", "service"))
                ports = ", ".join(s.get("ports", [])[:2])
                nid = b.node(sname, sname, kind, g, s.get("image") or ("build " + s.get("build", "")).strip(),
                             f"ports {ports}" if ports else "", cat=cat, repo=r.name)
                svcmap[sname] = nid
                if ports and not cat:
                    b.edge(internet(), nid, short(s["ports"][0].split(":")[0], 8))
            for sname, s in r.compose_services.items():
                for dep in s.get("depends_on", []):
                    if dep in svcmap:
                        b.data_edge(svcmap[sname], svcmap[dep], "" if b.cat.get(svcmap[dep]) else "depends on")
        if r.k8s_objects:
            k8s_nodes(b, r, multi, internet)
        if r.resources:
            add_cloud(b, r, None, fam)
        if not r.compose_services and not r.k8s_objects:
            for df in r.containers[:6]:
                g = b.group(f"docker:{r.name}", f"{r.name} containers", "environment")
                parent = df.rsplit("/", 1)[0] if "/" in df else r.name
                b.node(f"{r.name}_{parent}", parent, catalog_kind("container", "service"), g, "Dockerfile", repo=r.name)
    if not b.nodes:
        return build_architecture(repos, "architecture").model_copy(update={"type": "deployment"})
    return b.build(diagram_title(repos, "deployment"), "deployment")


def k8s_nodes(b: Builder, r: RepoInfo, multi: bool, internet: Callable[[], str]) -> None:
    g = b.group(f"k8s:{r.name}", f"Kubernetes{f' ({r.name})' if multi else ''}", "cluster")
    workloads = {"Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job"}
    ids: dict[tuple[str, str], str] = {}
    objs = [o for o in r.k8s_objects if o["kind"] in workloads | {"Service", "Ingress", "PersistentVolumeClaim"}][:40]
    for o in objs:
        kind, name = o["kind"], o["name"] or o["kind"].lower()
        image = o["images"][0].rsplit("/", 1)[-1] if o.get("images") else ""
        if kind in workloads:
            f = image_family(image)
            nk = catalog_kind("database") if f and f[1] == "database" else catalog_kind("container", "service")
            nid = b.node(f"{name}", name, nk, g, image or kind, kind, cat="database" if f and f[1] == "database" else "", repo=r.name)
        elif kind == "Service":
            nid = b.node(f"{name}_svc", name, catalog_kind("loadbalancer"), g, o.get("service_type", "Service"),
                         ", ".join(o["ports"][:2]), repo=r.name)
        elif kind == "Ingress":
            nid = b.node(f"{name}_ing", name, catalog_kind("gateway"), g, "Ingress", repo=r.name)
        else:
            nid = b.node(f"{name}_pvc", name, catalog_kind("storage"), g, "PVC", cat="storage", repo=r.name)
        ids[(kind, name)] = nid
    for o in objs:
        key = (o["kind"], o["name"] or o["kind"].lower())
        if o["kind"] == "Ingress":
            b.edge(internet(), ids[key], "HTTPS")
            for be in o["backends"]:
                if ("Service", be) in ids:
                    b.edge(ids[key], ids[("Service", be)], "routes")
        if o["kind"] == "Service":
            if o.get("service_type") == "LoadBalancer":
                b.edge(internet(), ids[key])
            for w in objs:
                if w["kind"] in workloads and o["selector"] and all(w["labels"].get(k) == v for k, v in o["selector"].items()):
                    b.edge(ids[key], ids[(w["kind"], w["name"] or w["kind"].lower())])
