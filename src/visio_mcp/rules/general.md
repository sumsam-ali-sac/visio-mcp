# General diagramming rules

These rules apply to every diagram, whatever its type. The type and provider files add
specifics on top. `visio_mcp.lint` checks most of them and reports findings as
`[code] message`; fix them before you call the diagram done.

## 1. One question per diagram
- Write down the question first: "How does an order flow from checkout to the warehouse?",
  "What runs where in production?". Everything that does not help answer it goes.
- Name the audience. Executives get a context view; engineers get containers or
  deployment; operators get network and runbook flows. Never mix audiences on one page.
- 5 to 30 nodes. Under 5, a sentence may do. Over 30 (`[size]`), split.

## 2. Choose the diagram type
| Question | Type |
|---|---|
| What steps and decisions make up this process? | `flowchart` |
| Who does which step, and where are the hand-offs? | `swimlane` |
| What is the system and who/what does it talk to? | `c4-context` |
| What deployable apps and stores make up the system? | `c4-container` or `architecture` |
| Which cloud services implement it? | `cloud` (+ provider rules) |
| What runs on which host, cluster or environment? | `deployment` |
| How are networks, subnets and devices connected? | `network` |
| Where does data come from, how is it transformed, where does it land? | `dataflow` |
| What are the stages of a build/release or ETL job? | `pipeline` |
| What are the tables/entities and their relationships? | `erd` |
| Who reports to whom? | `org` |
| What states can this object be in and what moves it between them? | `state` |
| How do ideas break down from one central topic? | `mindmap` |

Set `type` explicitly. `auto` guesses from the kinds, but you know the intent.

## 3. Split big systems (C4 thinking)
Draw several small diagrams instead of one poster: a **context** view (the system as
one box, its users and neighbours), a **container** view (apps, APIs, stores inside the
system), a **deployment** view (where containers run), and a **dataflow** or
**sequence-like flowchart** for one important scenario. Keep names identical across views.

## 4. Naming
- Node and group labels: Title Case nouns, the thing's name: `Orders API`, `Payments DB`,
  `Customer`. Not verbs, not sentences. The server title-cases them for you.
- Edge labels: short lowercase verb or protocol phrases: `reads`, `publishes order`,
  `HTTPS`, `SQL`, `AMQP`, `yes`. Acronyms keep their case.
- Labels: at most 4 words (`[label-length]` fires above 5). Put the technology in
  `technology` (`"Python / FastAPI"`) and one-sentence detail in `description`.
- Use official product names (`Azure Cosmos DB`, `Amazon S3`, `Cloud Run`), not
  nicknames. Labels must be unique (`[duplicate-label]`); two boxes with the same name
  are either one thing or badly named.
- Ids: short snake_case (`orders_db`). An empty label becomes the humanized id
  (`orders_db` -> `Orders DB`).

## 5. Flow direction
- Left to right (`flowchart-lr`): architecture, cloud, C4, dataflow, pipelines. Callers
  on the left, data stores on the right, as in reading order.
- Top to bottom (`flowchart-tb`): processes, flowcharts, state machines, networks
  (internet at the top, devices at the bottom), and `tree-tb` for hierarchies.
- Keep one main direction. Long edges going back against the flow mean the order of
  nodes or the grouping is wrong.
- Avoid crossings by ordering: list nodes in flow order and keep connected nodes in the
  same or adjacent groups.

## 6. Grouping
- Group by meaning: tiers (Presentation, Services, Data), trust boundaries
  (`boundary`), environments, ownership, or cloud scopes.
- Nest outer to inner: **cloud/account > region > network (VNet/VPC) > subnet >
  workload/cluster** (`[nesting-order]`). At most 4 levels (`[nesting]`).
- A group with one node rarely earns its frame (`[single-member]`); remove it unless it
  is a real boundary (subnet, zone, lane).
- External systems sit outside your boundaries, or in a group of kind `external`
  (`[external-placement]`).

## 7. Color discipline
- Let the theme color by category; `auto` picks one per type (azure/aws/gcp for cloud,
  c4 for C4, professional otherwise).
- Custom `fill`/`color` at most for 1-2 highlights (`[colors]`). `emphasis: true` on at
  most 2 nodes (`[emphasis]`): the thing that changed, the bottleneck, the failure.
- Never encode meaning in color alone; the label or legend must say it too.

## 8. Edge discipline
- Every edge that carries meaning gets a label; in architecture-style diagrams more
  than half unlabeled is a finding (`[edge-labels]`).
- `solid` = synchronous call/request; `dashed` = asynchronous message or event;
  `dotted` = optional, weak or occasional dependency.
- Arrow points in the direction of the call or the data movement - pick one and say
  which in the subtitle or legend. Two-way arrows only for truly symmetric links
  (replication, peering) (`[bidirectional]`).
- No orphan nodes (`[orphan]`): if it does not connect, it does not belong.
- No duplicate edges (`[duplicate-edge]`) and no self-loops outside state machines.

## 9. Title, subtitle, legend
- Title: system + view, e.g. `Orders Platform - Container View` (`[title]`).
- Subtitle: scope, audience, date or version: `Production, EU region - v2.3, Oct 2026`.
- Keep `legend: true` whenever shapes, line styles or group kinds are not obvious. The
  server builds it from what you used.

## 10. Consistency
- Same thing, same name, same kind, in every diagram of the set.
- Same direction and theme across a set of diagrams.
- One level of abstraction per diagram: do not mix a "Payments System" box with
  individual Lambda functions from another system.

## Lint codes
`render_diagram` returns findings as `[code] message`, most important first. Fix them
with `patch_diagram` or a corrected spec.

| Code | Means |
|---|---|
| `[size]` | More than 30 nodes: split the diagram. |
| `[decision]` | A decision lacks two labeled branches. |
| `[lane]` | Swimlane step outside a lane, or no lanes. |
| `[orphan]` | Node with no edges. |
| `[terminal]` | Flowchart without start/end, state machine without initial state. |
| `[c4-context]` | Containers drawn in a context diagram. |
| `[provider-kinds]` / `[mixed-providers]` | Cloud diagram without provider kinds, or mixing providers. |
| `[unknown-kind]` | Kind not in `list_kinds`; it draws as a plain rectangle. |
| `[label-length]` / `[edge-label-length]` | Node label over 5 words / edge label over 4 words. |
| `[duplicate-label]` | Two nodes with the same name. |
| `[erd-cardinality]` | ERD relationship without cardinality. |
| `[state-events]` | State transition without its event. |
| `[edge-labels]` | Most edges unlabeled in an architecture-style diagram. |
| `[external-placement]` | External system inside an internal group. |
| `[nesting]` / `[nesting-order]` | Groups too deep, or nested inner-to-outer. |
| `[layout]` | Layout does not suit the type (lanes, trees). |
| `[emphasis]` / `[colors]` | Too many highlights or custom colors. |
| `[title]` | Missing specific title or subtitle. |
| `[single-member]` | Group framing one node. |
| `[bidirectional]` | Too many two-way edges. |
| `[self-loop]` / `[duplicate-edge]` | Edge to itself (outside state machines), repeated edge. |

## Checklist
- [ ] One question, one audience, 5-30 nodes
- [ ] Right type and layout; type set explicitly
- [ ] Title Case node names <= 4 words; tech and detail moved out of the label
- [ ] Edges labeled with verbs/protocols; dashed for async; no orphans
- [ ] Groups nested outer-to-inner; externals outside the boundary
- [ ] Theme colors; at most 2 highlights
- [ ] Title + subtitle with scope and version; legend on
