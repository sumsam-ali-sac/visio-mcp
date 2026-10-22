"""No-AI fallback: turn scanned repos into a valid, decent-looking DiagramSpec."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from visio_mcp import catalog
from visio_mcp.spec import DiagramSpec, Edge, Group, Node

from ._common import short
from .detect import _BACKEND, _CLOUD_PRETTY, _FRONTEND, _NON_PRIMARY, image_family
from .heuristic_tables import PROVIDER_LABEL, RES_TABLE, SHADOWS, lookup_resource, resource_family, resource_key
from .model import RepoInfo
from .render import cross_links

_SERVERLESS = {"Azure Functions", ".NET Azure Functions", "AWS Lambda"}
_CAT_LABEL = {"database": "queries", "cache": "caches", "queue": "messages", "storage": "files"}
_WEB_NAMES = re.compile(r"web|front|ui|client|site|app$", re.I)


def _kind(preferred: str, base: str = "service") -> str:
    """preferred if the catalog knows it, else base, else a kind every catalog has."""
    for k in (preferred, base, "service", "process"):
        if catalog.lookup(k) is not None:
            return k
    return "process"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "n"


def _humanize(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ").replace("-", " ")
    return " ".join(s.split())


_ROLE_SUFFIX = {"database": "DB", "cache": "Cache", "queue": "Queue", "storage": "Storage"}


def _kind_suffix(kind: str) -> str:
    base = kind.split("-", 1)[-1] if kind.startswith(("azure-", "aws-", "gcp-")) else kind
    for words, suffix in ((("rds", "aurora", "sql", "dynamodb", "cosmos", "spanner", "firestore", "database",
                            "bigtable", "alloydb"), "DB"),
                          (("redis", "elasticache", "memorystore", "cache"), "Cache"),
                          (("s3", "blob", "storage"), "Storage"),
                          (("sqs", "sns", "service-bus", "pubsub", "queue", "topic", "event"), "Queue"),
                          (("ecs", "eks", "fargate", "aks", "gke", "container", "app-service", "cloud-run",
                            "service", "webapp", "ec2", "vm", "compute"), "Service"),
                          (("lambda", "function"), "Function"),
                          (("alb", "load", "gateway", "front-door", "cloudfront", "cdn"), "Gateway")):
        if any(w in base for w in words):
            return suffix
    return ""


def _primary_lang(r: RepoInfo) -> str:
    return next((l for l in r.languages if l not in _NON_PRIMARY), "")


class _Builder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.groups: dict[str, dict[str, Any]] = {}
        self._gkeys: dict[str, str] = {}
        self._ekeys: set[tuple[str, str]] = set()
        self.members: dict[str, set[str]] = defaultdict(set)  # repo name -> node ids
        self.cat: dict[str, str] = {}

    def _uid(self, base: str) -> str:
        s = _slug(base)
        cand, i = s, 2
        while cand in self.nodes or cand in self.groups:
            cand = f"{s}_{i}"
            i += 1
        return cand

    def group(self, key: str, label: str, kind: str = "generic", parent: str | None = None) -> str:
        if key not in self._gkeys:
            gid = self._uid("g_" + key)
            self._gkeys[key] = gid
            self.groups[gid] = {"id": gid, "label": short(label, 28), "kind": kind, "parent": parent}
        return self._gkeys[key]

    def node(self, base: str, label: str, kind: str, group: str | None = None, technology: str = "",
             description: str = "", emphasis: bool = False, cat: str = "", repo: str = "") -> str:
        nid = self._uid(base)
        self.nodes[nid] = {"id": nid, "label": short(label, 26), "kind": kind, "group": group,
                           "technology": short(technology, 32), "description": short(description, 60),
                           "emphasis": emphasis}
        if cat:
            self.cat[nid] = cat
        if repo:
            self.members[repo].add(nid)
        return nid

    def edge(self, a: str | None, b: str | None, label: str = "", style: str = "solid") -> None:
        if not a or not b or a == b or a not in self.nodes or b not in self.nodes or (a, b) in self._ekeys:
            return
        self._ekeys.add((a, b))
        self.edges.append({"source": a, "target": b, "label": short(label, 18), "style": style})

    def _unique_labels(self) -> None:
        """Two nodes called 'Orders' become 'Orders Service' and 'Orders DB'."""
        by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for n in self.nodes.values():
            by_label[n["label"].lower()].append(n)
        for same in by_label.values():
            if len(same) < 2:
                continue
            for n in same:
                suffix = _ROLE_SUFFIX.get(self.cat.get(n["id"], ""), "") or _kind_suffix(n["kind"])
                if suffix and not n["label"].lower().endswith(suffix.lower()):
                    n["label"] = short(f"{n['label']} {suffix}", 26)
            seen: dict[str, int] = defaultdict(int)
            for n in same:
                seen[n["label"].lower()] += 1
                if seen[n["label"].lower()] > 1 and n["technology"]:
                    n["label"] = short(f"{n['label']} ({n['technology']})", 26)

    def data_edge(self, src: str | None, dst: str, label: str = "") -> None:
        cat = self.cat.get(dst, "")
        self.edge(src, dst, label or _CAT_LABEL.get(cat, ""), "dashed" if cat == "queue" else "solid")

    def build(self, title: str, dtype: str, layout: str = "auto", subtitle: str = "Generated from repository scan") -> DiagramSpec:
        # a repo "system" frame around a single node adds nothing: drop the frame
        members: dict[str, list[str]] = defaultdict(list)
        for n in self.nodes.values():
            if n["group"]:
                members[n["group"]].append(n["id"])
        for gid, ids in members.items():
            g = self.groups[gid]
            if g["kind"] == "system" and len(ids) == 1 and not any(x.get("parent") == gid for x in self.groups.values()):
                self.nodes[ids[0]]["group"] = g.get("parent")
        used = {n["group"] for n in self.nodes.values() if n["group"]}
        for gid in list(used):  # keep the ancestors of every used group
            parent = self.groups[gid].get("parent")
            while parent and parent not in used:
                used.add(parent)
                parent = self.groups[parent].get("parent")
        groups = [g for g in self.groups.values() if g["id"] in used]
        self._unique_labels()
        if not self.nodes:
            self.node("system", "Repository", _kind("service"))
        return DiagramSpec(
            title=short(title, 60),
            subtitle=subtitle,
            type=dtype,  # type: ignore[arg-type]
            layout=layout,  # type: ignore[arg-type]
            nodes=[Node(**{**n, "group": n["group"] if n["group"] in used else None}) for n in self.nodes.values()],
            edges=[Edge(**e) for e in self.edges],
            groups=[Group(**g) for g in groups],
        )


# --------------------------------------------------------------------------- shared pieces


def _family_kind(label: str, default: str = "database") -> tuple[str, str]:
    """(catalog kind, category) for a data-store family label."""
    if label in ("Redis", "Memcached"):
        return _kind("cache", "database"), "cache"
    return _kind("database", "service"), default


def _data_group(b: _Builder) -> str:
    return b.group("data", "Data", "tier")


def _title(repos: list[RepoInfo], suffix: str) -> str:
    if len(repos) == 1:
        return f"{repos[0].name} {suffix}"
    parent = repos[0].path.parent.name if repos else ""
    same_parent = len({r.path.parent for r in repos}) == 1
    return f"{parent if same_parent and parent else f'{len(repos)} repositories'} {suffix}"


_NETWORK_TYPES = ("aws_vpc", "azurerm_virtual_network", "google_compute_network", "aws_subnet",
                  "Microsoft.Network/virtualNetworks", "AWS::EC2::VPC")
_NETWORK_LABEL = {"aws": "VPC", "azure": "Virtual Network", "gcp": "VPC Network"}


def _cloud_group(b: _Builder, r: RepoInfo, provider: str, role: str, nest: bool) -> str:
    """The group a resource of this role sits in: cloud > region > network when nesting."""
    top = b.group(f"cloud:{provider}", PROVIDER_LABEL.get(provider, provider.upper()), "cloud")
    if not nest or role == "edge":
        return top
    region = b.group(f"region:{provider}", _region_label(r, provider), "region", parent=top)
    has_net = any(str(x.get("type", "")).startswith(_NETWORK_TYPES) for x in r.resources)
    if role == "aux" or not has_net:
        return region
    return b.group(f"net:{provider}", _NETWORK_LABEL.get(provider, "Network"), "network", parent=region)


def _region_label(r: RepoInfo, provider: str) -> str:
    import re as _re

    for x in r.resources:
        for v in (x.get("region"), x.get("location")):
            if isinstance(v, str) and _re.fullmatch(r"[a-z]{2,}[-a-z]*-?\d?[a-z]?", v):
                return v
    return "Region"


def _add_cloud(b: _Builder, r: RepoInfo, api_id: str | None, fam: dict[str, str], nest: bool = False) -> list[str]:
    """Nodes for IaC resources with provider-specific kinds; returns the ids it used."""
    res = [x for x in r.resources if lookup_resource(x)]
    keys = {resource_key(x) for x in res}
    res = [x for x in res if SHADOWS.get(resource_key(x)) not in keys]
    groups: dict[str, list[dict]] = {}
    for x in res:
        groups.setdefault(resource_key(x), []).append(x)
    roles: dict[str, list[str]] = defaultdict(list)
    merged = False
    used: list[str] = []
    for key, items in list(groups.items())[:24]:
        entry = RES_TABLE[key]
        provider = items[0]["provider"] or (r.cloud[0] if r.cloud else "aws")
        grp = _cloud_group(b, r, provider, "aux" if entry.base == "storage" else entry.role, nest)
        kind = _kind(entry.preferred, entry.base)
        cat = entry.base if entry.role == "data" and entry.base in ("queue", "cache", "storage", "database") else ""
        for idx, it in enumerate(items[: 1 if len(items) > 3 else 3]):
            f = resource_family(it)
            family = f[1] if f else None
            if family and family in fam:  # same store already drawn (e.g. detected in a sibling repo)
                roles[entry.role].append(fam[family])
                continue
            name = it["name"]
            label = entry.label if (not name or name[0] in "[$(" or "{" in name or "'" in name) else _humanize(name)
            if len(items) > 3:
                label = f"{entry.label} x{len(items)}"
            if entry.role == "compute" and api_id and not merged and entry.base in ("function", "webapp", "service"):
                n = b.nodes[api_id]
                n["kind"], n["group"] = kind, grp
                n["description"] = short(entry.label, 60)
                roles["compute"].append(api_id)
                merged = True
                continue
            nid = b.node(f"{provider}_{label}", label, kind, grp, entry.label, cat=cat, repo=r.name)
            roles[entry.role].append(nid)
            used.append(nid)
            if family:
                fam[family] = nid
    edge, compute, data, aux = roles["edge"], roles["compute"], roles["data"], roles["aux"]
    for e in edge[:3]:
        for c in compute[:4]:
            b.edge(e, c, "routes")
        if not compute and api_id:
            b.edge(e, api_id, "routes")
    sources = compute[:3] if compute else ([api_id] if api_id else [])
    for s in sources:
        for d in data[:6]:
            b.data_edge(s, d)
        for a in aux[:2]:
            b.edge(s, a, "secrets" if "vault" in b.nodes[a]["kind"] else "auth", "dotted")
    if compute and api_id and api_id not in compute:
        b.edge(api_id, compute[0], "deployed to", "dotted")
    return used


# --------------------------------------------------------------------------- architecture


def _repo_nodes(b: _Builder, r: RepoInfo, grp: str) -> tuple[str | None, str | None]:
    """(entry node id, backend node id) for a repo's own application code."""
    fe = [f for f in r.frameworks if f in _FRONTEND]
    be = [f for f in r.frameworks if f in _BACKEND or f in _SERVERLESS]
    lang = _primary_lang(r)
    has_infra = any(k != "docker-compose" for k in r.iac_kinds)
    if not r.frameworks and not r.entrypoints and has_infra:
        return None, None

    def tech(fw: str) -> str:
        return f"{lang} / {fw}" if lang and fw else (lang or fw)

    def api_kind() -> str:
        if any("Azure Functions" in f for f in be):
            return _kind("azure-functions", "function")
        if "AWS Lambda" in be:
            return _kind("aws-lambda", "function")
        return _kind("service")

    if fe and be:
        ui = b.node(f"{r.name}_ui", f"{r.name} UI", _kind("webapp"), grp, tech(fe[0]), repo=r.name)
        api = b.node(r.name + "_api", f"{r.name} API", api_kind(), grp, tech(be[0]), repo=r.name)
        b.edge(ui, api, "REST")
        return ui, api
    if fe:
        n = b.node(r.name, r.name, _kind("webapp"), grp, tech(fe[0]), emphasis=True, repo=r.name)
        return n, n
    kind = api_kind() if be else _kind("service")
    n = b.node(r.name, r.name, kind, grp, tech(be[0]) if be else lang, emphasis=True, repo=r.name)
    web = any(f in _BACKEND for f in be) or any(s.get("ports") for s in r.compose_services.values())
    return (n if web else None), n


