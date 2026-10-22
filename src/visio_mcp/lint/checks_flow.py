"""Rules for flow-style diagrams: decisions, terminals, C4 context, ERD cardinality and state events."""

from __future__ import annotations

import re
from collections.abc import Iterator

from visio_mcp.lint.context import Context, quoted
from visio_mcp.lint.finding import Finding
from visio_mcp.lint.kinds import CONTAINER_NAMES, END_NAMES, START_NAMES

CARDINALITY = re.compile(r"(\d|\*|\.\.|\b[nm]\b|\bmany\b|\bone\b|\bzero\b)", re.IGNORECASE)


def check_decision(c: Context) -> Iterator[Finding]:
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


def check_terminal(c: Context) -> Iterator[Finding]:
    if c.type not in ("flowchart", "swimlane", "state"):
        return
    names = {c.info[n.id].name for n in c.spec.nodes}
    has_start = bool(names & START_NAMES)
    has_end = bool(names & END_NAMES)
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


def check_c4_context(c: Context) -> Iterator[Finding]:
    if c.type != "c4-context":
        return
    inner = [n.id for n in c.spec.nodes
             if c.info[n.id].category in ("data", "integration") or c.info[n.id].provider
             or c.info[n.id].name in CONTAINER_NAMES]
    if inner:
        yield Finding("c4-context", "medium", f"C4 context shows your system as ONE box; {quoted(inner)} are "
                      "containers - move them to a c4-container diagram.")
    for g in c.spec.groups:
        if g.kind == "system" and len(c.members(g.id)[0]) > 1:
            yield Finding("c4-context", "medium", f"System boundary '{g.id}' holds several nodes; at context level "
                          "draw the system as a single node and detail it in a c4-container diagram.")


def check_erd(c: Context) -> Iterator[Finding]:
    if c.type != "erd" or not c.spec.edges:
        return
    bad = [f"{e.source}->{e.target}" for e in c.spec.edges if not CARDINALITY.search(e.label)]
    if bad:
        yield Finding("erd-cardinality", "medium", f"Relationships {quoted(bad)} lack cardinality; label them "
                      "like '1..*', '0..1' or '1:N'.")


def check_state_events(c: Context) -> Iterator[Finding]:
    if c.type != "state":
        return
    bad = [f"{e.source}->{e.target}" for e in c.spec.edges
           if not e.label and c.info[e.source].name not in START_NAMES
           and c.info[e.target].name not in END_NAMES]  # completion transitions need no event
    if bad:
        yield Finding("state-events", "medium", f"Transitions {quoted(bad)} are unlabeled; name the triggering "
                      "event, e.g. 'payment received [amount ok] / ship'.")
