"""Diagram ground rules in code: normalize a spec (resolve 'auto', fix casing) and lint it.

`normalize` makes the mechanical fixes nobody should have to ask for. `lint` reports the
judgment calls back to the agent as short, actionable one-liners, each prefixed with a
rule code (``[orphan] Node 'cache' has no connections; ...``). The prose behind every
rule lives in ``visio_mcp/rules/*.md`` (see ``visio_mcp.rules``).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from visio_mcp import catalog
from visio_mcp.spec import DiagramSpec, Edge, Group, Node
from visio_mcp.style import sentence_case, title_case

Severity = Literal["high", "medium", "low"]
SEVERITY_RANK: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
MAX_FINDINGS = 15
MAX_NODES = 30
MAX_LABEL_WORDS = 5
MAX_EDGE_LABEL_WORDS = 4
MAX_NESTING = 4  # levels of groups, e.g. cloud > region > network > subnet
MAX_EMPHASIS = 2
MAX_CUSTOM_COLORS = 3

PROVIDERS = ("azure", "aws", "gcp")
_PREFIXES = {"azure-": "azure", "aws-": "aws", "gcp-": "gcp", "google-": "gcp", "amazon-": "aws"}

# Layout and theme defaults per diagram type.
LAYOUTS: dict[str, str] = {
    "flowchart": "flowchart-tb",
    "architecture": "flowchart-lr",
    "cloud": "flowchart-lr",
    "c4-context": "flowchart-lr",
    "c4-container": "flowchart-lr",
    "deployment": "flowchart-lr",
    "network": "flowchart-tb",
    "dataflow": "flowchart-lr",
    "pipeline": "flowchart-lr",
    "erd": "flowchart-lr",
    "org": "tree-tb",
    "swimlane": "swimlane-lr",
    "state": "flowchart-tb",
    "mindmap": "radial",
}

# Category by kind name, used when the catalog does not know a kind or leaves it generic.
_NAME_CATEGORY: dict[str, str] = {
    **dict.fromkeys(("start", "end", "initial", "final", "initial-state", "final-state", "terminator"), "terminal"),
    **dict.fromkeys(("process", "subprocess", "manual", "document", "data", "state", "composite-state"), "flow"),
    **dict.fromkeys(("decision", "choice"), "decision"),
    **dict.fromkeys(("database", "cache", "storage"), "data"),
    **dict.fromkeys(("service", "function", "server", "container", "c4-container"), "compute"),
    **dict.fromkeys(("queue", "api", "gateway"), "integration"),
    **dict.fromkeys(("client", "mobile", "webapp", "pc"), "client"),
    **dict.fromkeys(("user", "person"), "person"),
    **dict.fromkeys(("external", "external-system", "system-external"), "external"),
    **dict.fromkeys(("router", "switch", "loadbalancer", "cloud", "internet"), "network"),
    "firewall": "security",
    **dict.fromkeys(("executive", "manager", "position"), "org"),
    "entity": "entity",
    "note": "note",
}
_STATE_NAMES = {"state", "composite-state", "initial-state", "final-state", "initial", "final"}
_START_NAMES = {"start", "initial", "initial-state", "terminator"}
_END_NAMES = {"end", "final", "final-state"}
_SYSTEM_NAMES = {"system", "software-system", "c4-system", "external-system", "system-external"}
_CONTAINER_NAMES = {"container", "c4-container"}
_NETWORK_GEAR = {"router", "switch", "firewall", "access-point", "modem", "hub"}
_MINDMAP_NAMES = {"mindmap-root", "mindmap-topic", "central-idea"}
_PIPELINE_NAMES = {"pipeline", "build", "test", "deploy"}
_ARCH_TYPES = {"architecture", "cloud", "dataflow", "c4-context", "c4-container", "deployment"}
_NO_ORPHAN_TYPES = {"org", "mindmap"}
_INTERNAL_GROUPS = {"system", "tier", "network", "subnet", "cluster", "zone", "region"}
_STAGE_TYPES = {"dataflow", "pipeline"}  # tiers there are stages (Sources, Sinks), not ownership
_WRAPPER_GROUPS = {"lane", "tier", "subnet", "zone", "region", "network", "cloud", "external", "cluster"}
# cloud > region/network > subnet > cluster: a child must not rank above its parent.
_GROUP_RANK = {"cloud": 0, "region": 1, "network": 1, "subnet": 2, "cluster": 3}
_CARDINALITY = re.compile(r"(\d|\*|\.\.|\b[nm]\b|\bmany\b|\bone\b|\bzero\b)", re.IGNORECASE)


@dataclass(frozen=True)
class KindInfo:
    name: str  # canonical kind name (or the raw kind, lowercased, when unknown)
    category: str
    provider: str | None
    known: bool


def kind_info(kind: str) -> KindInfo:
    """Category and provider of a kind, from the catalog with name-based fallbacks."""
    raw = kind.strip().lower()
    k = catalog.lookup(kind)
    name = k.name if k else raw
    provider = getattr(k, "provider", None) if k else None
    if not provider:
        provider = next((p for pre, p in _PREFIXES.items() if raw.startswith(pre) or name.startswith(pre)), None)
    category = getattr(k, "category", "generic") if k else "generic"
    if category in ("", "generic"):
        category = _NAME_CATEGORY.get(name, _NAME_CATEGORY.get(raw, category or "generic"))
    return KindInfo(name, category, provider, k is not None)


# --- normalize ------------------------------------------------------------------------------


def infer_type(spec: DiagramSpec) -> str:
    """Guess the diagram type from node kinds and group kinds."""
    infos = [kind_info(n.kind) for n in spec.nodes]
    names = {i.name for i in infos}
    cats = Counter(i.category for i in infos)
    gkinds = {g.kind for g in spec.groups}
    if "lane" in gkinds:
        return "swimlane"
    if names & _STATE_NAMES:
        return "state"
    if cats["entity"]:
        return "erd"
    if cats["org"]:
        return "org"
    if names & _MINDMAP_NAMES:
        return "mindmap"
    if names & _PIPELINE_NAMES:
        return "pipeline"
    if cats["decision"] or cats["terminal"]:
        return "flowchart"
    if any(i.provider for i in infos):
        return "cloud"
    if cats["person"] and (names & _CONTAINER_NAMES or "system" in gkinds):
        return "c4-container"
    if cats["person"] and names & _SYSTEM_NAMES:
        return "c4-context"
    if names & {"router", "switch"} or (cats["network"] + cats["security"]) * 2 >= len(infos):
        return "network"
    if gkinds & {"environment", "cluster"} or "server" in names:
        return "deployment"
    return "architecture"


def dominant_provider(spec: DiagramSpec) -> str | None:
    """Most used provider among the nodes (ties go to the first one seen)."""
    counts = Counter(p for n in spec.nodes if (p := kind_info(n.kind).provider))
    if not counts:
        return None
    best = max(counts.values())
    return next(p for p in counts if counts[p] == best)


def humanize(ident: str) -> str:
    """'orders_db' -> 'Orders DB', 'paymentService' -> 'Payment Service'."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", ident)
    return title_case(" ".join(re.sub(r"[_\-.]+", " ", text).split()))


