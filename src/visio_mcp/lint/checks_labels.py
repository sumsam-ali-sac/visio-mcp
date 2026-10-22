"""Rules about label length, duplicates, edge labelling and the title."""

from __future__ import annotations

from collections.abc import Iterator

from visio_mcp.lint.context import Context, quoted, words
from visio_mcp.lint.finding import Finding

MAX_LABEL_WORDS = 5
MAX_EDGE_LABEL_WORDS = 4

ARCH_TYPES = {"architecture", "cloud", "dataflow", "c4-context", "c4-container", "deployment"}


def check_label_length(c: Context) -> Iterator[Finding]:
    long = [n.id for n in c.spec.nodes if words(n.label) > MAX_LABEL_WORDS]
    long += [g.id for g in c.spec.groups if words(g.label) > MAX_LABEL_WORDS]
    if long:
        yield Finding("label-length", "medium", f"Labels of {quoted(long)} exceed {MAX_LABEL_WORDS} words; keep "
                      "the name short and move detail to 'technology' or 'description'.")


def check_duplicate_label(c: Context) -> Iterator[Finding]:
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
            yield Finding("duplicate-label", "medium", f"Nodes {quoted(ids)} share the label '{label}'; make labels "
                          "unique or merge the nodes.")


def check_edge_labels(c: Context) -> Iterator[Finding]:
    if c.type not in ARCH_TYPES or len(c.spec.edges) < 3:
        return
    unlabeled = sum(not e.label for e in c.spec.edges)
    if unlabeled * 2 > len(c.spec.edges):
        yield Finding("edge-labels", "medium", f"{unlabeled} of {len(c.spec.edges)} edges are unlabeled; label "
                      "them with the protocol or verb (HTTPS, SQL, AMQP, 'publishes', 'reads').")


def check_edge_label_length(c: Context) -> Iterator[Finding]:
    long = [f"{e.source}->{e.target}" for e in c.spec.edges if words(e.label) > MAX_EDGE_LABEL_WORDS]
    if long:
        yield Finding("edge-label-length", "low", f"Edge labels on {quoted(long)} exceed {MAX_EDGE_LABEL_WORDS} "
                      "words; use a short verb or protocol ('publishes', 'HTTPS').")


def check_title(c: Context) -> Iterator[Finding]:
    if not c.spec.title or c.spec.title.strip().lower() == "diagram":
        yield Finding("title", "low", "Give the diagram a specific title naming the system and view, e.g. "
                      "'Orders Platform - Container View'.")
    elif not c.spec.subtitle:
        yield Finding("title", "low", "Add a subtitle with scope, audience and date or version.")
