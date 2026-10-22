"""IaC resources as provider-specific diagram nodes, nested in cloud > region > network groups."""

from __future__ import annotations

import re
from collections import defaultdict

from ..model import RepoInfo
from ..resources import PROVIDER_LABEL, RES_TABLE, SHADOWS, lookup_resource, resource_family, resource_key
from ..text import short
from .builder import Builder, catalog_kind
from .labels import humanize


NETWORK_TYPES = ("aws_vpc", "azurerm_virtual_network", "google_compute_network", "aws_subnet",
                  "Microsoft.Network/virtualNetworks", "AWS::EC2::VPC")

NETWORK_LABEL = {"aws": "VPC", "azure": "Virtual Network", "gcp": "VPC Network"}


def _cloud_group(b: Builder, r: RepoInfo, provider: str, role: str, nest: bool) -> str:
    """The group a resource of this role sits in: cloud > region > network when nesting."""
    top = b.group(f"cloud:{provider}", PROVIDER_LABEL.get(provider, provider.upper()), "cloud")
    if not nest or role == "edge":
        return top
    region = b.group(f"region:{provider}", _region_label(r), "region", parent=top)
    has_net = any(str(x.get("type", "")).startswith(NETWORK_TYPES) for x in r.resources)
    if role == "aux" or not has_net:
        return region
    return b.group(f"net:{provider}", NETWORK_LABEL.get(provider, "Network"), "network", parent=region)


def _region_label(r: RepoInfo) -> str:
    for x in r.resources:
        for v in (x.get("region"), x.get("location")):
            if isinstance(v, str) and re.fullmatch(r"[a-z]{2,}[-a-z]*-?\d?[a-z]?", v):
                return v
    return "Region"


def add_cloud(b: Builder, r: RepoInfo, api_id: str | None, fam: dict[str, str], nest: bool = False) -> list[str]:
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
        kind = catalog_kind(entry.preferred, entry.base)
        cat = entry.base if entry.role == "data" and entry.base in ("queue", "cache", "storage", "database") else ""
        for idx, it in enumerate(items[: 1 if len(items) > 3 else 3]):
            f = resource_family(it)
            family = f[1] if f else None
            if family and family in fam:  # same store already drawn (e.g. detected in a sibling repo)
                roles[entry.role].append(fam[family])
                continue
            name = it["name"]
            label = entry.label if (not name or name[0] in "[$(" or "{" in name or "'" in name) else humanize(name)
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