def _clean(text: str) -> str:
    return " ".join(text.split())


def normalize(spec: DiagramSpec) -> tuple[DiagramSpec, list[str]]:
    """Resolve type/layout/theme 'auto', fill empty labels, tidy whitespace and apply label
    casing (Title Case for nodes and groups, lowercase phrases for edges).

    Returns a new spec and a short list of human-readable notes on what changed.
    """
    notes: list[str] = []
    dtype = spec.type
    if dtype == "auto":
        dtype = infer_type(spec)
        notes.append(f"type auto -> {dtype}")
    layout = spec.layout
    if layout == "auto":
        layout = LAYOUTS.get(dtype, "flowchart-lr")
        notes.append(f"layout auto -> {layout}")
    theme = spec.theme
    if theme.strip().lower() in ("auto", ""):
        if dtype == "cloud":
            theme = dominant_provider(spec) or "professional"
        elif dtype.startswith("c4-"):
            theme = "c4"
        else:
            theme = "professional"
        notes.append(f"theme auto -> {theme}")

    recased = filled = 0

    def node_label(label: str, ident: str) -> str:
        nonlocal recased, filled
        clean = _clean(label)
        if not clean:
            filled += 1
            return humanize(ident)
        out = title_case(clean)
        recased += out != label
        return out

    def edge_label(label: str) -> str:
        nonlocal recased
        clean = _clean(label)
        out = sentence_case(clean) if clean else ""
        recased += out != label
        return out

    nodes = [n.model_copy(update={
        "label": node_label(n.label, n.id),
        "technology": _clean(n.technology),
        "description": _clean(n.description),
    }) for n in spec.nodes]
    groups = [g.model_copy(update={"label": node_label(g.label, g.id)}) for g in spec.groups]
    edges = [e.model_copy(update={"label": edge_label(e.label)}) for e in spec.edges]
    if filled:
        notes.append(f"filled {filled} empty label(s) from ids")
    if recased:
        notes.append(f"recased {recased} label(s) (Title Case nodes/groups, lowercase edge phrases)")
    out = spec.model_copy(update={
        "type": dtype, "layout": layout, "theme": theme, "title": _clean(spec.title),
        "subtitle": _clean(spec.subtitle), "nodes": nodes, "edges": edges, "groups": groups,
    })
    return out, notes


