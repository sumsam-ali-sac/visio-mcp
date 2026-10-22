"""Authoring instructions shipped with the server, so any MCP client knows how to use it."""

from __future__ import annotations

from typing import Literal

GUIDE = """\
# Authoring professional Visio diagrams

You describe a diagram by MEANING (nodes, edges, groups, type). The server picks shapes,
lays everything out, applies a theme (fonts, colors, line styles), adds a title block and a
legend, and draws it in Visio. Never place shapes by coordinates.

## 1. Decide what the diagram answers
One diagram, one question, one audience. Pick `type`:
flowchart (process with decisions) | architecture (components and data flow) |
cloud (Azure/AWS/GCP services) | c4-context | c4-container | deployment | network |
dataflow | pipeline (CI/CD, ETL) | erd | org | swimlane (who does what) | state | mindmap.
Then call get_diagram_rules(type) — it has the conventions, a checklist and an example.
Big systems become several diagrams (context, containers, deployment), not one huge one.

## 2. Write ONE spec
- title: short and specific ("Checkout Service — Containers"). subtitle: scope, version, date.
- nodes (5-30): id (short, snake_case), label (Title Case, at most 4 words), kind
  (from list_kinds — cloud kinds like azure-functions / aws-lambda / gcp-cloud-run for cloud
  diagrams), technology ("Python / FastAPI"), description (one short sentence, optional),
  emphasis (true on the 1-2 nodes the diagram is about).
- edges: source -> target, label = protocol or verb in lowercase ("HTTPS", "publishes order
  events", "yes"). style: solid = synchronous, dashed = asynchronous/event, dotted = optional.
- groups: tiers, trust boundaries, cloud hierarchy, lanes. kind sets the look:
  tier | system | boundary | cloud | region | zone | network | subnet | cluster | environment |
  lane | external. Nest with parent (cloud > region > network > subnet).
- type/layout/theme may stay "auto": layout follows the type (flowchart top-to-bottom,
  architecture left-to-right, org as a tree, swimlanes as lanes); theme follows the cloud
  provider (azure / aws / gcp), c4 for C4 diagrams, else professional. Themes: list_themes.
Labels are cased automatically, but write them well: nouns for nodes, verbs for edges.

## 3. Check, then render once
Optional: lint_diagram(spec) lists rule findings without drawing. Then call render_diagram
once with the whole spec. It draws live in the user's Visio window and returns overlaps,
warnings, suggestions (rule findings) and a PNG preview.

## 4. Review loop (at most 3 passes)
1. overlaps must be empty; read every warning and suggestion.
2. Look at the preview: readable labels, obvious flow, tidy groups, no tangles.
3. Fix with ONE patch_diagram batch per pass: update_node (label, kind, group, technology,
   description, emphasis), update_edge (label, style, arrow), add_node, add_edge, add_group,
   remove (node, group or "source->target"), update_diagram (title, subtitle, theme, layout,
   legend), relayout. The diagram re-lays-out and keeps its styling.
4. Stop when it is presentable; report what remains after three passes.

## Example
```json
{
  "title": "Orders Platform",
  "subtitle": "Container view · v2",
  "type": "architecture",
  "groups": [
    {"id": "edge", "label": "Edge", "kind": "tier"},
    {"id": "core", "label": "Order Services", "kind": "system"},
    {"id": "data", "label": "Data", "kind": "tier"}
  ],
  "nodes": [
    {"id": "customer", "label": "Customer", "kind": "user"},
    {"id": "web", "label": "Storefront", "kind": "webapp", "technology": "Next.js", "group": "edge"},
    {"id": "api", "label": "Orders API", "kind": "api", "technology": "Python / FastAPI",
     "group": "core", "emphasis": true},
    {"id": "worker", "label": "Fulfilment Worker", "kind": "service", "group": "core"},
    {"id": "bus", "label": "Order Events", "kind": "queue", "technology": "Kafka", "group": "core"},
    {"id": "db", "label": "Orders DB", "kind": "database", "technology": "PostgreSQL", "group": "data"}
  ],
  "edges": [
    {"source": "customer", "target": "web", "label": "HTTPS"},
    {"source": "web", "target": "api", "label": "REST"},
    {"source": "api", "target": "db", "label": "reads/writes"},
    {"source": "api", "target": "bus", "label": "publishes", "style": "dashed"},
    {"source": "bus", "target": "worker", "label": "consumes", "style": "dashed"}
  ]
}
```
"""


def diagram_prompt(subject: str, source: Literal["prompt", "repo"] = "prompt", diagram_type: str = "auto") -> str:
    """Instructions for drawing `subject`, from a description or by exploring a repo."""
    kind = "" if diagram_type == "auto" else f" as a {diagram_type} diagram"
    rules = (
        f"Call get_diagram_rules('{diagram_type}') for its conventions. "
        if diagram_type != "auto" else "Pick the diagram type, then call get_diagram_rules(type). "
    )
    if source == "repo":
        return (
            f"Draw a professional Visio diagram of the repository {subject}{kind}.\n\n"
            "First explore the repo and pick the view that answers the request:\n"
            "- Context and purpose: README, docs/, ADRs.\n"
            "- Components: package boundaries, entrypoints, imports between modules and services.\n"
            "- Integrations: config and env files (DATABASE_URL, queue/topic names, service URLs).\n"
            "- Deployment: docker-compose, Kubernetes manifests, Helm, Terraform, Bicep, CloudFormation.\n"
            "- Data model (ERD): ORM models, schema files, migrations.\n"
            "- Pipelines: .github/workflows, azure-pipelines.yml, .gitlab-ci.yml.\n\n"
            "Only draw what the code shows. Then read get_authoring_guide. " + rules +
            "Write one DiagramSpec, call render_diagram once, and review with patch_diagram.\n"
        )
    return (
        f"Draw a professional Visio diagram of: {subject}{kind}\n\n"
        "Read get_authoring_guide if you have not yet. " + rules +
        "Write one DiagramSpec, call render_diagram once, then review the overlaps, warnings, "
        "suggestions and preview and fix them with patch_diagram.\n"
    )
