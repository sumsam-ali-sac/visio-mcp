# State machine

**Use when:** one object (order, ticket, device, session) moves through states driven by events.

## Purpose
A UML state machine: the states an object can be in, the events that move it, the
guards that decide, and the start and final states. It answers "what can happen to an
order next?" - not "which code runs".

## Spec settings
- `"type": "state"`, `"layout": "flowchart-tb"` (`flowchart-lr` for long linear
  lifecycles).
- Theme: `professional`.

## Node kinds
| Kind | Use for |
|---|---|
| `initial` (or `start`) | The initial pseudo-state (exactly one; label it `Start` or the creation event). |
| `state` | A state: an adjective or past participle - `Pending`, `Paid`, `Shipped`. |
| `decision` | A choice pseudo-state when one event leads to different states by guard. |
| `final` (or `end`) | Final state(s): `Closed`, `Cancelled`. |

Name states as conditions the object is *in* (`Awaiting Payment`), never actions
(`Pay Order`). Composite states: use a `generic` group around the sub-states.

## Edges (transitions)
- Every transition is labeled with its trigger, UML style: `event [guard] / action`,
  e.g. `payment received`, `timeout [> 7 days] / cancel`, `ship / email customer`
  (`[state-events]`). Only the transition out of the initial state may be unlabeled.
- Self-transitions are allowed here (re-entering a state on an event).
- `dashed` for time-based or system-generated events if you want to separate them
  from user actions; say so in the legend.

## Checklist
- [ ] One initial state (`[terminal]`); final states where the lifecycle ends
- [ ] States are nouns/adjectives; transitions are events
- [ ] Every transition labeled with its event (and guard where it branches)
- [ ] No unreachable states, no dead ends except final states
- [ ] 4-15 states; split composite states into their own diagram beyond that

## Common mistakes
- Drawing a flowchart of actions and calling it a state machine.
- Unlabeled transitions: the diagram then says nothing about *why* state changes.
- Two transitions from one state on the same event without guards (non-deterministic).
- Missing error/cancel paths: real lifecycles have them; show them.

## Example
```json
{
  "title": "Order Lifecycle",
  "subtitle": "Order aggregate states - Orders service v3",
  "type": "state",
  "layout": "flowchart-tb",
  "nodes": [
    {"id": "init", "label": "Start", "kind": "initial"},
    {"id": "pending", "label": "Pending Payment", "kind": "state"},
    {"id": "paid", "label": "Paid", "kind": "state"},
    {"id": "shipped", "label": "Shipped", "kind": "state"},
    {"id": "delivered", "label": "Delivered", "kind": "final"},
    {"id": "cancelled", "label": "Cancelled", "kind": "final"}
  ],
  "edges": [
    {"source": "init", "target": "pending", "label": "order placed"},
    {"source": "pending", "target": "paid", "label": "payment received"},
    {"source": "pending", "target": "cancelled", "label": "timeout [48h]", "style": "dashed"},
    {"source": "paid", "target": "shipped", "label": "dispatch / email customer"},
    {"source": "paid", "target": "cancelled", "label": "cancel / refund"},
    {"source": "shipped", "target": "delivered", "label": "delivery confirmed"}
  ]
}
```
