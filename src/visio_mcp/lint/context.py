"""Shared context for the lint checks: kind info, degrees, group chains and message helpers."""

from __future__ import annotations

from collections import Counter

from visio_mcp.lint.infer import infer_type
from visio_mcp.lint.kinds import KindInfo, kind_info
from visio_mcp.spec import DiagramSpec, Edge, Group, Node


def quoted(items: list[str], limit: int = 3) -> str:
    shown = ", ".join(f"'{i}'" for i in items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def words(text: str) -> int:
    return len(text.split())


class Context:
    def __init__(self, spec: DiagramSpec) -> None:
        self.spec = spec
        self.type = spec.type if spec.type != "auto" else infer_type(spec)
        self.info: dict[str, KindInfo] = {n.id: kind_info(n.kind) for n in spec.nodes}
        self.groups: dict[str, Group] = {g.id: g for g in spec.groups}
        self.degree: Counter[str] = Counter()
        self.out: dict[str, list[Edge]] = {n.id: [] for n in spec.nodes}
        for e in spec.edges:
            self.degree[e.source] += 1
            self.degree[e.target] += 1
            self.out[e.source].append(e)

    def ancestors(self, gid: str | None) -> list[Group]:
        chain: list[Group] = []
        while gid and gid in self.groups and len(chain) <= len(self.groups):
            chain.append(self.groups[gid])
            gid = self.groups[gid].parent
        return chain

    def members(self, gid: str) -> tuple[list[Node], list[Group]]:
        return ([n for n in self.spec.nodes if n.group == gid],
                [g for g in self.spec.groups if g.parent == gid])
