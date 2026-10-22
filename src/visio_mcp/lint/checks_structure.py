"""Rules about diagram size, groups, placement and layout."""

from __future__ import annotations

from collections.abc import Iterator

from visio_mcp.lint.context import Context, quoted
from visio_mcp.lint.finding import Finding

MAX_NODES = 30
MAX_NESTING = 4  # levels of groups, e.g. cloud > region > network > subnet

NO_ORPHAN_TYPES = {"org", "mindmap"}
INTERNAL_GROUPS = {"system", "tier", "network", "subnet", "cluster", "zone", "region"}
STAGE_TYPES = {"dataflow", "pipeline"}  # tiers there are stages (Sources, Sinks), not ownership
WRAPPER_GROUPS = {"lane", "tier", "subnet", "zone", "region", "network", "cloud", "external", "cluster"}
# cloud > region/network > subnet > cluster: a child must not rank above its parent.
GROUP_RANK = {"cloud": 0, "region": 1, "network": 1, "subnet": 2, "cluster": 3}


def check_size(c: Context) -> Iterator[Finding]:
    n = len(c.spec.nodes)
    if n > MAX_NODES:
        yield Finding("size", "high", f"{n} nodes is too many for one diagram (aim for 5-30); split it into "
                      "separate views (context, container, deployment) or one diagram per subsystem.")


def check_lane(c: Context) -> Iterator[Finding]:
    if c.type != "swimlane":
        return
    if not any(g.kind == "lane" for g in c.spec.groups):
        yield Finding("lane", "high", "Swimlane diagram has no groups of kind 'lane'; add one lane per actor "
                      "or department and put every step in one.")
        return
    loose = [n.id for n in c.spec.nodes if not any(g.kind == "lane" for g in c.ancestors(n.group))]
    if loose:
        yield Finding("lane", "high", f"{quoted(loose)} sit outside any lane; set 'group' to the lane of the "
                      "actor who performs each step.")


def check_orphan(c: Context) -> Iterator[Finding]:
    if c.type in NO_ORPHAN_TYPES or len(c.spec.nodes) <= 1:
        return
    lone = [n.id for n in c.spec.nodes if not c.degree[n.id] and c.info[n.id].category != "note"]
    if len(lone) == 1:
        yield Finding("orphan", "medium", f"Node '{lone[0]}' has no connections; connect it or remove it.")
    elif lone:
        yield Finding("orphan", "medium", f"Nodes {quoted(lone)} have no connections; connect them or remove them.")


def check_external(c: Context) -> Iterator[Finding]:
    for n in c.spec.nodes:
        info = c.info[n.id]
        if info.category != "external" and info.name not in ("external-system", "system-external"):
            continue
        chain = c.ancestors(n.group)
        internal = INTERNAL_GROUPS - ({"tier"} if c.type in STAGE_TYPES else set())
        if chain and not any(g.kind == "external" for g in chain) and chain[0].kind in internal:
            yield Finding("external-placement", "medium", f"External system '{n.id}' sits inside internal group "
                          f"'{chain[0].id}'; move it outside your boundary or into a group of kind 'external'.")


def check_nesting(c: Context) -> Iterator[Finding]:
    deepest = max((len(c.ancestors(g.id)) for g in c.spec.groups), default=0)
    if deepest > MAX_NESTING:
        yield Finding("nesting", "medium", f"Groups nest {deepest} levels deep (max {MAX_NESTING}); flatten levels "
                      "that add no meaning or split the diagram.")
    for g in c.spec.groups:
        p = c.groups.get(g.parent or "")
        if p and g.kind in GROUP_RANK and p.kind in GROUP_RANK and GROUP_RANK[g.kind] < GROUP_RANK[p.kind]:
            yield Finding("nesting-order", "medium", f"Group '{g.id}' ({g.kind}) is inside '{p.id}' ({p.kind}); nest "
                          "outer to inner: cloud > region > network > subnet > cluster/workload.")


def check_layout(c: Context) -> Iterator[Finding]:
    lay, t = c.spec.layout, c.type
    if t == "swimlane" and not lay.startswith("swimlane"):
        yield Finding("layout", "medium", f"Swimlane diagram uses layout '{lay}'; use 'swimlane-lr' (or "
                      "'swimlane-tb') so groups render as lanes.")
    elif t != "swimlane" and lay.startswith("swimlane"):
        yield Finding("layout", "medium", f"Layout '{lay}' needs lane groups; set type 'swimlane' with groups "
                      "of kind 'lane', or use a flowchart layout.")
    elif t == "org" and not lay.startswith("tree"):
        yield Finding("layout", "low", f"Org chart uses layout '{lay}'; use 'tree-tb' for a hierarchy.")


def check_single_member(c: Context) -> Iterator[Finding]:
    lone = []
    for g in c.spec.groups:
        if g.kind in WRAPPER_GROUPS:
            continue
        nodes, kids = c.members(g.id)
        if len(nodes) == 1 and not kids:
            lone.append(g.id)
    if lone:
        yield Finding("single-member", "low", f"Group(s) {quoted(lone)} contain a single node; remove the group "
                      "or add the related nodes it is meant to frame.")
