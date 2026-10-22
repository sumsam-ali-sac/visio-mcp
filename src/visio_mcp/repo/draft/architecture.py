"""Architecture and cloud diagrams: apps, data stores, queues, external APIs and cross-repo links."""

from __future__ import annotations

import re

from visio_mcp.spec import DiagramSpec

from ..detect.compose import image_family
from ..detect.frameworks import BACKEND, FRONTEND
from ..detect.languages import primary_language
from ..links import cross_links
from ..model import RepoInfo
from .builder import Builder, catalog_kind
from .cloud import add_cloud
from .labels import diagram_title


SERVERLESS = {"Azure Functions", ".NET Azure Functions", "AWS Lambda"}
WEB_NAMES = re.compile(r"web|front|ui|client|site|app$", re.I)


def family_kind(label: str, default: str = "database") -> tuple[str, str]:
    """(catalog kind, category) for a data-store family label."""
    if label in ("Redis", "Memcached"):
        return catalog_kind("cache", "database"), "cache"
    return catalog_kind("database", "service"), default


def data_group(b: Builder) -> str:
    return b.group("data", "Data", "tier")


def repo_nodes(b: Builder, r: RepoInfo, grp: str) -> tuple[str | None, str | None]:
    """(entry node id, backend node id) for a repo's own application code."""
    fe = [f for f in r.frameworks if f in FRONTEND]
    be = [f for f in r.frameworks if f in BACKEND or f in SERVERLESS]
    lang = primary_language(r.languages)
    has_infra = any(k != "docker-compose" for k in r.iac_kinds)
    if not r.frameworks and not r.entrypoints and has_infra:
        return None, None

    def tech(fw: str) -> str:
        return f"{lang} / {fw}" if lang and fw else (lang or fw)

    def api_kind() -> str:
        if any("Azure Functions" in f for f in be):
            return catalog_kind("azure-functions", "function")
        if "AWS Lambda" in be:
            return catalog_kind("aws-lambda", "function")
        return catalog_kind("service")

    if fe and be:
        ui = b.node(f"{r.name}_ui", f"{r.name} UI", catalog_kind("webapp"), grp, tech(fe[0]), repo=r.name)
        api = b.node(r.name + "_api", f"{r.name} API", api_kind(), grp, tech(be[0]), repo=r.name)
        b.edge(ui, api, "REST")
        return ui, api
    if fe:
        n = b.node(r.name, r.name, catalog_kind("webapp"), grp, tech(fe[0]), emphasis=True, repo=r.name)
        return n, n
    kind = api_kind() if be else catalog_kind("service")
    n = b.node(r.name, r.name, kind, grp, tech(be[0]) if be else lang, emphasis=True, repo=r.name)
    web = any(f in BACKEND for f in be) or any(s.get("ports") for s in r.compose_services.values())
    return (n if web else None), n


