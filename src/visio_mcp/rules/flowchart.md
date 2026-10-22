# Flowchart

**Use when:** you need the steps and decisions of one process, with a clear start and end.

## Purpose
Show how a single process runs: the steps, the decisions that branch it and where it
ends. Symbols follow ISO 5807 / ANSI conventions: rounded terminator, rectangle
process, diamond decision, parallelogram input/output, document, predefined process.

## Spec settings
- `"type": "flowchart"`, `"layout": "flowchart-tb"` (top to bottom). Use
  `flowchart-lr` only for short, wide flows on slides.
- Theme: `professional` (auto). Use `swimlane` instead when *who* does a step matters.

## Node kinds
| Kind | Use for |
|---|---|
| `start`, `end` | Exactly one start; one or more ends (success, rejected, cancelled). |
| `process` | One action, verb + object: `Validate Order`, `Send Invoice`. |
| `decision` | A yes/no question: `Payment OK?`, `In Stock?`. |
| `data` | Input/output: `Order Form`, `Shipping Label`. |
| `document` | A produced or consumed document/report. |
| `subprocess` | A step detailed in another diagram. |
| `manual` | A step a person does by hand. |

Do not use architecture kinds (`service`, `database`, cloud icons) in a flowchart; the
step is "Store Order", not a database icon. A data store touched by many steps is
better described in the step label or a `data` node.

Process labels are verb-first ("Approve Request"), the exception to the noun rule.
Decision labels are short questions ending in `?`.

## Groups
Usually none. Use `generic` groups sparingly to frame phases (`Intake`, `Fulfilment`).
If you need actors, switch to a swimlane diagram.

## Edges
- Every decision has 2+ outgoing edges, each labeled with the branch: `yes`/`no`, or
  the condition (`< $500`, `>= $500`) (`[decision]`).
- Plain sequence edges stay unlabeled.
- Loops back (retry, rework) go to an earlier step; keep them few and label them
  (`retry`). Use `dashed` for exception or timeout paths.

## Checklist
- [ ] One `start`, at least one `end` (`[terminal]`)
- [ ] Every step reachable from start and leads to an end (no orphans)
- [ ] Decisions are questions with labeled branches
- [ ] Steps are verb + object, <= 4 words
- [ ] 5-25 nodes; deeper detail moved to a `subprocess`

## Common mistakes
- Decision with one outgoing edge, or unlabeled branches.
- Mixing system components into the flow ("API", "DB") instead of actions.
- Several starts; dangling steps with no way to an end.
- Spaghetti loops: model a retry as one labeled back edge, not many.

## Example
```json
{
  "title": "Order Fulfilment",
  "subtitle": "Happy path and payment failure - v1.2",
  "type": "flowchart",
  "layout": "flowchart-tb",
  "nodes": [
    {"id": "start", "label": "Order Received", "kind": "start"},
    {"id": "validate", "label": "Validate Order", "kind": "process"},
    {"id": "stock", "label": "In Stock?", "kind": "decision"},
    {"id": "backorder", "label": "Create Backorder", "kind": "process"},
    {"id": "charge", "label": "Charge Card", "kind": "process"},
    {"id": "paid", "label": "Payment OK?", "kind": "decision"},
    {"id": "ship", "label": "Ship Order", "kind": "process"},
    {"id": "notify", "label": "Notify Customer", "kind": "document"},
    {"id": "done", "label": "Order Complete", "kind": "end"},
    {"id": "cancel", "label": "Order Cancelled", "kind": "end"}
  ],
  "edges": [
    {"source": "start", "target": "validate"},
    {"source": "validate", "target": "stock"},
    {"source": "stock", "target": "charge", "label": "yes"},
    {"source": "stock", "target": "backorder", "label": "no"},
    {"source": "backorder", "target": "notify"},
    {"source": "charge", "target": "paid"},
    {"source": "paid", "target": "ship", "label": "yes"},
    {"source": "paid", "target": "cancel", "label": "no"},
    {"source": "ship", "target": "notify"},
    {"source": "notify", "target": "done"}
  ]
}
```