# --- lint ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def _names(items: list[str], limit: int = 3) -> str:
    shown = ", ".join(f"'{i}'" for i in items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def _words(text: str) -> int:
    return len(text.split())


class _Ctx:
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


def findings(spec: DiagramSpec) -> list[Finding]:
    """All rule findings, most important first (uncapped)."""
    c = _Ctx(spec)
    out: list[Finding] = []
    for rule in _RULES:
        out.extend(rule(c))
    return sorted(out, key=lambda f: SEVERITY_RANK[f.severity])  # stable: rule order within a severity


def lint(spec: DiagramSpec) -> list[str]:
    """Rule findings for a normalized spec. Empty when it follows the ground rules."""
    found = [str(f) for f in findings(spec)]
    if len(found) > MAX_FINDINGS:
        rest = len(found) - (MAX_FINDINGS - 1)
        found = found[: MAX_FINDINGS - 1] + [f"[more] {rest} more findings not shown; fix these and re-check."]
    return found


# Each rule takes the context and yields findings. Order within a severity = list order.


def _r_size(c: _Ctx):
    n = len(c.spec.nodes)
    if n > MAX_NODES:
        yield Finding("size", "high", f"{n} nodes is too many for one diagram (aim for 5-30); split it into "
                      "separate views (context, container, deployment) or one diagram per subsystem.")


def _r_decision(c: _Ctx):
    for n in c.spec.nodes:
        if c.info[n.id].category != "decision":
            continue
        outs = c.out[n.id]
        if len(outs) < 2:
            yield Finding("decision", "high", f"Decision '{n.id}' has {len(outs)} outgoing edge(s); give it one "
                          "labeled edge per branch (e.g. 'yes' and 'no').")
        elif any(not e.label for e in outs):
            yield Finding("decision", "high", f"Label every outgoing edge of decision '{n.id}' with its branch "
                          "('yes'/'no' or the condition).")


def _r_lane(c: _Ctx):
    if c.type != "swimlane":
        return
    if not any(g.kind == "lane" for g in c.spec.groups):
        yield Finding("lane", "high", "Swimlane diagram has no groups of kind 'lane'; add one lane per actor "
                      "or department and put every step in one.")
        return
    loose = [n.id for n in c.spec.nodes if not any(g.kind == "lane" for g in c.ancestors(n.group))]
    if loose:
        yield Finding("lane", "high", f"{_names(loose)} sit outside any lane; set 'group' to the lane of the "
                      "actor who performs each step.")


def _r_orphan(c: _Ctx):
    if c.type in _NO_ORPHAN_TYPES or len(c.spec.nodes) <= 1:
        return
    lone = [n.id for n in c.spec.nodes if not c.degree[n.id] and c.info[n.id].category != "note"]
    if len(lone) == 1:
        yield Finding("orphan", "medium", f"Node '{lone[0]}' has no connections; connect it or remove it.")
    elif lone:
        yield Finding("orphan", "medium", f"Nodes {_names(lone)} have no connections; connect them or remove them.")


def _r_terminal(c: _Ctx):
    if c.type not in ("flowchart", "swimlane", "state"):
        return
    names = {c.info[n.id].name for n in c.spec.nodes}
    has_start = bool(names & _START_NAMES)
    has_end = bool(names & _END_NAMES)
    if c.type == "state":
        if not has_start:
            yield Finding("terminal", "medium", "State machine has no initial state; add a 'start' node with one "
                          "transition into the first state.")
        return
    if c.type == "flowchart" or has_start or has_end:
        missing = [w for w, ok in (("start", has_start), ("end", has_end)) if not ok]
        if missing:
            yield Finding("terminal", "medium", f"Flow has no {' or '.join(missing)} node; add "
                          f"{' and '.join(repr(m) for m in missing)} terminator(s) so readers see where it begins and ends.")


def _r_c4_context(c: _Ctx):
    if c.type != "c4-context":
        return
    inner = [n.id for n in c.spec.nodes
             if c.info[n.id].category in ("data", "integration") or c.info[n.id].provider
             or c.info[n.id].name in _CONTAINER_NAMES]
    if inner:
        yield Finding("c4-context", "medium", f"C4 context shows your system as ONE box; {_names(inner)} are "
                      "containers - move them to a c4-container diagram.")
    for g in c.spec.groups:
        if g.kind == "system" and len(c.members(g.id)[0]) > 1:
            yield Finding("c4-context", "medium", f"System boundary '{g.id}' holds several nodes; at context level "
                          "draw the system as a single node and detail it in a c4-container diagram.")


def _r_providers(c: _Ctx):
    if c.type != "cloud":
        return
    provs = list(dict.fromkeys(p for n in c.spec.nodes if (p := c.info[n.id].provider)))
    if not provs:
        yield Finding("provider-kinds", "medium", "Cloud diagram uses no provider kinds; use official service "
                      "kinds (e.g. 'azure-functions', 'aws-lambda', 'gcp-cloud-run') so icons and theme match.")
    elif len(provs) > 1 and sum(g.kind == "cloud" for g in c.spec.groups) < 2:
        yield Finding("mixed-providers", "medium", f"Cloud diagram mixes providers ({', '.join(provs)}); stick to "
                      "one, or if truly multi-cloud put each provider in its own group of kind 'cloud'.")


def _r_unknown_kind(c: _Ctx):
    unknown = [n.id for n in c.spec.nodes if not c.info[n.id].known]
    if unknown:
        kinds = list(dict.fromkeys(c.info[i].name for i in unknown))
        yield Finding("unknown-kind", "medium", f"Unknown kind(s) {_names(kinds)}; pick kinds from list_kinds "
                      "or they draw as plain rectangles.")


def _r_label_length(c: _Ctx):
    long = [n.id for n in c.spec.nodes if _words(n.label) > MAX_LABEL_WORDS]
    long += [g.id for g in c.spec.groups if _words(g.label) > MAX_LABEL_WORDS]
    if long:
        yield Finding("label-length", "medium", f"Labels of {_names(long)} exceed {MAX_LABEL_WORDS} words; keep "
                      "the name short and move detail to 'technology' or 'description'.")


def _r_duplicate_label(c: _Ctx):
    if c.type in ("org", "mindmap"):
        return
    seen: dict[str, list[str]] = {}
    for n in c.spec.nodes:
        if c.info[n.id].category in ("terminal", "note"):
            continue
        seen.setdefault(n.label.strip().lower(), []).append(n.id)
    for ids in seen.values():
        if len(ids) > 1:
            label = next(n.label for n in c.spec.nodes if n.id == ids[0])
            yield Finding("duplicate-label", "medium", f"Nodes {_names(ids)} share the label '{label}'; make labels "
                          "unique or merge the nodes.")


def _r_erd(c: _Ctx):
    if c.type != "erd" or not c.spec.edges:
        return
    bad = [f"{e.source}->{e.target}" for e in c.spec.edges if not _CARDINALITY.search(e.label)]
    if bad:
        yield Finding("erd-cardinality", "medium", f"Relationships {_names(bad)} lack cardinality; label them "
                      "like '1..*', '0..1' or '1:N'.")


def _r_state_events(c: _Ctx):
    if c.type != "state":
        return
    bad = [f"{e.source}->{e.target}" for e in c.spec.edges
           if not e.label and c.info[e.source].name not in _START_NAMES]
    if bad:
        yield Finding("state-events", "medium", f"Transitions {_names(bad)} are unlabeled; name the triggering "
                      "event, e.g. 'payment received [amount ok] / ship'.")


def _r_edge_labels(c: _Ctx):
    if c.type not in _ARCH_TYPES or len(c.spec.edges) < 3:
        return
    unlabeled = sum(not e.label for e in c.spec.edges)
    if unlabeled * 2 > len(c.spec.edges):
        yield Finding("edge-labels", "medium", f"{unlabeled} of {len(c.spec.edges)} edges are unlabeled; label "
                      "them with the protocol or verb (HTTPS, SQL, AMQP, 'publishes', 'reads').")


def _r_external(c: _Ctx):
    for n in c.spec.nodes:
        info = c.info[n.id]
        if info.category != "external" and info.name not in ("external-system", "system-external"):
            continue
        chain = c.ancestors(n.group)
        internal = _INTERNAL_GROUPS - ({"tier"} if c.type in _STAGE_TYPES else set())
        if chain and not any(g.kind == "external" for g in chain) and chain[0].kind in internal:
            yield Finding("external-placement", "medium", f"External system '{n.id}' sits inside internal group "
                          f"'{chain[0].id}'; move it outside your boundary or into a group of kind 'external'.")


def _r_nesting(c: _Ctx):
    deepest = max((len(c.ancestors(g.id)) for g in c.spec.groups), default=0)
    if deepest > MAX_NESTING:
        yield Finding("nesting", "medium", f"Groups nest {deepest} levels deep (max {MAX_NESTING}); flatten levels "
                      "that add no meaning or split the diagram.")
    for g in c.spec.groups:
        p = c.groups.get(g.parent or "")
        if p and g.kind in _GROUP_RANK and p.kind in _GROUP_RANK and _GROUP_RANK[g.kind] < _GROUP_RANK[p.kind]:
            yield Finding("nesting-order", "medium", f"Group '{g.id}' ({g.kind}) is inside '{p.id}' ({p.kind}); nest "
                          "outer to inner: cloud > region > network > subnet > cluster/workload.")


def _r_layout(c: _Ctx):
    lay, t = c.spec.layout, c.type
    if t == "swimlane" and not lay.startswith("swimlane"):
        yield Finding("layout", "medium", f"Swimlane diagram uses layout '{lay}'; use 'swimlane-lr' (or "
                      "'swimlane-tb') so groups render as lanes.")
    elif t != "swimlane" and lay.startswith("swimlane"):
        yield Finding("layout", "medium", f"Layout '{lay}' needs lane groups; set type 'swimlane' with groups "
                      "of kind 'lane', or use a flowchart layout.")
    elif t == "org" and not lay.startswith("tree"):
        yield Finding("layout", "low", f"Org chart uses layout '{lay}'; use 'tree-tb' for a hierarchy.")


def _r_emphasis(c: _Ctx):
    hot = [n.id for n in c.spec.nodes if n.emphasis]
    if len(hot) > MAX_EMPHASIS:
        yield Finding("emphasis", "medium", f"{len(hot)} nodes are emphasized ({_names(hot)}); emphasize at most "
                      f"{MAX_EMPHASIS} so the highlight still means something.")


def _r_title(c: _Ctx):
    if not c.spec.title or c.spec.title.strip().lower() == "diagram":
        yield Finding("title", "low", "Give the diagram a specific title naming the system and view, e.g. "
                      "'Orders Platform - Container View'.")
    elif not c.spec.subtitle:
        yield Finding("title", "low", "Add a subtitle with scope, audience and date or version.")


def _r_single_member(c: _Ctx):
    lone = []
    for g in c.spec.groups:
        if g.kind in _WRAPPER_GROUPS:
            continue
        nodes, kids = c.members(g.id)
        if len(nodes) == 1 and not kids:
            lone.append(g.id)
    if lone:
        yield Finding("single-member", "low", f"Group(s) {_names(lone)} contain a single node; remove the group "
                      "or add the related nodes it is meant to frame.")


def _r_bidirectional(c: _Ctx):
    edges = c.spec.edges
    pairs = {(e.source, e.target) for e in edges}
    both = sum(e.arrow == "both" for e in edges)
    recip = sum(1 for (s, t) in pairs if s < t and (t, s) in pairs)
    count = both + recip
    if count > 2 and count * 5 > len(edges):
        yield Finding("bidirectional", "low", f"{count} edges are two-way; show the direction of the call or "
                      "data flow (who initiates) and keep two-way arrows for truly symmetric links.")


def _r_self_loop(c: _Ctx):
    if c.type == "state":
        return
    loops = [e.source for e in c.spec.edges if e.source == e.target]
    if loops:
        yield Finding("self-loop", "low", f"Self-loops on {_names(loops)}; describe repetition in the node's "
                      "description or model it as an explicit retry step.")


def _r_duplicate_edge(c: _Ctx):
    counts = Counter((e.source, e.target, e.label.lower()) for e in c.spec.edges)
    dup = [f"{s}->{t}" for (s, t, _), k in counts.items() if k > 1]
    if dup:
        yield Finding("duplicate-edge", "low", f"Edges {_names(dup)} are repeated with the same label; keep one.")


def _r_edge_label_length(c: _Ctx):
    long = [f"{e.source}->{e.target}" for e in c.spec.edges if _words(e.label) > MAX_EDGE_LABEL_WORDS]
    if long:
        yield Finding("edge-label-length", "low", f"Edge labels on {_names(long)} exceed {MAX_EDGE_LABEL_WORDS} "
                      "words; use a short verb or protocol ('publishes', 'HTTPS').")


def _r_colors(c: _Ctx):
    fills = {x.fill.upper() for x in [*c.spec.nodes, *c.spec.groups] if x.fill}
    lines = {e.color.upper() for e in c.spec.edges if e.color}
    if len(fills) > MAX_CUSTOM_COLORS or len(lines) > 2:
        yield Finding("colors", "low", f"{len(fills)} custom fills and {len(lines)} custom line colors; let the "
                      "theme color by category and keep overrides to 1-2 for emphasis.")


_RULES = (
    _r_size, _r_decision, _r_lane,
    _r_orphan, _r_terminal, _r_c4_context, _r_providers, _r_unknown_kind, _r_label_length, _r_duplicate_label,
    _r_erd, _r_state_events, _r_edge_labels, _r_external, _r_nesting, _r_layout, _r_emphasis,
    _r_title, _r_single_member, _r_bidirectional, _r_self_loop, _r_duplicate_edge, _r_edge_label_length,
    _r_colors,
)

RULE_CODES: tuple[str, ...] = (
    "size", "decision", "lane", "orphan", "terminal", "c4-context", "provider-kinds", "mixed-providers",
    "unknown-kind", "label-length", "duplicate-label", "erd-cardinality", "state-events", "edge-labels",
    "external-placement", "nesting", "nesting-order", "layout", "emphasis", "title", "single-member",
    "bidirectional", "self-loop", "duplicate-edge", "edge-label-length", "colors",
)
