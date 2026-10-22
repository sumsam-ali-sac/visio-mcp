"""Rules for cloud diagrams: provider kinds, mixed providers and unknown kinds."""

from __future__ import annotations

from collections.abc import Iterator

from visio_mcp.lint.context import Context, quoted
from visio_mcp.lint.finding import Finding


def check_providers(c: Context) -> Iterator[Finding]:
    if c.type != "cloud":
        return
    provs = list(dict.fromkeys(p for n in c.spec.nodes if (p := c.info[n.id].provider)))
    if not provs:
        yield Finding("provider-kinds", "medium", "Cloud diagram uses no provider kinds; use official service "
                      "kinds (e.g. 'azure-functions', 'aws-lambda', 'gcp-cloud-run') so icons and theme match.")
    elif len(provs) > 1 and sum(g.kind == "cloud" for g in c.spec.groups) < 2:
        yield Finding("mixed-providers", "medium", f"Cloud diagram mixes providers ({', '.join(provs)}); stick to "
                      "one, or if truly multi-cloud put each provider in its own group of kind 'cloud'.")


def check_unknown_kind(c: Context) -> Iterator[Finding]:
    unknown = [n.id for n in c.spec.nodes if not c.info[n.id].known]
    if unknown:
        kinds = list(dict.fromkeys(c.info[i].name for i in unknown))
        yield Finding("unknown-kind", "medium", f"Unknown kind(s) {quoted(kinds)}; pick kinds from list_kinds "
                      "or they draw as plain rectangles.")
