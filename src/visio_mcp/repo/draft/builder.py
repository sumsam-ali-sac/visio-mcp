"""Incremental construction of a DiagramSpec: nodes, edges and groups with unique ids and labels."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from visio_mcp import catalog
from visio_mcp.spec import DiagramSpec, Edge, Group, Node

from ..text import short
from .labels import ROLE_SUFFIX, kind_suffix, slug


CAT_LABEL = {"database": "queries", "cache": "caches", "queue": "messages", "storage": "files"}


def catalog_kind(preferred: str, base: str = "service") -> str:
    """preferred if the catalog knows it, else base, else a kind every catalog has."""
    for k in (preferred, base, "service", "process"):
        if catalog.lookup(k) is not None:
            return k
    return "process"


class Builder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self.groups: dict[str, dict[str, Any]] = {}
        self._gkeys: dict[str, str] = {}
        self._ekeys: set[tuple[str, str]] = set()
        self.members: dict[str, set[str]] = defaultdict(set)  # repo name -> node ids
        self.cat: dict[str, str] = {}

    def _uid(self, base: str) -> str:
        s = slug(base)
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
                suffix = ROLE_SUFFIX.get(self.cat.get(n["id"], ""), "") or kind_suffix(n["kind"])
                if suffix and not n["label"].lower().endswith(suffix.lower()):
                    n["label"] = short(f"{n['label']} {suffix}", 26)
            seen: dict[str, int] = defaultdict(int)
            for n in same:
                seen[n["label"].lower()] += 1
                if seen[n["label"].lower()] > 1 and n["technology"]:
                    n["label"] = short(f"{n['label']} ({n['technology']})", 26)

    def data_edge(self, src: str | None, dst: str, label: str = "") -> None:
        cat = self.cat.get(dst, "")
        self.edge(src, dst, label or CAT_LABEL.get(cat, ""), "dashed" if cat == "queue" else "solid")

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
            self.node("system", "Repository", catalog_kind("service"))
        return DiagramSpec(
            title=short(title, 60),
            subtitle=subtitle,
            type=dtype,  # type: ignore[arg-type]
            layout=layout,  # type: ignore[arg-type]
            nodes=[Node(**{**n, "group": n["group"] if n["group"] in used else None}) for n in self.nodes.values()],
            edges=[Edge(**e) for e in self.edges],
            groups=[Group(**g) for g in groups],
        )
