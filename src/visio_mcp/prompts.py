"""Authoring instructions shipped with the server, so any MCP client knows how to use it."""

from __future__ import annotations

from typing import Literal

GUIDE = """\
# Authoring Visio diagrams

Write ONE DiagramSpec that describes the diagram by meaning (nodes, edges, groups, layout).
Never place shapes by coordinates; the server lays it out and draws it in Visio.

## 1. Pick a layout
- flowchart-tb: processes, pipelines, decisions (default).
- flowchart-lr: architecture and data flow, left to right (clients -> services -> data).
- tree-tb: hierarchies, org charts, containment (root on top). tree-lr: same, root on the left.
- radial: one hub with spokes (a gateway or core service and its clients).
- compact: big flat sets where order matters little (ERDs, inventories).
- circular / none: rare. "none" keeps your own x/y values.

## 2. Size it
- Aim for 5 to 30 nodes. Bigger systems become several diagrams: context (system and
  actors), containers (apps, services, stores), deployment (hosts, networks).
- Each diagram answers one question.

## 3. Write the spec
- Ids: short, unique, no spaces (api, orders_db). Labels: at most 4 words.
- kind: a semantic kind from list_kinds (service, database, queue, user, decision, ...).
  Call list_kinds when unsure. Do not guess shape names.
- groups: tiers (Presentation, Services, Data), trust boundaries (Internet, VPC), or
  environments. A node sits in at most one group via its "group" field.
- edges: arrows from source to target between nodes only. Add a label only when it adds
  meaning ("HTTPS", "SQL", "yes"/"no"). style "dashed" for async or optional flows.
- Decisions: kind "decision" with exactly two outgoing edges labeled with the branches.
- Titles: short and descriptive.

## 4. Render once
Call render_diagram once with the whole spec and a meaningful name. Never render node by node.

## 5. Review loop (at most 3 passes)
1. Read the result. overlaps must be empty. Read every warning.
2. Look at the PNG preview: labels readable, flow obvious, no tangled edges.
3. If a kind fell back to a plain rectangle (a warning says so), choose another kind
   from list_kinds and patch it with update_node.
4. Fix with patch_diagram, one batch per pass: update_node (label, fill), add_node,
   add_edge, remove (node, group or "source->target" edge), move (single shape),
   relayout (new layout style for the whole page).
5. Stop once it is presentable. Two passes is typical. After three, report what remains.
Use inspect_diagram for exact positions and the overlap list of the open diagram.

## 6. Tips
- Keep the main flow in one direction; avoid long backward edges.
- Prefer relayout over many move ops.
- Use fill sparingly, to highlight one tier or the failing path.
- Export png only unless the user asks for svg or pdf.

## Example: a small web architecture
```json
{
  "title": "Order service",
  "layout": "flowchart-lr",
  "groups": [{"id": "edge", "label": "Edge"}, {"id": "core", "label": "Core"}],
  "nodes": [
    {"id": "user", "label": "Customer", "kind": "user"},
    {"id": "web", "label": "Web app", "kind": "webapp", "group": "edge"},
    {"id": "api", "label": "Orders API", "kind": "api", "group": "core"},
    {"id": "db", "label": "Orders DB", "kind": "database", "group": "core"}
  ],
  "edges": [
    {"source": "user", "target": "web"},
    {"source": "web", "target": "api", "label": "HTTPS"},
    {"source": "api", "target": "db", "label": "SQL"}
  ]
}
```
"""


def diagram_prompt(subject: str, source: Literal["prompt", "repo"] = "prompt") -> str:
    """Instructions for drawing `subject`, from a description or by exploring a repo."""
    if source == "repo":
        return (
            f"Draw a Visio diagram of the repository {subject}.\n\n"
            "First explore the repo and pick the view that answers the request:\n"
            "- Context and purpose: README, docs/, ADRs.\n"
            "- Components: package boundaries and imports between them (src/ folders, modules, services).\n"
            "- Deployment: docker-compose.yml, Kubernetes manifests, Helm charts, Terraform, Bicep.\n"
            "- Data model (ERD): ORM models, schema files, migrations.\n"
            "- API map: routes, controllers, OpenAPI/Swagger files.\n\n"
            "Note the nodes and edges you found, then follow the authoring guide. Call "
            "get_authoring_guide if you have not read it yet: write one DiagramSpec, call "
            "render_diagram once, and review with patch_diagram.\n"
        )
    return (
        f"Draw a Visio diagram of: {subject}\n\n"
        "Follow the authoring guide. Call get_authoring_guide if you have not read it yet: "
        "choose the layout, write one DiagramSpec, call render_diagram once, then review the "
        "overlaps, warnings and preview and fix issues with patch_diagram.\n"
    )
