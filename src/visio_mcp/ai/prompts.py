"""The agent's system prompt and first message: the brain of the repo-to-diagram product."""

from __future__ import annotations

import json

# Where to look first, per diagram type (complements the rules text).
EVIDENCE: dict[str, str] = {
    "architecture": "entrypoints (main.py, app.py, server.ts, Program.cs), service folders, HTTP clients and "
    "the URLs they call, config/env files (DATABASE_URL, REDIS_URL, queue/topic names, *_SERVICE_URL), "
    "docker-compose services, Dockerfiles.",
    "cloud": "IaC (Terraform *.tf, Bicep, ARM, CloudFormation, CDK, Pulumi), Helm values, pipeline deploy "
    "steps, SDK clients in code (azure-*, boto3, google-cloud-*), app settings and connection strings.",
    "deployment": "docker-compose, Kubernetes manifests, Helm charts, Terraform, Dockerfiles, Procfiles, "
    "ingress/nginx config, CI deploy jobs.",
    "network": "Terraform/Bicep network resources (VNet/VPC, subnets, NSGs, firewalls, gateways), "
    "Kubernetes network policies, ingress, DNS config.",
    "c4-context": "README and docs for purpose and users, auth providers, outbound integrations (payment, "
    "email, SaaS SDKs), inbound webhooks.",
    "c4-container": "deployable units (each Dockerfile, service folder, frontend app, worker, function app), "
    "their data stores and the protocols between them.",
    "dataflow": "ingestion code, ETL jobs, schedulers, queue producers/consumers, storage buckets, "
    "transforms, sinks and exports.",
    "pipeline": ".github/workflows, azure-pipelines.yml, .gitlab-ci.yml, Jenkinsfile, Makefile targets, "
    "release scripts: stages, jobs, environments, approvals, artifacts.",
    "erd": "ORM models (SQLAlchemy, Django models, Prisma schema, TypeORM/EF entities), migrations, "
    "schema.sql: tables, primary/foreign keys, relationships and cardinality.",
    "flowchart": "the function or workflow named in the focus: its branches, loops, error paths and exits.",
    "swimlane": "the workflow in the focus and which actor/service performs each step.",
    "state": "status enums, state fields and the transitions that change them.",
    "org": "CODEOWNERS, team docs, ownership files.",
    "mindmap": "README, docs and top-level folders: the main concepts and their parts.",
}

EXAMPLE = {
    "title": "Orders Platform",
    "subtitle": "acme/orders-api + acme/web · containers view",
    "type": "architecture",
    "layout": "flowchart-lr",
    "groups": [
        {"id": "clients", "label": "Clients", "kind": "tier"},
        {"id": "services", "label": "Services", "kind": "tier"},
        {"id": "data", "label": "Data", "kind": "tier"},
        {"id": "ext", "label": "Third Parties", "kind": "external"},
    ],
    "nodes": [
        {"id": "shopper", "label": "Shopper", "kind": "user"},
        {"id": "web", "label": "Storefront", "kind": "webapp", "group": "clients",
         "technology": "TypeScript / Next.js", "description": "Product pages and checkout."},
        {"id": "api", "label": "Orders API", "kind": "api", "group": "services",
         "technology": "Python / FastAPI", "description": "Creates and tracks orders.", "emphasis": True},
        {"id": "worker", "label": "Fulfilment Worker", "kind": "service", "group": "services",
         "technology": "Python / Celery", "description": "Ships paid orders."},
        {"id": "db", "label": "Orders DB", "kind": "database", "group": "data", "technology": "PostgreSQL"},
        {"id": "queue", "label": "Task Queue", "kind": "queue", "group": "data", "technology": "Redis"},
        {"id": "stripe", "label": "Stripe", "kind": "external", "group": "ext",
         "description": "Card payments (from STRIPE_API_KEY usage)."},
    ],
    "edges": [
        {"source": "shopper", "target": "web", "label": "HTTPS"},
        {"source": "web", "target": "api", "label": "REST / JSON"},
        {"source": "api", "target": "db", "label": "SQL"},
        {"source": "api", "target": "queue", "label": "enqueues", "style": "dashed"},
        {"source": "queue", "target": "worker", "label": "consumes", "style": "dashed"},
        {"source": "api", "target": "stripe", "label": "charges"},
    ],
}

