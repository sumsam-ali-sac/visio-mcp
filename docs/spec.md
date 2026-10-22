# Writing diagram specs

A `DiagramSpec` says **what** is in a diagram. visio-mcp decides **how it looks**: shapes,
sizes, positions, routes, fonts, colors, title block and legend. You never place shapes by hand
(except with `layout: "none"`).

## Anatomy

```json
{
  "title": "Order Intake",
  "subtitle": "AWS serverless · event-driven",
  "type": "cloud",
  "layout": "auto",
  "theme": "auto",
  "legend": true,
  "groups": [
    {"id": "aws", "label": "AWS Cloud", "kind": "cloud"},
    {"id": "region", "label": "us-east-1", "kind": "region", "parent": "aws"},
    {"id": "vpc", "label": "VPC", "kind": "network", "parent": "region"},
    {"id": "private", "label": "Private Subnet", "kind": "subnet", "parent": "vpc"}
  ],
  "nodes": [
    {"id": "client", "label": "Mobile App", "kind": "mobile"},
    {"id": "create", "label": "Create Order", "kind": "aws-lambda", "group": "region",
     "technology": "Python 3.12", "emphasis": true},
    {"id": "db", "label": "Inventory DB", "kind": "aws-aurora", "technology": "PostgreSQL",
     "group": "private", "description": "Stock levels per warehouse"}
  ],
  "edges": [
    {"source": "client", "target": "create", "label": "HTTPS"},
    {"source": "create", "target": "db", "label": "SQL"}
  ]
}
```

Full schema: [reference/diagram-spec.schema.json](reference/diagram-spec.schema.json).

### Diagram

| Field | Default | |
|---|---|---|
| `title` | `"Diagram"` | Big title, top-left. Short and specific. |
| `subtitle` | `""` | Scope, audience, version or date. Strongly recommended. |
| `type` | `"auto"` | One of 14 [diagram types](reference/diagram-types.md). `auto` infers it from the kinds. Drives layout, theme and rules. |
| `layout` | `"auto"` | `auto` picks per type. See below. |
| `theme` | `"auto"` | `auto` picks per type and cloud provider. See [themes](reference/themes.md). |
| `legend` | `true` | Legend of the node categories, line styles and boundary kinds actually used (skipped when it would have one entry). |

### Nodes

| Field | |
|---|---|
| `id` | Unique, short, snake_case. Edges refer to it. |
| `label` | Title Case noun, at most ~4 words. Cased automatically (acronyms such as API, AWS, PostgreSQL and iOS are kept). Defaults to a humanized id. |
| `kind` | Semantic kind: [reference/kinds.md](reference/kinds.md). Drives the shape and color. |
| `group` | The innermost group the node sits in. |
| `technology` | Shown as `[Python / FastAPI]` under the label, C4-style. |
| `description` | One short sentence in small text. |
| `emphasis` | Thick accent border. Use on the 1–2 nodes the diagram is about. |
| `icon` | Path to a custom `.svg`/`.png` icon. |
| `fill` | Override fill `#RRGGBB`. Prefer themes. |
| `x`, `y` | Center in inches; only with `layout: "none"`. |

### Edges

| Field | |
|---|---|
| `source`, `target` | Node ids. |
| `label` | A verb or protocol: `HTTPS`, `publishes OrderCreated`, `yes`. Rendered as a lowercase phrase. |
| `style` | `solid` = synchronous call, `dashed` = asynchronous/event, `dotted` = optional or weak. |
| `arrow` | `end` (default), `both`, `none` (ERD relationships). |
| `color` | Override `#RRGGBB`. |

### Groups

Groups become Visio containers. A node belongs to its innermost group; groups nest with `parent`.

| `kind` | Use for | Looks like |
|---|---|---|
| `tier` | Presentation / services / data | soft panel |
| `system` | A software system boundary (C4) | dashed frame in C4 |
| `boundary` | Trust boundary | red dashed frame |
| `cloud` | Subscription / account / project | provider-colored frame |
| `region`, `zone` | Cloud region, availability zone | dashed frame |
| `network`, `subnet` | VNet / VPC, subnets | tinted panels |
| `cluster` | Kubernetes or compute cluster | tinted panel |
| `environment` | dev / staging / prod | panel |
| `lane` | Swimlane (actor, team) | full-width lane |
| `external` | Things outside your control | grey dashed |
| `generic` | Anything else | panel |

Cloud nesting order: **cloud › region › network › (zone) › subnet › workload**.

## Layouts

| Layout | Picked by `auto` for | |
|---|---|---|
| `flowchart-tb` | flowchart, state, network | Layered top to bottom |
| `flowchart-lr` | architecture, cloud, C4, data flow, deployment, pipeline, ERD | Layered left to right |
| `tree-tb`, `tree-lr` | org | Tidy tree |
| `swimlane-lr`, `swimlane-tb` | swimlane | Top-level groups become lanes |
| `radial` | mind map | Hub and spokes |
| `circular`, `grid` | | Rings and inventories |
| `none` | | Your own `x`/`y` |

The layout engine is group-aware: groups never overlap each other or non-members, members always
sit inside their frames, nested groups inside their parents, and edges are orthogonal with
spread ports.

## Patching

After a render, edit with `patch_diagram` (MCP) or by chatting in the studio. See the op table
in [The MCP server](mcp-server.md#tools). The spec is updated and the diagram is redrawn.

## Quality checklist

The linter (`lint_diagram`, `/lint`) checks these and more, each finding prefixed by a rule code:

- 5–30 nodes; split bigger systems into several diagrams (context, containers, deployment).
- Every node connected; every edge that carries meaning is labeled.
- Decisions have two or more labeled outgoing edges; flowcharts have start and end.
- Labels are short; details go in `technology` and `description`.
- Cloud diagrams use the provider's kinds, one provider, and the standard nesting.
- At most two emphasized nodes; few custom colors.

Rule codes and the full conventions per type: [reference/diagram-types.md](reference/diagram-types.md).