def _architecture(repos: list[RepoInfo], dtype: str) -> DiagramSpec:
    b = _Builder()
    fam: dict[str, str] = {}
    mains: dict[str, str] = {}
    entries: list[str] = []
    multi = len(repos) > 1

    for r in repos:
        grp = b.group(f"repo:{r.name}", r.name, "system")
        entry, api = _repo_nodes(b, r, grp)
        if api:
            mains[r.name] = api
        if entry:
            entries.append(entry)

        # 1. IaC resources (production truth) first, so dev compose / detected stores reuse them
        _add_cloud(b, r, api, fam, nest=dtype == "cloud")

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
                kind = {"cache": _kind("cache", "database"), "queue": _kind("queue", "service"),
                        "storage": _kind("storage", "database")}.get(cat, _kind("database"))
                data_grp = data_grp or _data_group(b)
                nid = b.node(sname, label, kind, data_grp, s.get("image", ""), cat=cat, repo=r.name)
                fam[label] = nid
                svcmap[sname] = nid
            elif f and f[1] == "gateway":
                nid = b.node(sname, sname, _kind("gateway"), grp, s.get("image", ""), repo=r.name)
                svcmap[sname] = nid
                if s.get("ports"):
                    entries.append(nid)
            else:
                if api and not taken_main and s.get("build", "") in (".", "./", ""):
                    if s.get("build") in (".", "./") or (not s.get("image") and len(r.compose_services) == 1):
                        svcmap[sname] = api
                        taken_main = True
                        continue
                kind = _kind("webapp") if _WEB_NAMES.search(sname) and not s.get("build", "").startswith("..") and (
                    "front" in sname or "web" in sname or sname == "ui") else _kind("service")
                tech = s.get("image", "") or _primary_lang(r)
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
            k, c = _family_kind(d)
            wanted.append((d, c, k))
        for m in r.messaging:
            if m != "Celery":
                wanted.append((m, "queue", _kind("queue", "service")))
        for s_ in r.storage:
            wanted.append((s_, "storage", _kind("storage", "database")))
        for label, cat, kind in wanted:
            if label not in fam:
                fam[label] = b.node(label, label, kind, _data_group(b), cat=cat)
            tgt = fam[label]
            b.members[r.name].add(tgt)
            if api and not any(e["target"] == tgt and e["source"] in b.members[r.name] for e in b.edges):
                b.data_edge(api, tgt)

        # 4. Celery workers
        if "Celery" in r.frameworks or "Celery" in r.messaging:
            w = b.node(f"{r.name}_worker", "Celery worker", _kind("worker", "service"), grp,
                       f"{_primary_lang(r)} / Celery".strip(" /"), repo=r.name)
            b.edge(api, w, "tasks", "dashed")
            for broker in ("Redis", "RabbitMQ"):
                if broker in fam:
                    b.edge(w, fam[broker], "broker", "dashed")
                    break

        # 5. external APIs
        for ext in r.external_apis:
            key = "ext:" + ext
            if key not in fam:
                fam[key] = b.node(ext, ext, _kind("external", "service"), b.group("external", "External", "external"))
            b.edge(api or entry or next(iter(sorted(b.members[r.name])), None), fam[key], "HTTPS")

    # clients
    if entries:
        clients = b.group("clients", "Clients", "tier")
        users = b.node("users", "Users", _kind("user", "client"), clients)
        for e in dict.fromkeys(entries):
            b.edge(users, e, "HTTPS")

    # cross-repo links
    if multi:
        for a, c, why in cross_links(repos):
            http = "config" in why or "env" in why or "url" in why
            b.edge(mains.get(a) or next(iter(sorted(b.members[a])), None), mains.get(c) or next(iter(sorted(b.members[c])), None),
                   "HTTPS" if http else "calls", "solid" if http else "dashed")

    out_type = "cloud" if dtype == "cloud" else "architecture"
    return b.build(_title(repos, "architecture" if dtype != "cloud" else "cloud architecture"), out_type)