def build_architecture(repos: list[RepoInfo], dtype: str) -> DiagramSpec:
    b = Builder()
    fam: dict[str, str] = {}
    mains: dict[str, str] = {}
    entries: list[str] = []
    multi = len(repos) > 1

    for r in repos:
        grp = b.group(f"repo:{r.name}", r.name, "system")
        entry, api = repo_nodes(b, r, grp)
        if api:
            mains[r.name] = api
        if entry:
            entries.append(entry)

        # 1. IaC resources (production truth) first, so dev compose / detected stores reuse them
        add_cloud(b, r, api, fam, nest=dtype == "cloud")

        # 2. docker compose services
        svcmap: dict[str, str] = {}
        data_grp = None
        taken_main = False
        for sname, s in r.compose_services.items():
            f = image_family(s.get("image", ""))
            if f and f[0] and f[1] in ("database", "cache", "queue", "storage"):
                label, cat = f[0], f[1]
                if label in fam and fam[label] in b.nodes:
                    svcmap[sname] = fam[label]
                    continue
                kind = {"cache": catalog_kind("cache", "database"), "queue": catalog_kind("queue", "service"),
                        "storage": catalog_kind("storage", "database")}.get(cat, catalog_kind("database"))
                data_grp = data_grp or data_group(b)
                nid = b.node(sname, label, kind, data_grp, s.get("image", ""), cat=cat, repo=r.name)
                fam[label] = nid
                svcmap[sname] = nid
            elif f and f[1] == "gateway":
                nid = b.node(sname, sname, catalog_kind("gateway"), grp, s.get("image", ""), repo=r.name)
                svcmap[sname] = nid
                if s.get("ports"):
                    entries.append(nid)
            else:
                if api and not taken_main and s.get("build", "") in (".", "./", ""):
                    if s.get("build") in (".", "./") or (not s.get("image") and len(r.compose_services) == 1):
                        svcmap[sname] = api
                        taken_main = True
                        continue
                kind = catalog_kind("webapp") if WEB_NAMES.search(sname) and not s.get("build", "").startswith("..") and (
                    "front" in sname or "web" in sname or sname == "ui") else catalog_kind("service")
                tech = s.get("image", "") or primary_language(r.languages)
                nid = b.node(sname, sname, kind, grp, tech, repo=r.name)
                svcmap[sname] = nid
                if s.get("ports") and not entry and not entries[-1:] == [nid]:
                    entries.append(nid)
        for sname, s in r.compose_services.items():
            for dep in s.get("depends_on", []):
                if sname in svcmap and dep in svcmap:
                    b.data_edge(svcmap[sname], svcmap[dep], "" if b.cat.get(svcmap[dep]) else "calls")

        # 3. detected stores / queues / object storage
        wanted: list[tuple[str, str, str]] = []  # label, cat, kind
        for d in r.databases:
            k, c = family_kind(d)
            wanted.append((d, c, k))
        for m in r.messaging:
            if m != "Celery":
                wanted.append((m, "queue", catalog_kind("queue", "service")))
        for s_ in r.storage:
            wanted.append((s_, "storage", catalog_kind("storage", "database")))
        for label, cat, kind in wanted:
            if label not in fam:
                fam[label] = b.node(label, label, kind, data_group(b), cat=cat)
            tgt = fam[label]
            b.members[r.name].add(tgt)
            if api and not any(e["target"] == tgt and e["source"] in b.members[r.name] for e in b.edges):
                b.data_edge(api, tgt)

        # 4. Celery workers
        if "Celery" in r.frameworks or "Celery" in r.messaging:
            w = b.node(f"{r.name}_worker", "Celery worker", catalog_kind("worker", "service"), grp,
                       f"{primary_language(r.languages)} / Celery".strip(" /"), repo=r.name)
            b.edge(api, w, "tasks", "dashed")
            for broker in ("Redis", "RabbitMQ"):
                if broker in fam:
                    b.edge(w, fam[broker], "broker", "dashed")
                    break

        # 5. external APIs
        for ext in r.external_apis:
            key = "ext:" + ext
            if key not in fam:
                fam[key] = b.node(ext, ext, catalog_kind("external", "service"), b.group("external", "External", "external"))
            b.edge(api or entry or next(iter(sorted(b.members[r.name])), None), fam[key], "HTTPS")

    # clients
    if entries:
        clients = b.group("clients", "Clients", "tier")
        users = b.node("users", "Users", catalog_kind("user", "client"), clients)
        for e in dict.fromkeys(entries):
            b.edge(users, e, "HTTPS")

    # cross-repo links
    if multi:
        for a, c, why in cross_links(repos):
            http = "config" in why or "env" in why or "url" in why
            b.edge(mains.get(a) or next(iter(sorted(b.members[a])), None), mains.get(c) or next(iter(sorted(b.members[c])), None),
                   "HTTPS" if http else "calls", "solid" if http else "dashed")

    out_type = "cloud" if dtype == "cloud" else "architecture"
    return b.build(diagram_title(repos, "architecture" if dtype != "cloud" else "cloud architecture"), out_type)
