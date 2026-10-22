"""Group nesting: which items each scope holds and how edges lift between scopes."""

from __future__ import annotations

from visio_mcp.spec import DiagramSpec

Scope = str | None  # a group id, or None for the page


class Hierarchy:
    """Nesting of nodes in groups. Groups without any node inside are dropped."""

    def __init__(self, spec: DiagramSpec) -> None:
        self.parent: dict[str, str | None] = {g.id: g.parent for g in spec.groups}
        self.node_group = {n.id: n.group for n in spec.nodes}
        self.index = {n.id: i for i, n in enumerate(spec.nodes)}
        rank = {g.id: i for i, g in enumerate(spec.groups)}
        first: dict[str, int] = {}
        for n in spec.nodes:
            for g in self.ancestors(n.id):
                first.setdefault(g, self.index[n.id])
        self.groups = sorted(first, key=lambda g: rank[g])  # live groups, spec order
        children: dict[Scope, list[str]] = {None: []}
        for g in self.groups:
            children[g] = []
        for n in spec.nodes:
            children[n.group].append(n.id)
        for g in self.groups:
            children[self.parent[g]].append(g)
        order = {**self.index, **first}
        self.children = {s: sorted(items, key=lambda i: (order[i], i in rank)) for s, items in children.items()}

    def is_group(self, item: str) -> bool:
        return item in self.parent

    def ancestors(self, node: str) -> list[str]:
        """Groups holding node, innermost first."""
        out, cur = [], self.node_group.get(node)
        while cur:
            out.append(cur)
            cur = self.parent.get(cur)
        return out

    def path(self, node: str) -> list[Scope]:
        """Scopes holding node, page first."""
        return [None, *reversed(self.ancestors(node))]

    def lift(self, a: str, b: str) -> tuple[Scope, str, str]:
        """Lowest common scope of two nodes and the items standing for them there."""
        pa, pb = self.path(a), self.path(b)
        ia, ib = [*pa[1:], a], [*pb[1:], b]
        k = 0
        while k + 1 < min(len(pa), len(pb)) and pa[k + 1] == pb[k + 1]:
            k += 1
        return pa[k], ia[k], ib[k]

    def item_in(self, scope: Scope, node: str) -> str:
        """The item of scope that contains node (the node itself or a child group)."""
        p = self.path(node)
        items = [*p[1:], node]
        return items[p.index(scope)]

    def between(self, node: str, scope: Scope) -> list[str]:
        """Groups holding node strictly inside scope, innermost first."""
        out = []
        for g in self.ancestors(node):
            if g == scope:
                break
            out.append(g)
        return out

    def depth_first(self) -> list[str]:
        """Live groups, children before parents."""
        out: list[str] = []

        def visit(s: Scope) -> None:
            for it in self.children[s]:
                if self.is_group(it):
                    visit(it)
                    out.append(it)

        visit(None)
        return out