# --------------------------------------------------------------------------- pipeline


def _pipeline(repos: list[RepoInfo]) -> DiagramSpec:
    b = _Builder()
    multi = len(repos) > 1
    targets: dict[str, str] = {}
    any_ci = any(r.ci_jobs for r in repos)
    for r in repos:
        pipes: dict[str, list[dict]] = {}
        for j in r.ci_jobs:
            pipes.setdefault(j["pipeline"], []).append(j)
        cloud = _CLOUD_PRETTY.get(r.cloud[0], r.cloud[0]) if r.cloud else ""
        for pipe, jobs in pipes.items():
            pname = jobs[0]["pipeline_name"]
            grp = b.group(f"pipe:{r.name}:{pipe}", f"{r.name}: {pname}" if multi else pname, "tier")
            trig = r.ci_triggers.get(pipe) or "push"
            start = b.node(f"{r.name}_{pname}_start", short(trig, 22) or "Trigger", _kind("start", "process"), grp)
            ids = {}
            for j in jobs:
                ids[j["id"]] = b.node(f"{r.name}_{pname}_{j['id']}", j["label"], _kind("process"), grp,
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
                        targets[(r.name, label)] = b.node(f"{r.name}_target", label, _kind("cloud", "external"),
                                                           b.group("targets", "Targets", "external"))
                    b.edge(ids[j["id"]], targets[(r.name, label)], "deploys")
    if not any_ci:  # no pipeline files: sketch the usual flow from what the repo contains
        for r in repos:
            grp = b.group(f"pipe:{r.name}", f"{r.name} (suggested)", "tier")
            steps = [("Commit", _kind("start", "process"))]
            steps.append(("Lint & test", _kind("process")))
            steps.append(("Build", _kind("process")))
            if r.containers or r.compose_services:
                steps.append(("Docker image", _kind("container", "storage")))
            steps.append(("Deploy", _kind("process")))
            prev = None
            for label, kind in steps:
                nid = b.node(f"{r.name}_{label}", label, kind, grp, emphasis=label == "Deploy")
                b.edge(prev, nid)
                prev = nid
            if prev:
                tgt = b.node(f"{r.name}_env", _CLOUD_PRETTY.get(r.cloud[0], "Environment") if r.cloud else "Environment",
                             _kind("cloud", "external"), b.group("targets", "Targets", "external"))
                b.edge(prev, tgt, "deploys")
    return b.build(_title(repos, "pipeline"), "pipeline", "flowchart-lr")


# --------------------------------------------------------------------------- deployment


def _deployment(repos: list[RepoInfo]) -> DiagramSpec:
    b = _Builder()
    fam: dict[str, str] = {}
    multi = len(repos) > 1
    net: str | None = None

    def internet() -> str:
        nonlocal net
        if net is None:
            net = b.node("internet", "Internet", _kind("internet", "cloud"), b.group("clients", "Clients", "tier"))
        return net

    for r in repos:
        if r.compose_services:
            g = b.group(f"compose:{r.name}", f"Docker Compose{f' ({r.name})' if multi else ''}", "environment")
            svcmap: dict[str, str] = {}
            for sname, s in r.compose_services.items():
                f = image_family(s.get("image", ""))
                cat = f[1] if f and f[1] in ("database", "cache", "queue", "storage") else ""
                kind = {"database": _kind("database"), "cache": _kind("cache", "database"), "queue": _kind("queue"),
                        "storage": _kind("storage", "database")}.get(cat) or (
                    _kind("gateway") if f and f[1] == "gateway" else _kind("container", "service"))
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
            _k8s_nodes(b, r, multi, internet)
        if r.resources:
            _add_cloud(b, r, None, fam)
        if not r.compose_services and not r.k8s_objects:
            for df in r.containers[:6]:
                g = b.group(f"docker:{r.name}", f"{r.name} containers", "environment")
                parent = df.rsplit("/", 1)[0] if "/" in df else r.name
                b.node(f"{r.name}_{parent}", parent, _kind("container", "service"), g, "Dockerfile", repo=r.name)
    if not b.nodes:
        return _architecture(repos, "architecture").model_copy(update={"type": "deployment"})
    return b.build(_title(repos, "deployment"), "deployment")


def _k8s_nodes(b: _Builder, r: RepoInfo, multi: bool, internet) -> None:
    g = b.group(f"k8s:{r.name}", f"Kubernetes{f' ({r.name})' if multi else ''}", "cluster")
    workloads = {"Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job"}
    ids: dict[tuple[str, str], str] = {}
    objs = [o for o in r.k8s_objects if o["kind"] in workloads | {"Service", "Ingress", "PersistentVolumeClaim"}][:40]
    for o in objs:
        kind, name = o["kind"], o["name"] or o["kind"].lower()
        image = o["images"][0].rsplit("/", 1)[-1] if o.get("images") else ""
        if kind in workloads:
            f = image_family(image)
            nk = _kind("database") if f and f[1] == "database" else _kind("container", "service")
            nid = b.node(f"{name}", name, nk, g, image or kind, kind, cat="database" if f and f[1] == "database" else "", repo=r.name)
        elif kind == "Service":
            nid = b.node(f"{name}_svc", name, _kind("loadbalancer"), g, o.get("service_type", "Service"),
                         ", ".join(o["ports"][:2]), repo=r.name)
        elif kind == "Ingress":
            nid = b.node(f"{name}_ing", name, _kind("gateway"), g, "Ingress", repo=r.name)
        else:
            nid = b.node(f"{name}_pvc", name, _kind("storage"), g, "PVC", cat="storage", repo=r.name)
        ids[(kind, name)] = nid
    svcs = [o for o in objs if o["kind"] == "Service"]
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
    _ = svcs


# --------------------------------------------------------------------------- entry point


def heuristic_spec(repos: list[RepoInfo], diagram_type: str = "architecture") -> DiagramSpec:
    """A no-AI diagram of the scanned repos. Always returns a valid DiagramSpec."""
    repos = list(repos)
    if not repos:
        return DiagramSpec(title="Architecture", subtitle="Generated from repository scan", type="architecture",
                           nodes=[Node(id="system", label="System", kind=_kind("service"))])
    if diagram_type == "pipeline":
        return _pipeline(repos)
    if diagram_type == "deployment":
        return _deployment(repos)
    return _architecture(repos, "cloud" if diagram_type == "cloud" else "architecture")