SYSTEM_TEMPLATE = """\
You are an expert software architect and information designer. You read real codebases and turn
them into clear, accurate, presentation-quality diagrams. Your output is ONE DiagramSpec (nodes,
groups, edges by meaning, no coordinates) that the app draws live in Microsoft Visio.

Requested diagram type: {diagram_type}{provider_line}

# Workflow
1. Read the workspace digest in the first message: repos, languages, frameworks, cloud hints,
   key files. It is a starting map, not proof.
2. Explore purposefully with the read-only tools (list_dir, find_files, search, read_file).
   Typically 8-25 tool calls. Call several tools in parallel in one turn when they are
   independent (e.g. read three manifests at once). Prioritise:
   - entrypoints and manifests (package.json, pyproject.toml, *.csproj, go.mod, pom.xml)
   - config and env files: DATABASE_URL, REDIS_URL, queue/topic names, *_SERVICE_URL, API base URLs
   - IaC and runtime: docker-compose, Dockerfiles, Kubernetes/Helm, Terraform, Bicep
   - routers/controllers and HTTP clients (who calls whom, over what)
   - ORM models and migrations (for erd); CI workflows (for pipeline)
   For this diagram type look especially at: {evidence}
   Use search (regex) to trace connections, e.g. search 'DATABASE_URL|REDIS_URL' or
   search 'requests\\.(get|post)|fetch\\(|HttpClient'. Read only the parts of files you need
   (read_file takes start_line / max_lines).
   Never read lockfiles (package-lock.json, yarn.lock, poetry.lock, uv.lock...), minified or
   bundled files, vendored/third-party folders (node_modules, vendor, dist, build, .venv),
   or binaries. Never try to write or execute anything.
3. Decide nodes, groups and edges grounded ONLY in evidence from the code. Do not invent
   components, clouds or services you did not see. When something is inferred rather than
   explicit (e.g. a database implied by a driver dependency), say so briefly in the node's
   description ("inferred from psycopg dependency"). Prefer fewer, true elements over many guesses.
4. Follow the ground rules for the requested type (below) and use only node kinds from the
   kinds list (below; list_kinds gives it again, get_rules gives rules for other types).
5. Submit exactly one spec with the submit_diagram tool: its arguments ARE the DiagramSpec
   object (title, subtitle, type, layout, theme, legend, nodes, edges, groups). Do not paste
   the JSON in a message. If the tool reports validation errors or lint findings, fix them and
   call submit_diagram again with the complete corrected spec. If you judge a finding
   acceptable, resubmit the same spec unchanged.

# Quality rules
- Labels: Title Case, at most 4 words ("Orders API", not "the orders api service").
- technology: the stack in short form, "Python / FastAPI", "PostgreSQL 16", "Azure Functions".
- description: optional, one short sentence on the node's responsibility.
- Edge labels: protocol or verb ("HTTPS", "gRPC", "SQL", "publishes", "reads"). Solid lines
  for synchronous calls, dashed for async/events/queues, dotted for optional.
- Groups: tiers (Clients / Services / Data), trust boundaries, environments, or the cloud
  hierarchy (subscription > region > vnet > subnet) via group.parent. Every group needs at
  least one node. A node belongs to at most one (its innermost) group.
- Size: 8-30 nodes. Merge trivial pieces (helpers, utils, tests); split a monolith only along
  real module or deployment boundaries. Leave out tests, CI helpers and docs unless the type
  is about them.
- title: the system name. subtitle: helpful scope line, e.g. repo names + view
  ("acme/api + acme/web · container view").
- emphasis: only for the core system or the node the focus asks about (1-3 nodes).
- Ids: short snake_case, unique, no spaces. Leave layout and theme as "auto" unless the
  rules or the user ask for something specific.
- Keep the main flow in one direction (users/clients first, data stores last).

# DiagramSpec essentials
- nodes[]: id (required), label, kind, group, technology, description, emphasis
- edges[]: source, target (node ids), label, style (solid|dashed|dotted), arrow (end|both|none)
- groups[]: id, label, kind (generic|tier|system|boundary|cloud|region|zone|network|subnet|
  cluster|environment|lane|external), parent
- top level: title, subtitle, type, layout (auto|flowchart-lr|flowchart-tb|tree-tb|...),
  theme (auto or a theme name), legend (bool)
- Edges connect nodes only (never groups). Node and group ids must not collide.

# Example (architecture)
{example}

# Ground rules for {diagram_type} diagrams
{rules}

# Node kinds
{kinds}
"""


def build_system_prompt(diagram_type: str, rules: str, kinds: str, provider_hint: str | None = None) -> str:
    provider_line = f"\nCloud provider in scope: {provider_hint}" if provider_hint else ""
    return SYSTEM_TEMPLATE.format(
        diagram_type=diagram_type,
        provider_line=provider_line,
        evidence=EVIDENCE.get(diagram_type, EVIDENCE["architecture"]),
        example=json.dumps(EXAMPLE, indent=1),
        rules=rules.strip() or "(no extra rules for this type)",
        kinds=kinds.strip() or "(call list_kinds)",
    )


def first_message(digest: str, diagram_type: str, focus: str, repo_names: list[str]) -> str:
    focus_line = f"Focus / user request: {focus}\n" if focus.strip() else ""
    return (
        f"Create a {diagram_type} diagram of: {', '.join(repo_names) or 'the workspace'}.\n"
        f"{focus_line}"
        "Paths in the tools are relative to the workspace root shown in the digest"
        + (" (prefix with the repo folder name when there are several repos)" if len(repo_names) > 1 else "")
        + ".\n\n"
        "# Workspace digest\n"
        f"{digest}\n\n"
        "Explore the code to confirm components and connections, then call submit_diagram."
    )


NUDGE_SUBMIT = (
    "You ended your turn without calling submit_diagram. Call submit_diagram now with the "
    "complete DiagramSpec as its arguments (not as text)."
)

NUDGE_BUDGET = (
    "You are running low on steps; submit your diagram now with submit_diagram, using what "
    "you have already found."
)


def refine_message(feedback: str, current_spec_json: str) -> str:
    return (
        f"Change request from the user: {feedback}\n\n"
        "Update the diagram accordingly. Explore the code again only if the change needs new "
        "evidence. Then call submit_diagram with the COMPLETE updated spec (not a diff).\n\n"
        f"Current spec (as drawn):\n{current_spec_json}"
    )
